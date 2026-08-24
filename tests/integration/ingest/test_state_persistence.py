"""Integration tests for State Persistence, Recovery, and Circuit Breaker lifecycle.

Validates state checkpoint integrity across pipeline failures, watermark immutability,
Circuit Breaker tripping after consecutive failures, and recovery procedures.
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from src.ingest.exceptions import (
    StorageError,
    WooCommerceCircuitBreakerError,
)
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.woocommerce.api_client import WooCommerceAPIClient
from src.ingest.woocommerce.state_manager import WooCommerceStateManager


@pytest.fixture
def state_pipeline_env(tmp_path: Path) -> Dict[str, Any]:
    """Provides isolated filesystem and real components for state lifecycle testing."""
    data_dir = tmp_path / "data"
    bronze_dir = data_dir / "bronze"
    metadata_dir = data_dir / "metadata" / "woocommerce"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    bronze_dir.mkdir(parents=True, exist_ok=True)

    state_file = metadata_dir / "state.json"
    customers_file = metadata_dir / "customers.json"

    state_manager = WooCommerceStateManager(state_file_path=state_file)
    storage_writer = LocalStorageWriter(base_dir=bronze_dir)

    client = WooCommerceAPIClient(
        use_simulator=True,
        storage_writer=storage_writer,
        state_manager=state_manager,
        max_circuit_failures=5,
    )
    if client.simulator:
        client.simulator.state_file = state_file
        client.simulator.customers_file = customers_file

    return {
        "client": client,
        "state_manager": state_manager,
        "storage_writer": storage_writer,
        "bronze_dir": bronze_dir,
        "state_file": state_file,
    }


# -----------------------------------------------------------------------------
# 1. STORAGE FAILURE AND STATE RECOVERY INTEGRATION TEST
# -----------------------------------------------------------------------------


def test_storage_failure_preserves_watermark_and_recovers(
    state_pipeline_env: Dict[str, Any],
) -> None:
    """Verify state checkpoint does not advance on storage error, and recovers on subsequent attempt."""
    client: WooCommerceAPIClient = state_pipeline_env["client"]
    state_file: Path = state_pipeline_env["state_file"]
    storage_writer: LocalStorageWriter = state_pipeline_env["storage_writer"]

    # Initialize successful cold start (1001 to 1010)
    result_1 = client.extract_and_load(batch_size=10)
    assert result_1["last_order_id"] == 1010

    # Simulate physical storage failure on second batch
    with patch.object(
        storage_writer, "write", side_effect=StorageError("Disk write I/O error")
    ):
        with pytest.raises(StorageError, match="Failed to persist payload"):
            client.extract_and_load(batch_size=10)

    # 1. Verify watermark was NOT advanced on disk (must remain 1010)
    state_after_failure = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_after_failure["last_order_id"] == 1010
    assert state_after_failure["consecutive_failures"] == 1
    assert state_after_failure["last_execution_status"] == "FAILED"

    # 2. Re-run after fixing storage error (Recovery phase)
    result_recovered = client.extract_and_load(batch_size=10)
    assert result_recovered["status"] == "SUCCESS"
    assert result_recovered["last_order_id"] == 1020
    assert result_recovered["records_ingested"] == 10

    # 3. Verify failure counter was reset to 0
    state_after_recovery = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_after_recovery["last_order_id"] == 1020
    assert state_after_recovery["consecutive_failures"] == 0
    assert state_after_recovery["last_execution_status"] == "SUCCESS"


# -----------------------------------------------------------------------------
# 2. CIRCUIT BREAKER TRIPPING AND MANUAL RESET END-TO-END TEST
# -----------------------------------------------------------------------------


def test_circuit_breaker_tripping_and_reset_workflow(
    state_pipeline_env: Dict[str, Any],
) -> None:
    """Verify Circuit Breaker trips after 5 failures and resumes operation after state reset."""
    client: WooCommerceAPIClient = state_pipeline_env["client"]
    state_manager: WooCommerceStateManager = state_pipeline_env["state_manager"]
    storage_writer: LocalStorageWriter = state_pipeline_env["storage_writer"]

    # 1. Trigger 5 consecutive failures
    with patch.object(
        storage_writer, "write", side_effect=StorageError("Simulated outage")
    ):
        for failure_num in range(1, 6):
            with pytest.raises(StorageError):
                client.extract_and_load(batch_size=5)

    assert state_manager.load_state()["consecutive_failures"] == 5

    # 2. Attempt 6th execution -> Circuit Breaker must trip and abort immediately
    with pytest.raises(
        WooCommerceCircuitBreakerError,
        match="Circuit breaker open due to 5 historical failures",
    ):
        client.extract_and_load(batch_size=5)

    # 3. Resolve incident / Reset state checkpoint
    current_state = state_manager.load_state()
    state_manager.update_state(
        last_order_id=current_state["last_order_id"],
        status="RESET_AFTER_INCIDENT",
    )
    assert state_manager.load_state()["consecutive_failures"] == 0

    # 4. Pipeline resumes normal operation
    resume_result = client.extract_and_load(batch_size=5)
    assert resume_result["status"] == "SUCCESS"
    assert resume_result["records_ingested"] == 5


# -----------------------------------------------------------------------------
# 3. CORRUPTED STATE GUARD TEST
# -----------------------------------------------------------------------------


def test_corrupted_state_file_halts_pipeline_to_prevent_cursor_reset(
    state_pipeline_env: Dict[str, Any],
) -> None:
    """Verify pipeline refuses to execute if state.json is corrupted to prevent reingesting all data."""
    client: WooCommerceAPIClient = state_pipeline_env["client"]
    state_file: Path = state_pipeline_env["state_file"]

    # Write corrupted data to state file
    state_file.write_text("{malformed_json: true, ...", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Corrupted ingestion state file"):
        client.extract_and_load(batch_size=10)
