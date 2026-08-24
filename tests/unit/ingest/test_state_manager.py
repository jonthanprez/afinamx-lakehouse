"""Unit tests for the WooCommerceStateManager class.

Validates state persistence, incremental cursor watermarking,
atomic file operations, Circuit Breaker failure counters, and corruption guards.
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from src.ingest.woocommerce.state_manager import WooCommerceStateManager


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary file path for state persistence."""
    return tmp_path / "metadata" / "woocommerce" / "state.json"


@pytest.fixture
def state_manager(state_file: Path) -> WooCommerceStateManager:
    """Fixture providing a WooCommerceStateManager initialized with an isolated state file."""
    return WooCommerceStateManager(state_file_path=state_file)


def test_load_state_cold_start_initializes_default_schema(
    state_manager: WooCommerceStateManager, state_file: Path
) -> None:
    """Verify load_state returns standard initial schema when state file does not exist."""
    assert not state_file.exists()

    state = state_manager.load_state()

    assert state["dataset_name"] == "woocommerce"
    assert state["last_order_id"] == 1000
    assert state["last_updated_at"] is None
    assert state["last_execution_status"] == "INITIALIZED"
    assert state["consecutive_failures"] == 0
    assert state["last_error_message"] is None
    assert "last_execution_timestamp" in state


def test_load_state_reads_existing_persisted_state(
    state_manager: WooCommerceStateManager, state_file: Path
) -> None:
    """Verify load_state accurately deserializes an existing state file from disk."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    persisted_data: Dict[str, Any] = {
        "dataset_name": "woocommerce",
        "last_order_id": 2500,
        "last_updated_at": "2026-08-24T12:00:00+00:00",
        "last_execution_timestamp": "2026-08-24T12:05:00+00:00",
        "last_execution_status": "SUCCESS",
        "consecutive_failures": 0,
        "last_error_message": None,
    }
    state_file.write_text(json.dumps(persisted_data), encoding="utf-8")

    state = state_manager.load_state()

    assert state == persisted_data
    assert state["last_order_id"] == 2500


def test_load_state_raises_runtime_error_on_corrupted_file(
    state_manager: WooCommerceStateManager, state_file: Path
) -> None:
    """Verify load_state halts execution if state file is corrupted to prevent cursor resets."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{corrupted_json_payload: invalid...", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Corrupted ingestion state file"):
        state_manager.load_state()


def test_update_state_advances_cursor_and_resets_failures(
    state_manager: WooCommerceStateManager, state_file: Path
) -> None:
    """Verify update_state advances watermark and resets failure counter to zero."""
    # Simulate an earlier failure state
    state_manager.register_failure("Temporary 503 error")
    failed_state = state_manager.load_state()
    assert failed_state["consecutive_failures"] == 1

    # Perform successful state update
    updated_state = state_manager.update_state(
        last_order_id=1050,
        last_updated_at="2026-08-24T15:00:00+00:00",
        status="SUCCESS",
    )

    # 1. Validate returned state
    assert updated_state["last_order_id"] == 1050
    assert updated_state["last_updated_at"] == "2026-08-24T15:00:00+00:00"
    assert updated_state["last_execution_status"] == "SUCCESS"
    assert updated_state["consecutive_failures"] == 0
    assert updated_state["last_error_message"] is None

    # 2. Validate atomic persistence to physical disk
    assert state_file.exists()
    disk_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert disk_data["last_order_id"] == 1050
    assert disk_data["consecutive_failures"] == 0


def test_update_state_enforces_monotonic_cursor_advancement(
    state_manager: WooCommerceStateManager,
) -> None:
    """Verify update_state rejects backwards cursor updates to guarantee idempotency."""
    state_manager.update_state(last_order_id=2000)

    # Attempt to regress watermark to a lower ID
    regressed_state = state_manager.update_state(last_order_id=1500)

    # State must retain higher cursor id (2000)
    assert regressed_state["last_order_id"] == 2000


def test_register_failure_increments_consecutive_failures(
    state_manager: WooCommerceStateManager,
) -> None:
    """Verify register_failure increments failure counter for Circuit Breaker tracking."""
    assert state_manager.load_state()["consecutive_failures"] == 0

    count_1 = state_manager.register_failure("API Timeout on attempt 1")
    assert count_1 == 1
    state_1 = state_manager.load_state()
    assert state_1["consecutive_failures"] == 1
    assert state_1["last_execution_status"] == "FAILED"
    assert state_1["last_error_message"] == "API Timeout on attempt 1"

    count_2 = state_manager.register_failure("API Rate Limit 429")
    assert count_2 == 2
    state_2 = state_manager.load_state()
    assert state_2["consecutive_failures"] == 2
    assert state_2["last_error_message"] == "API Rate Limit 429"


def test_save_state_raises_runtime_error_on_io_failure(
    state_manager: WooCommerceStateManager,
) -> None:
    """Verify I/O errors during state persistence raise custom RuntimeError."""
    with patch("builtins.open", side_effect=OSError("Disk write permission denied")):
        with pytest.raises(
            RuntimeError, match="I/O error updating ingestion checkpoint"
        ):
            state_manager.update_state(last_order_id=1010)
