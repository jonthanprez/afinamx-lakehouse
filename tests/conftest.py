"""Global pytest fixtures for the Data Lakehouse test suite.

Provides isolated environment setups, filesystem redirection via temporary paths,
AWS mocking configuration, and standard mock domain payloads.
"""

from typing import Any, Dict, Generator
from unittest.mock import patch
import pytest

from src.ingest.models import Customer, LineItem, Order


# -----------------------------------------------------------------------------
# 1. ENVIRONMENT & FILESYSTEM FIXTURES
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_testing_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce dev mode and mock AWS environment variables globally."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("S3_BUCKET_NAME", "test-afinamx-lakehouse-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing_access_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing_secret_key")


@pytest.fixture
def mock_lakehouse_dirs(
    tmp_path: pytest.TempPathFactory,
) -> Generator[Dict[str, Any], None, None]:
    """Redirect Lakehouse storage and metadata paths to an isolated temporary directory.

    Prevents unit/integration tests from writing to the real local `./data/` directory.
    """
    tmp_data_dir = tmp_path / "data"
    tmp_bronze_dir = tmp_data_dir / "bronze"
    tmp_silver_dir = tmp_data_dir / "silver"
    tmp_gold_dir = tmp_data_dir / "gold"
    tmp_metadata_dir = tmp_data_dir / "metadata"
    tmp_woo_metadata_dir = tmp_metadata_dir / "woocommerce"

    # Ensure mock directory structure exists
    for directory in [
        tmp_data_dir,
        tmp_bronze_dir,
        tmp_silver_dir,
        tmp_gold_dir,
        tmp_metadata_dir,
        tmp_woo_metadata_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    with (
        patch("src.ingest.config.LOCAL_DATA_DIR", tmp_data_dir),
        patch("src.ingest.config.BRONZE_DIR", tmp_bronze_dir),
        patch("src.ingest.config.SILVER_DIR", tmp_silver_dir),
        patch("src.ingest.config.GOLD_DIR", tmp_gold_dir),
        patch("src.ingest.config.METADATA_DIR", tmp_metadata_dir),
        patch("src.ingest.config.WOOCOMMERCE_METADATA_DIR", tmp_woo_metadata_dir),
        patch(
            "src.ingest.config.WOOCOMMERCE_STATE_FILE",
            tmp_woo_metadata_dir / "state.json",
        ),
        patch(
            "src.ingest.config.WOOCOMMERCE_CUSTOMERS_FILE",
            tmp_woo_metadata_dir / "customers.json",
        ),
    ):
        yield {
            "root": tmp_data_dir,
            "bronze": tmp_bronze_dir,
            "silver": tmp_silver_dir,
            "gold": tmp_gold_dir,
            "metadata": tmp_metadata_dir,
            "woo_metadata": tmp_woo_metadata_dir,
            "woo_state_file": tmp_woo_metadata_dir / "state.json",
            "woo_customers_file": tmp_woo_metadata_dir / "customers.json",
        }


# -----------------------------------------------------------------------------
# 2. DOMAIN MOCK PAYLOAD FIXTURES (WOOCOMMERCE)
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_customer() -> Customer:
    """Return a standard WooCommerce Customer dictionary conforming to models.Customer."""
    return {
        "id": 1,
        "first_name": "Juan",
        "last_name": "Pérez",
        "email": "juan.perez@example.com",
        "address": "Av. Reforma 123",
        "city": "Ciudad de México",
        "state": "CDMX",
        "postcode": "01000",
        "country": "MX",
    }


@pytest.fixture
def mock_line_item() -> LineItem:
    """Return a standard WooCommerce LineItem dictionary conforming to models.LineItem."""
    return {
        "product_id": 101,
        "sku": "AFN-FIL-101",
        "name": "Filtro de Aceite Sintético Premium",
        "brand": "Fram",
        "category": "Filtración",
        "quantity": 2,
        "unit_price": "250.0",
        "total": "500.0",
    }


@pytest.fixture
def mock_order(mock_customer: Customer, mock_line_item: LineItem) -> Order:
    """Return a complete WooCommerce Order dictionary conforming to models.Order."""
    return {
        "id": 1001,
        "status": "completed",
        "currency": "MXN",
        "date_created": "2026-08-11T10:00:00+00:00",
        "total": "500.0",
        "payment_method": "credit_card",
        "customer": mock_customer,
        "line_items": [mock_line_item],
    }
