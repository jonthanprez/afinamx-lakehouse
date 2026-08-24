"""Unit tests for WooCommerceAPIClient.

Validates the Double Switch (Simulator vs Real API), Circuit Breaker fail-fast guard,
audit envelope construction, incremental state management, and error handling.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.ingest.exceptions import (
    StorageError,
    WooCommerceAPIError,
    WooCommerceCircuitBreakerError,
)
from src.ingest.storage.base import BaseStorageWriter
from src.ingest.woocommerce.api_client import WooCommerceAPIClient
from src.ingest.woocommerce.state_manager import WooCommerceStateManager


@pytest.fixture
def mock_storage_writer() -> MagicMock:
    """Fixture providing a mocked BaseStorageWriter."""
    writer = MagicMock(spec=BaseStorageWriter)
    writer.write.return_value = "/mock/path/bronze/woocommerce/batch_orders.json"
    return writer


@pytest.fixture
def mock_state_manager() -> MagicMock:
    """Fixture providing a mocked WooCommerceStateManager."""
    manager = MagicMock(spec=WooCommerceStateManager)
    manager.load_state.return_value = {
        "dataset_name": "woocommerce",
        "last_order_id": 1000,
        "last_updated_at": "2026-08-24T12:00:00+00:00",
        "last_execution_status": "SUCCESS",
        "consecutive_failures": 0,
        "last_error_message": None,
    }
    manager.state_file_path = "/mock/path/metadata/woocommerce/state.json"
    return manager


# -----------------------------------------------------------------------------
# 1. SIMULATOR MODE TESTS (DEV)
# -----------------------------------------------------------------------------


def test_extract_and_load_simulator_success(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify incremental extraction, envelope creation, persistence and state checkpoint in simulator mode."""
    client = WooCommerceAPIClient(
        use_simulator=True,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
    )
    exec_date = datetime(2026, 8, 24, 15, 0, 0, tzinfo=timezone.utc)

    result = client.extract_and_load(
        batch_size=5,
        execution_id="exec_test_01",
        execution_date=exec_date,
    )

    # 1. Validate return summary
    assert result["status"] == "SUCCESS"
    assert result["records_ingested"] == 5
    assert result["execution_id"] == "exec_test_01"
    assert result["last_order_id"] == 1005

    # 2. Validate StorageWriter call with audit envelope
    mock_storage_writer.write.assert_called_once()
    call_kwargs = mock_storage_writer.write.call_args.kwargs
    envelope = call_kwargs["payload"]

    assert envelope["metadata"]["source_system"] == "woocommerce"
    assert envelope["metadata"]["record_count"] == 5
    assert envelope["metadata"]["extracted_range"]["start_order_id"] == 1001
    assert envelope["metadata"]["extracted_range"]["end_order_id"] == 1005
    assert len(envelope["payload"]) == 5

    # 3. Validate state advancement
    mock_state_manager.update_state.assert_called_once()
    state_call_kwargs = mock_state_manager.update_state.call_args.kwargs
    assert state_call_kwargs["last_order_id"] == 1005
    assert state_call_kwargs["status"] == "SUCCESS"


# -----------------------------------------------------------------------------
# 2. REAL API MODE TESTS (PROD)
# -----------------------------------------------------------------------------


def test_extract_and_load_real_api_success(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify successful extraction from external REST API and pagination parameter passing."""
    api_orders_payload: List[Dict[str, Any]] = [
        {
            "id": 1001,
            "status": "processing",
            "date_created": "2026-08-24T12:00:00",
            "date_modified_gmt": "2026-08-24T12:00:00Z",
            "total": "450.00",
        },
        {
            "id": 1002,
            "status": "completed",
            "date_created": "2026-08-24T12:05:00",
            "date_modified_gmt": "2026-08-24T12:05:00Z",
            "total": "990.00",
        },
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = api_orders_payload
    mock_response.raise_for_status.return_value = None

    client = WooCommerceAPIClient(
        use_simulator=False,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
    )

    with patch.object(
        client.http_session, "get", return_value=mock_response
    ) as mock_get:
        result = client.extract_and_load(batch_size=50)

        mock_get.assert_called_once()
        get_params = mock_get.call_args.kwargs["params"]
        assert get_params["per_page"] == 50
        assert get_params["after"] == "2026-08-24T12:00:00+00:00"

        assert result["status"] == "SUCCESS"
        assert result["records_ingested"] == 2
        assert result["last_order_id"] == 1002


def test_extract_and_load_empty_batch_skips_persistence(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify empty result from API returns SKIPPED without modifying storage or advancing state."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None

    client = WooCommerceAPIClient(
        use_simulator=False,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
    )

    with patch.object(client.http_session, "get", return_value=mock_response):
        result = client.extract_and_load(batch_size=10)

        assert result["status"] == "SKIPPED"
        assert result["records_ingested"] == 0
        mock_storage_writer.write.assert_not_called()
        mock_state_manager.update_state.assert_not_called()


# -----------------------------------------------------------------------------
# 3. CIRCUIT BREAKER & ERROR HANDLING TESTS
# -----------------------------------------------------------------------------


def test_extract_and_load_circuit_breaker_open_halts_execution(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify Circuit Breaker fail-fast guard aborts immediately when consecutive_failures exceeds threshold."""
    mock_state_manager.load_state.return_value = {
        "dataset_name": "woocommerce",
        "last_order_id": 1000,
        "consecutive_failures": 5,  # Equal to max_circuit_failures
    }

    client = WooCommerceAPIClient(
        use_simulator=False,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
        max_circuit_failures=5,
    )

    with pytest.raises(WooCommerceCircuitBreakerError, match="Circuit breaker open"):
        client.extract_and_load()

    mock_storage_writer.write.assert_not_called()


def test_extract_and_load_http_error_registers_failure(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify HTTP/Network exceptions register failure in state manager and raise WooCommerceAPIError."""
    client = WooCommerceAPIClient(
        use_simulator=False,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
    )

    with patch.object(
        client.http_session,
        "get",
        side_effect=requests.exceptions.ConnectionError("Connection refused"),
    ):
        with pytest.raises(WooCommerceAPIError, match="HTTP request failed"):
            client.extract_and_load()

        mock_state_manager.register_failure.assert_called_once()
        mock_storage_writer.write.assert_not_called()


def test_extract_and_load_storage_failure_registers_failure(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify storage persistence failure registers failure counter and raises StorageError."""
    mock_storage_writer.write.side_effect = Exception("Disk full")

    client = WooCommerceAPIClient(
        use_simulator=True,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
    )

    with pytest.raises(
        StorageError, match="Failed to persist payload to bronze storage"
    ):
        client.extract_and_load(batch_size=3)

    mock_state_manager.register_failure.assert_called_once()
    mock_state_manager.update_state.assert_not_called()


def test_extract_and_load_malformed_api_response_raises_api_error(
    mock_storage_writer: MagicMock,
    mock_state_manager: MagicMock,
) -> None:
    """Verify non-list JSON payload from API raises WooCommerceAPIError."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": "rest_no_route",
        "message": "No route found",
    }
    mock_response.raise_for_status.return_value = None

    client = WooCommerceAPIClient(
        use_simulator=False,
        storage_writer=mock_storage_writer,
        state_manager=mock_state_manager,
    )

    with patch.object(client.http_session, "get", return_value=mock_response):
        with pytest.raises(WooCommerceAPIError, match="Unexpected API response format"):
            client.extract_and_load()

        mock_state_manager.register_failure.assert_called_once()
