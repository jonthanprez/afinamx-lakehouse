"""Integration tests for the Simulator-to-Storage Bronze pipeline.

Validates end-to-end data flow: DataSimulator -> APIClient -> LocalStorageWriter,
verifying Hive partitioning, customer pool persistence, operational metadata,
and sequential multi-batch execution on an isolated local filesystem.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.woocommerce.api_client import WooCommerceAPIClient
from src.ingest.woocommerce.state_manager import WooCommerceStateManager


@pytest.fixture
def isolated_pipeline_env(tmp_path: Path) -> Dict[str, Any]:
    """Sets up an isolated directory structure and real pipeline components."""
    data_dir = tmp_path / "data"
    bronze_dir = data_dir / "bronze"
    metadata_dir = data_dir / "metadata" / "woocommerce"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    bronze_dir.mkdir(parents=True, exist_ok=True)

    state_file = metadata_dir / "state.json"
    customers_file = metadata_dir / "customers.json"

    # Real concrete components pointing to temporary directory
    state_manager = WooCommerceStateManager(state_file_path=state_file)
    storage_writer = LocalStorageWriter(base_dir=bronze_dir)

    client = WooCommerceAPIClient(
        use_simulator=True,
        storage_writer=storage_writer,
        state_manager=state_manager,
    )
    # Point simulator state and customer paths to temp directory
    if client.simulator:
        client.simulator.state_file = state_file
        client.simulator.customers_file = customers_file

    return {
        "client": client,
        "state_manager": state_manager,
        "storage_writer": storage_writer,
        "bronze_dir": bronze_dir,
        "state_file": state_file,
        "customers_file": customers_file,
    }


# -----------------------------------------------------------------------------
# 1. COLD START END-TO-END TEST
# -----------------------------------------------------------------------------


def test_cold_start_pipeline_end_to_end(
    isolated_pipeline_env: Dict[str, Any],
) -> None:
    """Verify first pipeline run initializes metadata, extracts orders, and writes Bronze file."""
    client: WooCommerceAPIClient = isolated_pipeline_env["client"]
    bronze_dir: Path = isolated_pipeline_env["bronze_dir"]
    state_file: Path = isolated_pipeline_env["state_file"]
    customers_file: Path = isolated_pipeline_env["customers_file"]

    exec_date = datetime(2026, 8, 24, 15, 0, 0, tzinfo=timezone.utc)

    # 1. Execute extraction and load
    result = client.extract_and_load(
        batch_size=10,
        execution_id="cold_start_01",
        execution_date=exec_date,
    )

    # 2. Verify returned operational summary
    assert result["status"] == "SUCCESS"
    assert result["records_ingested"] == 10
    assert result["last_order_id"] == 1010
    assert result["execution_id"] == "cold_start_01"

    # 3. Verify state.json persistence and cursor advance
    assert state_file.exists()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["last_order_id"] == 1010
    assert state_data["last_execution_status"] == "SUCCESS"
    assert state_data["consecutive_failures"] == 0

    # 4. Verify customers.json pool initialization
    assert customers_file.exists()
    customers_pool = json.loads(customers_file.read_text(encoding="utf-8"))
    assert len(customers_pool) >= 50
    assert customers_pool[0]["country"] == "MX"

    # 5. Verify physical Hive partitioned file in Bronze layer
    expected_file = (
        bronze_dir
        / "woocommerce"
        / "year=2026"
        / "month=08"
        / "batch_orders_1001_to_1010.json"
    )
    assert expected_file.exists()
    assert expected_file.is_file()

    # 6. Verify JSON content and metadata envelope
    file_content = json.loads(expected_file.read_text(encoding="utf-8"))
    assert "_metadata" in file_content
    assert file_content["_metadata"]["dataset_name"] == "woocommerce"
    assert file_content["_metadata"]["execution_date"] == exec_date.isoformat()

    orders_payload = file_content["data"]["payload"]
    assert len(orders_payload) == 10
    assert orders_payload[0]["id"] == 1001
    assert orders_payload[-1]["id"] == 1010

    # Verify domain fields
    sample_order = orders_payload[0]
    assert "customer" in sample_order
    assert "line_items" in sample_order
    assert sample_order["currency"] == "MXN"
    assert len(sample_order["line_items"]) > 0


# -----------------------------------------------------------------------------
# 2. SEQUENTIAL MULTI-BATCH CONTINUITY TEST
# -----------------------------------------------------------------------------


def test_sequential_multi_batch_ingestion_continuity(
    isolated_pipeline_env: Dict[str, Any],
) -> None:
    """Verify consecutive batches maintain seamless cursor continuity without data gaps or overlaps."""
    client: WooCommerceAPIClient = isolated_pipeline_env["client"]
    bronze_dir: Path = isolated_pipeline_env["bronze_dir"]
    state_file: Path = isolated_pipeline_env["state_file"]

    exec_date = datetime(2026, 8, 24, 16, 0, 0, tzinfo=timezone.utc)

    # Batch 1: Ingest 10 orders (IDs: 1001 to 1010)
    result_batch_1 = client.extract_and_load(
        batch_size=10,
        execution_id="batch_01",
        execution_date=exec_date,
    )
    assert result_batch_1["last_order_id"] == 1010

    # Batch 2: Ingest next 15 orders (IDs: 1011 to 1025)
    result_batch_2 = client.extract_and_load(
        batch_size=15,
        execution_id="batch_02",
        execution_date=exec_date,
    )
    assert result_batch_2["last_order_id"] == 1025
    assert result_batch_2["records_ingested"] == 15

    # 1. Verify updated state file
    final_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_state["last_order_id"] == 1025

    # 2. Verify both physical batch files exist independently
    batch_1_path = (
        bronze_dir
        / "woocommerce"
        / "year=2026"
        / "month=08"
        / "batch_orders_1001_to_1010.json"
    )
    batch_2_path = (
        bronze_dir
        / "woocommerce"
        / "year=2026"
        / "month=08"
        / "batch_orders_1011_to_1025.json"
    )

    assert batch_1_path.exists()
    assert batch_2_path.exists()

    # 3. Verify IDs continuity (no gap, no duplicate)
    batch_1_orders = json.loads(batch_1_path.read_text(encoding="utf-8"))["data"][
        "payload"
    ]
    batch_2_orders = json.loads(batch_2_path.read_text(encoding="utf-8"))["data"][
        "payload"
    ]

    batch_1_ids = [o["id"] for o in batch_1_orders]
    batch_2_ids = [o["id"] for o in batch_2_orders]

    assert batch_1_ids == list(range(1001, 1011))
    assert batch_2_ids == list(range(1011, 1026))
    assert set(batch_1_ids).isdisjoint(set(batch_2_ids))


# -----------------------------------------------------------------------------
# 3. HIVE PARTITIONING ACROSS DIFFERENT EXECUTION DATES
# -----------------------------------------------------------------------------


def test_hive_partitioning_by_execution_date(
    isolated_pipeline_env: Dict[str, Any],
) -> None:
    """Verify files are routed to respective year=YYYY/month=MM partitions based on logical date."""
    client: WooCommerceAPIClient = isolated_pipeline_env["client"]
    bronze_dir: Path = isolated_pipeline_env["bronze_dir"]

    # Run 1: August 2026
    date_august = datetime(2026, 8, 31, 23, 59, 0, tzinfo=timezone.utc)
    client.extract_and_load(batch_size=5, execution_date=date_august)

    # Run 2: September 2026
    date_september = datetime(2026, 9, 1, 0, 1, 0, tzinfo=timezone.utc)
    client.extract_and_load(batch_size=5, execution_date=date_september)

    # Verify directory partitions
    august_partition = bronze_dir / "woocommerce" / "year=2026" / "month=08"
    september_partition = bronze_dir / "woocommerce" / "year=2026" / "month=09"

    assert august_partition.exists()
    assert september_partition.exists()

    august_files = list(august_partition.glob("*.json"))
    september_files = list(september_partition.glob("*.json"))

    assert len(august_files) == 1
    assert len(september_files) == 1
    assert "batch_orders_1001_to_1005.json" in august_files[0].name
    assert "batch_orders_1006_to_1010.json" in september_files[0].name
