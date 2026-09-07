"""Unit tests for Pydantic data models in the ingestion layer.

Validates schema constraints, field boundaries, type coercions,
and resilience against unexpected fields (extra="ignore").
"""

import pytest
from pydantic import ValidationError

from src.ingest.models import (
    Customer,
    LineItem,
    Order,
    Product,
    SimulatorState,
)


# -----------------------------------------------------------------------------
# 1. PRODUCT MODEL TESTS
# -----------------------------------------------------------------------------


def test_product_valid_creation() -> None:
    """Verify a valid product model is successfully created and properties match."""
    product = Product(
        id=101,
        sku="AFN-FIL-101",
        name="Filtro de Aceite",
        brand="Fram",
        category="Filtración",
        price=250.0,
        cost=110.0,
    )
    assert product.id == 101
    assert product.sku == "AFN-FIL-101"
    assert product.price == 250.0
    assert product.cost == 110.0


def test_product_negative_price_or_cost_fails() -> None:
    """Verify negative price or cost triggers a validation error."""
    with pytest.raises(ValidationError):
        Product(
            id=101,
            sku="AFN-FIL-101",
            name="Filtro",
            brand="Fram",
            category="Filtración",
            price=-10.0,
            cost=50.0,
        )

    with pytest.raises(ValidationError):
        Product(
            id=101,
            sku="AFN-FIL-101",
            name="Filtro",
            brand="Fram",
            category="Filtración",
            price=100.0,
            cost=-5.0,
        )


def test_product_invalid_id_fails() -> None:
    """Verify zero or negative product ID triggers a validation error."""
    with pytest.raises(ValidationError):
        Product(
            id=0,
            sku="AFN-FIL-101",
            name="Filtro",
            brand="Fram",
            category="Filtración",
            price=100.0,
            cost=50.0,
        )


def test_product_extra_fields_ignored() -> None:
    """Verify unrecognized fields are ignored without raising exceptions."""
    raw_data = {
        "id": 101,
        "sku": "AFN-FIL-101",
        "name": "Filtro",
        "brand": "Fram",
        "category": "Filtración",
        "price": 100.0,
        "cost": 50.0,
        "unexpected_future_api_field": "some_value",
    }
    product = Product.model_validate(raw_data)
    assert not hasattr(product, "unexpected_future_api_field")


# -----------------------------------------------------------------------------
# 2. CUSTOMER MODEL TESTS
# -----------------------------------------------------------------------------


def test_customer_valid_creation(mock_customer: Customer) -> None:
    """Verify customer fixture matches schema expectations."""
    assert mock_customer.id == 1
    assert mock_customer.country == "MX"
    assert mock_customer.first_name == "Juan"


def test_customer_whitespace_stripping() -> None:
    """Verify whitespace is automatically stripped from string fields."""
    customer = Customer(
        id=2,
        first_name="  María  ",
        last_name="  González  ",
        email="  maria@example.com  ",
        address="Calle 5",
        city="Guadalajara",
        state="JAL",
        postcode="44100",
    )
    assert customer.first_name == "María"
    assert customer.last_name == "González"
    assert customer.email == "maria@example.com"


# -----------------------------------------------------------------------------
# 3. LINEITEM MODEL TESTS
# -----------------------------------------------------------------------------


def test_line_item_valid_creation(mock_line_item: LineItem) -> None:
    """Verify line item fixture creation and property access."""
    assert mock_line_item.product_id == 101
    assert mock_line_item.quantity == 2
    assert mock_line_item.unit_price == "250.0"
    assert mock_line_item.total == "500.0"


def test_line_item_zero_quantity_fails() -> None:
    """Verify zero quantity line item triggers validation error."""
    with pytest.raises(ValidationError):
        LineItem(
            product_id=101,
            sku="AFN-FIL-101",
            name="Filtro",
            brand="Fram",
            category="Filtración",
            quantity=0,
            unit_price="250.0",
            total="0.0",
        )


# -----------------------------------------------------------------------------
# 4. ORDER MODEL TESTS
# -----------------------------------------------------------------------------


def test_order_valid_creation(mock_order: Order) -> None:
    """Verify complete order hierarchy validation and serialization."""
    assert mock_order.id == 1001
    assert mock_order.status == "completed"
    assert mock_order.currency == "MXN"
    assert len(mock_order.line_items) == 1
    assert mock_order.customer.first_name == "Juan"

    dumped = mock_order.model_dump()
    assert isinstance(dumped, dict)
    assert dumped["id"] == 1001
    assert isinstance(dumped["customer"], dict)
    assert isinstance(dumped["line_items"], list)


def test_order_model_dump_json(mock_order: Order) -> None:
    """Verify JSON string serialization of order model."""
    json_str = mock_order.model_dump_json()
    assert '"id":1001' in json_str or '"id": 1001' in json_str
    assert "completed" in json_str


# -----------------------------------------------------------------------------
# 5. SIMULATOR STATE MODEL TESTS
# -----------------------------------------------------------------------------


def test_simulator_state_valid_creation() -> None:
    """Verify SimulatorState creation and default last_order_id."""
    state = SimulatorState(updated_at="2026-08-24T15:00:00+00:00")
    assert state.last_order_id == 1000
    assert state.updated_at == "2026-08-24T15:00:00+00:00"


def test_simulator_state_custom_order_id() -> None:
    """Verify SimulatorState with custom incremental order ID."""
    state = SimulatorState(last_order_id=1500, updated_at="2026-08-24T16:00:00+00:00")
    assert state.last_order_id == 1500
