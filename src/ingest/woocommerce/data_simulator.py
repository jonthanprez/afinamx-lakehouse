"""WooCommerce source system simulator (event and transaction generator).

Responsible for generating simulated transactions (JSON orders) while maintaining the
incremental state of the `order_id` and the persistence of the reusable customer pool.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import random
from typing import Optional
from faker import Faker

from src.ingest.config import (
    WOOCOMMERCE_CUSTOMERS_FILE,
    WOOCOMMERCE_STATE_FILE,
)
from src.ingest.models import Customer, LineItem, Order, SimulatorState
from src.ingest.woocommerce.products import (
    METHODS_PAYMENT,
    ORDER_STATUS_CONFIG,
    PRODUCTS_CATALOG,
)

logger = logging.getLogger(__name__)
fake = Faker("es_MX")

DEFAULT_START_ORDER_ID = 1000


class WooCommerceDataSimulator:
    """Generates simulated transactional loads in WooCommerce v3-style JSON format."""

    def __init__(
        self,
        customer_pool_size: int = 50,
        returning_customer_ratio: float = 0.70,
    ) -> None:
        """Initializes the WooCommerce simulator.

        Args:
            - customer_pool_size: Initial number of customers to generate in the pool.
            - returning_customer_ratio: Probability (0.0 to 1.0) of reusing an existing customer.
        """
        self.state_file = Path(WOOCOMMERCE_STATE_FILE)
        self.customers_file = Path(WOOCOMMERCE_CUSTOMERS_FILE)
        self.customer_pool_size = customer_pool_size
        self.returning_customer_ratio = returning_customer_ratio

        logger.info(
            "Initializing WooCommerceDataSimulator (Pool Size: %d, Returning Ratio: %.2f)",
            self.customer_pool_size,
            self.returning_customer_ratio,
        )

        # Charge or initialize persistent pool client
        self.customer_pool: list[Customer] = self._load_or_create_customer_pool()

    def _generate_single_customer(self, customer_id: int) -> Customer:
        """Helper method to generate a single fake customer dict."""
        return {
            "id": customer_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": fake.email(),
            "address": fake.street_address(),
            "city": fake.city(),
            "state": fake.state_abbr(),
            "postcode": fake.postcode(),
            "country": "MX",
        }

    def _load_or_create_customer_pool(self) -> list[Customer]:
        """Loads the customer pool from disk or generates it using Faker if missing."""
        if self.customers_file.exists():
            try:
                pool: list[Customer] = json.loads(
                    self.customers_file.read_text(encoding="utf-8")
                )
                logger.info(
                    "Customer pool loaded successfully (%d records from %s)",
                    len(pool),
                    self.customers_file,
                )
                return pool
            except (json.JSONDecodeError, OSError) as err:
                logger.warning(
                    "Error reading customer file %s. Regenerating new pool. Details: %s",
                    self.customers_file,
                    err,
                    exc_info=True,
                )

        logger.info(
            "Cold Start: Generating initial pool of %d customers with Faker...",
            self.customer_pool_size,
        )
        pool = [
            self._generate_single_customer(cid)
            for cid in range(1, self.customer_pool_size + 1)
        ]
        self._save_customer_pool(pool)
        return pool

    def _save_customer_pool(self, pool: list[Customer]) -> None:
        """Atomically persists the customer pool to metadata storage."""
        temp_file = self.customers_file.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps(pool, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temp_file.replace(self.customers_file)
        logger.debug(
            "Customer pool atomically saved (%d registered customers)", len(pool)
        )

    def _get_last_order_id(self) -> int:
        """Reads the last persisted order_id from state storage."""
        if not self.state_file.exists():
            logger.info(
                "State file not found (%s). Setting initial order_id: %d",
                self.state_file,
                DEFAULT_START_ORDER_ID,
            )
            return DEFAULT_START_ORDER_ID

        try:
            state: SimulatorState = json.loads(
                self.state_file.read_text(encoding="utf-8")
            )
            last_id = state.get("last_order_id", DEFAULT_START_ORDER_ID)
            logger.info("Last order_id recovered from metadata: %d", last_id)
            return last_id
        except (json.JSONDecodeError, OSError) as err:
            logger.warning(
                "Error reading state file %s. Resetting order_id to %d. Details: %s",
                self.state_file,
                DEFAULT_START_ORDER_ID,
                err,
            )
            return DEFAULT_START_ORDER_ID

    def _save_last_order_id(self, last_id: int) -> None:
        """Atomically updates the processed order_id checkpoint."""
        state: SimulatorState = {
            "last_order_id": last_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        temp_file = self.state_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp_file.replace(self.state_file)
        logger.info("Checkpoint updated successfully: last_order_id = %d", last_id)

    def _select_or_create_customer(self) -> Customer:
        """Selects an existing customer from the pool or dynamically creates a new one."""
        if random.random() < self.returning_customer_ratio and self.customer_pool:
            return random.choice(self.customer_pool)

        new_id = len(self.customer_pool) + 1
        new_customer = self._generate_single_customer(new_id)

        self.customer_pool.append(new_customer)
        self._save_customer_pool(self.customer_pool)

        logger.debug(
            "New customer registered dynamically: ID %d (%s)",
            new_id,
            new_customer["email"],
        )
        return new_customer

    def generate_orders_batch(
        self, start_order_id: Optional[int] = None, count: int = 10
    ) -> list[Order]:
        """Generates a batch of simulated WooCommerce API orders.

        Args:
            start_order_id: Explicit starting order ID. If None, continues from last checkpoint.
            count: Number of order payloads to simulate.

        Returns:
            List of generated Order dictionaries matching WooCommerce schema.
        """
        logger.info("Starting order batch simulation (%d orders)...", count)
        if start_order_id is not None:
            current_order_id = start_order_id - 1
        else:
            current_order_id = self._get_last_order_id()
        orders: list[Order] = []

        for _ in range(count):
            current_order_id += 1

            # 1. Product selection and line items generation
            num_items = random.randint(1, 5)
            selected_products = random.sample(
                PRODUCTS_CATALOG, k=min(num_items, len(PRODUCTS_CATALOG))
            )

            line_items: list[LineItem] = []
            order_total = 0.0

            for prod in selected_products:
                qty = random.randint(1, 3)
                unit_price = prod["price"]
                item_total = round(qty * unit_price, 2)
                order_total += item_total

                line_items.append(
                    {
                        "product_id": prod["id"],
                        "sku": prod["sku"],
                        "name": prod["name"],
                        "brand": prod["brand"],
                        "category": prod["category"],
                        "quantity": qty,
                        "unit_price": f"{unit_price:.2f}",
                        "total": f"{item_total:.2f}",
                    }
                )

            # 2. Metadata assignment
            status = random.choices(
                ORDER_STATUS_CONFIG["statuses"],
                weights=ORDER_STATUS_CONFIG["weights"],
            )[0]
            payment_method = random.choice(METHODS_PAYMENT)
            customer = self._select_or_create_customer()
            now_iso = datetime.now(timezone.utc).isoformat()

            # 3. Payload assembly
            order_json: Order = {
                "id": current_order_id,
                "status": status,
                "currency": "MXN",
                "date_created": now_iso,
                "date_modified_gmt": now_iso,
                "total": f"{order_total:.2f}",
                "payment_method": payment_method,
                "customer": customer,
                "line_items": line_items,
            }

            orders.append(order_json)

        if start_order_id is None:
            self._save_last_order_id(current_order_id)
        else:
            self._last_order_id = current_order_id

        logger.info(
            "Batch completed successfully. Generated %d orders (IDs: %d to %d)",
            len(orders),
            current_order_id - count + 1,
            current_order_id,
        )
        return orders

    def generate_orders(self, num_orders: int = 10) -> list[Order]:
        """Backward-compatible alias for generating orders."""
        return self.generate_orders_batch(count=num_orders)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    )

    simulator = WooCommerceDataSimulator()
    batch = simulator.generate_orders(num_orders=3)

    print("\nSample of generated order:")
    print(json.dumps(batch[0], indent=2, ensure_ascii=False))
