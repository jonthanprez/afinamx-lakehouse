"""Unit tests for AnomalyInjector and dirty-by-default simulation."""

import copy
import pytest
from src.ingest.cli import build_parser, handle_generate
from src.ingest.models import Order
from src.ingest.woocommerce.anomalies import (
    ANOMALY_DUPLICATE_ORDERS,
    SUPPORTED_ANOMALIES,
    AnomalyInjector,
)
from src.ingest.woocommerce.data_simulator import WooCommerceDataSimulator


@pytest.fixture
def clean_order_dict(mock_order):
    """Provides a single clean dictionary order payload."""
    return copy.deepcopy(mock_order.model_dump())


def test_anomaly_injector_initialization_defaults():
    """Validates default initialization parameters of AnomalyInjector."""
    injector = AnomalyInjector()
    assert injector.anomaly_rate == 0.15
    assert set(injector.enabled_anomalies) == set(SUPPORTED_ANOMALIES)


def test_anomaly_injector_clamps_rate():
    """Validates that anomaly_rate is clamped between 0.0 and 1.0."""
    injector_low = AnomalyInjector(anomaly_rate=-0.5)
    assert injector_low.anomaly_rate == 0.0

    injector_high = AnomalyInjector(anomaly_rate=1.5)
    assert injector_high.anomaly_rate == 1.0


def test_inject_null_fields(clean_order_dict):
    """Verifies that null fields mutator sets at least one target attribute to None."""
    injector = AnomalyInjector()
    # Force mutation multiple times on copies to cover random targets
    mutated = False
    for _ in range(20):
        order_copy = copy.deepcopy(clean_order_dict)
        injector.inject_null_fields(order_copy)
        customer = order_copy.get("customer") or {}
        if (
            customer.get("email") is None
            or customer.get("postcode") is None
            or customer.get("address") is None
            or order_copy.get("payment_method") is None
        ):
            mutated = True
            break
    assert mutated, "Expected at least one null field to be injected"


def test_inject_math_mismatch(clean_order_dict):
    """Verifies that math mismatch mutator tampers with totals."""
    injector = AnomalyInjector()
    original_total = clean_order_dict["total"]
    mutated = False
    for _ in range(20):
        order_copy = copy.deepcopy(clean_order_dict)
        injector.inject_math_mismatch(order_copy)
        if order_copy["total"] != original_total:
            mutated = True
            break
        # Or line item total altered
        items = order_copy.get("line_items", [])
        if (
            items
            and items[0].get("total") != clean_order_dict["line_items"][0]["total"]
        ):
            mutated = True
            break
    assert mutated, "Expected order or line item total math mismatch"


def test_inject_invalid_numbers(clean_order_dict):
    """Verifies invalid numeric mutator produces zero quantity, negative price, or negative total."""
    injector = AnomalyInjector()
    mutated = False
    for _ in range(20):
        order_copy = copy.deepcopy(clean_order_dict)
        injector.inject_invalid_numbers(order_copy)
        line_items = order_copy.get("line_items", [])
        if (
            order_copy.get("total") == "-150.00"
            or (line_items and line_items[0].get("quantity") == 0)
            or (line_items and line_items[0].get("unit_price") == "-49.99")
        ):
            mutated = True
            break
    assert mutated, "Expected negative price, zero quantity, or negative total"


def test_inject_corrupted_dates(clean_order_dict):
    """Verifies corrupted dates mutator creates invalid format or temporal sequence violations."""
    injector = AnomalyInjector()
    mutated = False
    for _ in range(20):
        order_copy = copy.deepcopy(clean_order_dict)
        injector.inject_corrupted_dates(order_copy)
        if (
            order_copy.get("date_created") == "2026-13-45T99:99:99"
            or order_copy.get("date_modified_gmt") == "2020-01-01T00:00:00+00:00"
        ):
            mutated = True
            break
    assert mutated, "Expected corrupted date timestamp"


def test_inject_malformed_formats(clean_order_dict):
    """Verifies malformed formats mutator inserts broken email or string into total."""
    injector = AnomalyInjector()
    mutated = False
    for _ in range(20):
        order_copy = copy.deepcopy(clean_order_dict)
        injector.inject_malformed_formats(order_copy)
        customer = order_copy.get("customer") or {}
        if (
            customer.get("email") == "broken.user@@invalid_domain"
            or order_copy.get("total") == "N/A"
        ):
            mutated = True
            break
    assert mutated, "Expected malformed email or N/A total"


def test_inject_duplicates():
    """Verifies that duplicate orders can be created in a batch."""
    injector = AnomalyInjector(
        anomaly_rate=1.0, enabled_anomalies=[ANOMALY_DUPLICATE_ORDERS]
    )
    orders = [{"id": 1001, "total": "50.00"}, {"id": 1002, "total": "75.00"}]
    result = injector.inject(orders)
    assert len(result) == 2, "Expected batch size preserved"
    ids = [o["id"] for o in result]
    assert len(ids) != len(set(ids)), "Expected duplicate IDs in batch"


def test_clean_mode_guarantees_valid_pydantic_orders():
    """Verifies that setting enable_anomalies=False ensures 100% valid Pydantic models."""
    simulator = WooCommerceDataSimulator(enable_anomalies=False)
    orders = simulator.generate_orders_batch(count=30, enable_anomalies=False)

    for raw in orders:
        # Pydantic validation must succeed without exceptions
        validated = Order.model_validate(raw)
        assert validated.id > 0
        assert float(validated.total) >= 0.0
        assert len(validated.line_items) > 0


def test_simulator_anomalies_active_by_default():
    """Verifies that simulator enables anomalies by default and generates records."""
    simulator = WooCommerceDataSimulator(anomaly_rate=0.5)
    assert simulator.enable_anomalies is True
    orders = simulator.generate_orders_batch(count=20)
    assert len(orders) >= 20


def test_cli_parser_options():
    """Validates CLI arguments parsing for clean and chaos options."""
    parser = build_parser()

    args_default = parser.parse_args(["generate", "--count", "25"])
    assert args_default.count == 25
    assert args_default.clean is False
    assert args_default.chaos_rate is None

    args_clean = parser.parse_args(["generate", "--count", "10", "--clean"])
    assert args_clean.clean is True

    args_custom = parser.parse_args(
        [
            "generate",
            "--chaos-rate",
            "0.4",
            "--anomalies",
            "null_fields,duplicate_orders",
        ]
    )
    assert args_custom.chaos_rate == 0.4
    assert args_custom.anomalies == "null_fields,duplicate_orders"


def test_cli_dry_run_execution(capsys):
    """Verifies CLI dry run prints JSON sample and exits cleanly."""
    parser = build_parser()
    args = parser.parse_args(["generate", "--count", "3", "--dry-run", "--clean"])
    status = handle_generate(args)
    assert status == 0

    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out
    assert "Generated 3 orders" in captured.out
