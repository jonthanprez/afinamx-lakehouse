"""WooCommerce source system simulator (event and transaction generator).

Responsible for generating simulated transactions (JSON orders) while maintaining the
incremental state of the `order_id` and the persistence of the reusable customer pool.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional
from faker import Faker

from src.common.logger import get_logger, setup_logging
from src.ingest.config import (
    SIMULATOR_ANOMALY_RATE,
    SIMULATOR_ENABLE_ANOMALIES,
    WOOCOMMERCE_CUSTOMERS_FILE,
    WOOCOMMERCE_STATE_FILE,
)
from src.ingest.models import (
    Customer,
    IngestionState,
    LineItem,
    Order,
    SimulatorState,
)
from src.ingest.woocommerce.anomalies import AnomalyInjector
from src.ingest.woocommerce.products import (
    METHODS_PAYMENT,
    ORDER_STATUS_CONFIG,
    PRODUCTS_CATALOG,
)

logger = get_logger(__name__)
fake = Faker("es_MX")

DEFAULT_START_ORDER_ID = 1000


class WooCommerceDataSimulator:
    """Generates simulated transactional loads in WooCommerce v3-style JSON format."""

    def __init__(
        self,
        customer_pool_size: int = 50,
        returning_customer_ratio: float = 0.70,
        enable_anomalies: Optional[bool] = None,
        anomaly_rate: Optional[float] = None,
        enabled_anomalies: Optional[List[str]] = None,
    ) -> None:
        """Initializes the WooCommerce simulator.

        Args:
            customer_pool_size: Initial number of customers to generate in the pool.
            returning_customer_ratio: Probability (0.0 to 1.0) of reusing an existing customer.
            enable_anomalies: Flag to inject data quality defects. Defaults to SIMULATOR_ENABLE_ANOMALIES (True).
            anomaly_rate: Corruption probability rate. Defaults to SIMULATOR_ANOMALY_RATE (0.15).
            enabled_anomalies: Specific list of anomalies to enable. Defaults to all supported anomalies.
        """
        self.state_file = Path(WOOCOMMERCE_STATE_FILE)
        self.customers_file = Path(WOOCOMMERCE_CUSTOMERS_FILE)
        self.customer_pool_size = customer_pool_size
        self.returning_customer_ratio = returning_customer_ratio

        if enable_anomalies is not None:
            self.enable_anomalies = enable_anomalies
        else:
            self.enable_anomalies = SIMULATOR_ENABLE_ANOMALIES

        self.anomaly_rate = (
            anomaly_rate if anomaly_rate is not None else SIMULATOR_ANOMALY_RATE
        )
        self.enabled_anomalies = enabled_anomalies

        self.anomaly_injector = (
            AnomalyInjector(
                anomaly_rate=self.anomaly_rate,
                enabled_anomalies=self.enabled_anomalies,
            )
            if self.enable_anomalies
            else None
        )

        logger.info(
            "Initializing WooCommerceDataSimulator",
            extra={
                "customer_pool_size": self.customer_pool_size,
                "returning_customer_ratio": self.returning_customer_ratio,
                "enable_anomalies": self.enable_anomalies,
                "anomaly_rate": self.anomaly_rate,
            },
        )

        # Load or initialize persistent customer pool
        self.customer_pool: List[Customer] = self._load_or_create_customer_pool()

    def _generate_single_customer(self, customer_id: int) -> Customer:
        """Helper method to generate and validate a single fake customer model."""
        return Customer(
            id=customer_id,
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            email=fake.email(),
            address=fake.street_address(),
            city=fake.city(),
            state=fake.state_abbr(),
            postcode=fake.postcode(),
            country="MX",
        )

    def _load_or_create_customer_pool(self) -> List[Customer]:
        """Loads the customer pool from disk or generates it using Faker if missing."""
        if self.customers_file.exists():
            try:
                raw_pool = json.loads(self.customers_file.read_text(encoding="utf-8"))
                pool = [Customer.model_validate(c) for c in raw_pool]
                logger.info(
                    "Customer pool loaded successfully",
                    extra={
                        "pool_size": len(pool),
                        "customers_file": str(self.customers_file),
                    },
                )
                return pool
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning(
                    "Error reading customer file. Regenerating new pool",
                    exc_info=True,
                    extra={
                        "customers_file": str(self.customers_file),
                        "error": str(err),
                    },
                )

        logger.info(
            "Cold Start: Generating initial customer pool with Faker",
            extra={"customer_pool_size": self.customer_pool_size},
        )
        pool = [
            self._generate_single_customer(cid)
            for cid in range(1, self.customer_pool_size + 1)
        ]
        self._save_customer_pool(pool)
        return pool

    def _save_customer_pool(self, pool: List[Customer]) -> None:
        """Atomically persists the customer pool to metadata storage."""
        temp_file = self.customers_file.with_suffix(".tmp")
        serialized = [c.model_dump() for c in pool]
        temp_file.write_text(
            json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temp_file.replace(self.customers_file)
        logger.debug(
            "Customer pool saved atomically",
            extra={
                "pool_size": len(pool),
                "customers_file": str(self.customers_file),
            },
        )

    def _get_last_order_id(self) -> int:
        """Reads the last persisted order_id from state storage."""
        if not self.state_file.exists():
            logger.info(
                "State file not found. Setting initial order_id",
                extra={
                    "state_file": str(self.state_file),
                    "default_start_order_id": DEFAULT_START_ORDER_ID,
                },
            )
            return DEFAULT_START_ORDER_ID

        try:
            raw_state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if "last_execution_timestamp" in raw_state:
                state = IngestionState.model_validate(raw_state)
            else:
                state = SimulatorState.model_validate(raw_state)
            logger.info(
                "Last order_id recovered from metadata",
                extra={"last_order_id": state.last_order_id},
            )
            return state.last_order_id
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.warning(
                "Error reading state file. Resetting order_id",
                exc_info=True,
                extra={
                    "state_file": str(self.state_file),
                    "default_start_order_id": DEFAULT_START_ORDER_ID,
                    "error": str(err),
                },
            )
            return DEFAULT_START_ORDER_ID

    def _save_last_order_id(self, last_id: int) -> None:
        """Atomically updates the processed order_id checkpoint."""
        now_iso = datetime.now(timezone.utc).isoformat()
        state = IngestionState(
            dataset_name="woocommerce",
            last_order_id=last_id,
            last_updated_at=now_iso,
            last_execution_timestamp=now_iso,
            last_execution_status="SUCCESS",
        )
        temp_file = self.state_file.with_suffix(".tmp")
        temp_file.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        temp_file.replace(self.state_file)
        logger.info(
            "Checkpoint updated successfully",
            extra={
                "last_order_id": last_id,
                "state_file": str(self.state_file),
            },
        )

    def _select_or_create_customer(self) -> Customer:
        """Selects an existing customer from the pool or dynamically creates a new one."""
        if random.random() < self.returning_customer_ratio and self.customer_pool:
            return random.choice(self.customer_pool)

        new_id = len(self.customer_pool) + 1
        new_customer = self._generate_single_customer(new_id)

        self.customer_pool.append(new_customer)
        self._save_customer_pool(self.customer_pool)

        logger.debug(
            "New customer registered dynamically",
            extra={
                "customer_id": new_id,
                "email": new_customer.email,
            },
        )
        return new_customer

    def generate_orders_batch(
        self,
        start_order_id: Optional[int] = None,
        count: int = 10,
        enable_anomalies: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Generates a batch of simulated WooCommerce API orders.

        Args:
            start_order_id: Explicit starting order ID. If None, continues from last checkpoint.
            count: Number of order payloads to simulate.
            enable_anomalies: Explicitly enable/disable anomaly injection for this batch.

        Returns:
            List of generated Order dictionaries matching WooCommerce schema (with anomalies if enabled).
        """
        logger.info(
            "Starting order batch simulation",
            extra={"count": count, "start_order_id": start_order_id},
        )
        if start_order_id is not None:
            current_order_id = start_order_id - 1
        else:
            current_order_id = self._get_last_order_id()
        orders: List[Dict[str, Any]] = []

        for _ in range(count):
            current_order_id += 1

            # 1. Product selection and line items generation
            num_items = random.randint(1, 5)
            selected_products = random.sample(
                PRODUCTS_CATALOG, k=min(num_items, len(PRODUCTS_CATALOG))
            )

            line_items: List[LineItem] = []
            order_total = 0.0

            for prod in selected_products:
                qty = random.randint(1, 3)
                unit_price = prod.price
                item_total = round(qty * unit_price, 2)
                order_total += item_total

                line_items.append(
                    LineItem(
                        product_id=prod.id,
                        sku=prod.sku,
                        name=prod.name,
                        brand=prod.brand,
                        category=prod.category,
                        quantity=qty,
                        unit_price=f"{unit_price:.2f}",
                        total=f"{item_total:.2f}",
                    )
                )

            # 2. Metadata assignment
            status = random.choices(
                ORDER_STATUS_CONFIG["statuses"],
                weights=ORDER_STATUS_CONFIG["weights"],
            )[0]
            payment_method = random.choice(METHODS_PAYMENT)
            customer = self._select_or_create_customer()
            now_iso = datetime.now(timezone.utc).isoformat()

            # 3. Payload assembly and Pydantic validation
            order = Order(
                id=current_order_id,
                status=status,
                currency="MXN",
                date_created=now_iso,
                date_modified_gmt=now_iso,
                total=f"{order_total:.2f}",
                payment_method=payment_method,
                customer=customer,
                line_items=line_items,
            )

            orders.append(order.model_dump())

        if start_order_id is None:
            self._save_last_order_id(current_order_id)
        else:
            self._last_order_id = current_order_id

        # 4. Anomaly and Chaos Injection (Dirty by Default)
        should_inject = (
            enable_anomalies if enable_anomalies is not None else self.enable_anomalies
        )
        if should_inject and self.anomaly_injector is not None:
            orders = self.anomaly_injector.inject(orders)

        logger.info(
            "Batch simulation completed successfully",
            extra={
                "records_count": len(orders),
                "start_order_id": current_order_id - count + 1,
                "end_order_id": current_order_id,
                "anomalies_applied": should_inject,
            },
        )
        return orders

    def generate_orders(
        self, num_orders: int = 10, enable_anomalies: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Backward-compatible alias for generating orders."""
        return self.generate_orders_batch(
            count=num_orders, enable_anomalies=enable_anomalies
        )


if __name__ == "__main__":
    setup_logging(level="INFO")

    simulator = WooCommerceDataSimulator()
    batch = simulator.generate_orders(num_orders=3)

    print("\nSample of generated order:")
    print(json.dumps(batch[0], indent=2, ensure_ascii=False))
