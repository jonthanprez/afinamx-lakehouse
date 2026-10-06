"""Anomaly and chaos injection engine for synthetic WooCommerce data.

Designed to realistically simulate messy, real-world e-commerce source data
for testing Bronze-to-Silver data quality, schema enforcement, and quarantine pipelines.
"""

import copy
import random
from typing import Any, Dict, List, Optional

from src.common.logger import get_logger

logger = get_logger(__name__)

ANOMALY_NULL_FIELDS = "null_fields"
ANOMALY_DUPLICATE_ORDERS = "duplicate_orders"
ANOMALY_MATH_MISMATCH = "math_mismatch"
ANOMALY_INVALID_NUMBERS = "invalid_numbers"
ANOMALY_CORRUPTED_DATES = "corrupted_dates"
ANOMALY_MALFORMED_FORMATS = "malformed_formats"

SUPPORTED_ANOMALIES = [
    ANOMALY_NULL_FIELDS,
    ANOMALY_DUPLICATE_ORDERS,
    ANOMALY_MATH_MISMATCH,
    ANOMALY_INVALID_NUMBERS,
    ANOMALY_CORRUPTED_DATES,
    ANOMALY_MALFORMED_FORMATS,
]


class AnomalyInjector:
    """Injects realistic data quality anomalies and defects into raw order batches."""

    def __init__(
        self,
        anomaly_rate: float = 0.15,
        enabled_anomalies: Optional[List[str]] = None,
    ) -> None:
        """Initializes the Anomaly Injector.

        Args:
            anomaly_rate: Probability (0.0 to 1.0) of a record being corrupted.
            enabled_anomalies: List of anomaly names to activate. Defaults to all supported anomalies.
        """
        self.anomaly_rate = max(0.0, min(1.0, anomaly_rate))
        if enabled_anomalies is None:
            self.enabled_anomalies = list(SUPPORTED_ANOMALIES)
        else:
            self.enabled_anomalies = [
                a for a in enabled_anomalies if a in SUPPORTED_ANOMALIES
            ]

        logger.debug(
            "Initialized AnomalyInjector",
            extra={
                "anomaly_rate": self.anomaly_rate,
                "enabled_anomalies": self.enabled_anomalies,
            },
        )

    def inject_null_fields(self, order: Dict[str, Any]) -> None:
        """Injects missing or None values into required/optional fields."""
        targets = [
            "customer_email",
            "customer_postcode",
            "payment_method",
            "customer_address",
        ]
        chosen = random.choice(targets)

        if chosen == "customer_email" and order.get("customer"):
            order["customer"]["email"] = None
        elif chosen == "customer_postcode" and order.get("customer"):
            order["customer"]["postcode"] = None
        elif chosen == "customer_address" and order.get("customer"):
            order["customer"]["address"] = None
        elif chosen == "payment_method":
            order["payment_method"] = None

    def inject_math_mismatch(self, order: Dict[str, Any]) -> None:
        """Inconsistency between line item unit prices, quantities, and order totals."""
        if random.random() < 0.5:
            # Modify overall order total
            current_total = float(order.get("total", "100.00"))
            drift = random.choice([25.50, -30.00, 100.00])
            tampered = max(0.0, current_total + drift)
            order["total"] = f"{tampered:.2f}"
        else:
            # Modify single line item total vs unit_price * quantity
            line_items = order.get("line_items", [])
            if line_items:
                target_item = random.choice(line_items)
                fake_line_total = round(
                    float(target_item.get("total", "10.00")) * 1.75, 2
                )
                target_item["total"] = f"{fake_line_total:.2f}"

    def inject_invalid_numbers(self, order: Dict[str, Any]) -> None:
        """Injects negative prices, zero quantities, or negative totals."""
        scenario = random.choice(["negative_price", "zero_quantity", "negative_total"])
        line_items = order.get("line_items", [])

        if scenario == "negative_price" and line_items:
            target_item = random.choice(line_items)
            target_item["unit_price"] = "-49.99"
        elif scenario == "zero_quantity" and line_items:
            target_item = random.choice(line_items)
            target_item["quantity"] = 0
        elif scenario == "negative_total":
            order["total"] = "-150.00"

    def inject_corrupted_dates(self, order: Dict[str, Any]) -> None:
        """Injects unparseable timestamps or temporal sequence violations."""
        if random.random() < 0.5:
            # Corrupted / invalid timestamp string
            order["date_created"] = "2026-13-45T99:99:99"
        else:
            # Modified date earlier than created date
            order["date_modified_gmt"] = "2020-01-01T00:00:00+00:00"

    def inject_malformed_formats(self, order: Dict[str, Any]) -> None:
        """Injects malformed emails or non-numeric strings in number fields."""
        if random.random() < 0.5 and order.get("customer"):
            order["customer"]["email"] = "broken.user@@invalid_domain"
        else:
            order["total"] = "N/A"

    def _apply_record_mutation(self, order: Dict[str, Any]) -> Optional[str]:
        """Randomly selects and applies an active record-level anomaly."""
        record_anomalies = [
            a for a in self.enabled_anomalies if a != ANOMALY_DUPLICATE_ORDERS
        ]
        if not record_anomalies:
            return None

        chosen_anomaly = random.choice(record_anomalies)

        if chosen_anomaly == ANOMALY_NULL_FIELDS:
            self.inject_null_fields(order)
        elif chosen_anomaly == ANOMALY_MATH_MISMATCH:
            self.inject_math_mismatch(order)
        elif chosen_anomaly == ANOMALY_INVALID_NUMBERS:
            self.inject_invalid_numbers(order)
        elif chosen_anomaly == ANOMALY_CORRUPTED_DATES:
            self.inject_corrupted_dates(order)
        elif chosen_anomaly == ANOMALY_MALFORMED_FORMATS:
            self.inject_malformed_formats(order)

        return chosen_anomaly

    def inject(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Injects anomalies across the provided order batch.

        Args:
            orders: List of raw order dictionaries.

        Returns:
            New list of order dictionaries with injected anomalies.
        """
        if not orders or self.anomaly_rate <= 0.0 or not self.enabled_anomalies:
            return orders

        mutated_orders = copy.deepcopy(orders)
        injected_count = 0

        # 1. Apply record-level mutations
        for order in mutated_orders:
            if random.random() < self.anomaly_rate:
                anomaly_type = self._apply_record_mutation(order)
                if anomaly_type:
                    injected_count += 1

        # 2. Apply batch-level duplicate anomalies
        if (
            ANOMALY_DUPLICATE_ORDERS in self.enabled_anomalies
            and len(mutated_orders) > 1
            and random.random() < self.anomaly_rate
        ):
            # Duplicate an order by replacing another record in the batch (simulates duplicate event / retry)
            idx_to_clone = random.randint(0, len(mutated_orders) - 1)
            idx_to_overwrite = random.randint(0, len(mutated_orders) - 1)
            while idx_to_overwrite == idx_to_clone and len(mutated_orders) > 1:
                idx_to_overwrite = random.randint(0, len(mutated_orders) - 1)

            cloned_order = copy.deepcopy(mutated_orders[idx_to_clone])
            mutated_orders[idx_to_overwrite] = cloned_order
            injected_count += 1
            logger.debug(
                "Injected duplicate order anomaly",
                extra={"duplicated_order_id": cloned_order.get("id")},
            )

        logger.info(
            "Anomaly injection completed",
            extra={
                "batch_size_initial": len(orders),
                "batch_size_final": len(mutated_orders),
                "anomalies_injected": injected_count,
                "anomaly_rate": self.anomaly_rate,
            },
        )

        return mutated_orders
