"""WooCommerce source system simulator (event and transaction generator).

Responsible for generating simulated transactions (JSON orders) while maintaining the
incremental state of the `order_id` and the persistence of the reusable customer pool.
"""

import json
import logging
from typing import TypedDict
from pathlib import Path
from faker import Faker

from src.ingest.config import (
    WOOCOMMERCE_CUSTOMERS_FILE,
    WOOCOMMERCE_STATE_FILE,
)


class Customer(TypedDict):
    id: int
    first_name: str
    last_name: str
    email: str
    address: str
    city: str
    state: str
    postcode: str
    country: str


logger = logging.getLogger(__name__)

fake = Faker("es_MX")


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
        self.customer_pool = self._load_or_create_customer_pool()

    def _load_or_create_customer_pool(self) -> list[Customer]:
        """Loads the customer pool from disk or generates it using Faker if it does not exist."""
        if self.customers_file.exists():
            try:
                with open(self.customers_file, "r", encoding="utf-8") as f:
                    pool: list[Customer] = json.load(f)
                    logger.info(
                        "clients pool charged from metadata (%d records in %s)",
                        len(pool),
                        self.customers_file,
                    )
                    return pool
            except (json.JSONDecodeError, OSError) as err:
                logger.warning(
                    "Error reading client file %s. A new pool will be regenerated. Details: %s",
                    self.customers_file,
                    err,
                    exc_info=True,
                )

        logger.info(
            "Starting Cold Start: Generating initial pool of %d clients with Faker...",
            self.customer_pool_size,
        )

        pool: list[Customer] = [
            {
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
            for customer_id in range(1, self.customer_pool_size + 1)
        ]

        self._save_customer_pool(pool)
        return pool
