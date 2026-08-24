"""Unit tests for the LocalStorageWriter class.

Validates Medallion architecture directory structures (Hive partitioning),
atomic file I/O operations, metadata envelope, and JSON serialization.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

import pytest

from src.ingest.storage.local_writer import LocalStorageWriter


@pytest.fixture
def local_writer(tmp_path: Path) -> LocalStorageWriter:
    """Fixture providing a LocalStorageWriter injected with a temporary directory."""
    return LocalStorageWriter(base_dir=str(tmp_path / "bronze"))


def test_local_writer_creates_hive_partitioned_paths(
    local_writer: LocalStorageWriter,
) -> None:
    """Verify the writer constructs correct Hive-style paths with zero-padded months."""
    test_data: List[Dict[str, str]] = [{"id": "1", "status": "active"}]
    exec_date = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

    file_path_str = local_writer.write(
        payload=test_data,
        dataset_name="woocommerce",
        filename="batch_01.json",
        execution_date=exec_date,
    )
    file_path = Path(file_path_str)

    # 1. Verify physical existence on disk
    assert file_path.exists()
    assert file_path.is_file()

    # 2. Verify strict Medallion / Hive partition structure (year=YYYY/month=MM)
    normalized_path = file_path.as_posix()
    expected_suffix = "bronze/woocommerce/year=2026/month=08/batch_01.json"

    assert (
        expected_suffix in normalized_path
    ), f"Expected {expected_suffix} in {normalized_path}"


def test_local_writer_persists_valid_json_with_metadata_envelope(
    local_writer: LocalStorageWriter,
) -> None:
    """Verify data is saved with operational metadata envelope and UTF-8 encoding."""
    test_data: List[Dict[str, Union[int, float]]] = [{"order_id": 999, "total": 150.50}]
    exec_date = datetime(2026, 11, 5, tzinfo=timezone.utc)

    file_path_str = local_writer.write(
        payload=test_data,
        dataset_name="woocommerce",
        filename="orders.json",
        execution_date=exec_date,
    )
    file_path = Path(file_path_str)

    # Verify content integrity and operational envelope
    with open(file_path, "r", encoding="utf-8") as f:
        saved_payload = json.load(f)

    assert "_metadata" in saved_payload
    assert saved_payload["_metadata"]["dataset_name"] == "woocommerce"
    assert saved_payload["_metadata"]["execution_date"] == exec_date.isoformat()
    assert saved_payload["data"] == test_data


def test_local_writer_handles_dictionary_payload(
    local_writer: LocalStorageWriter,
) -> None:
    """Verify dictionary payloads are persisted correctly."""
    test_data: Dict[str, Any] = {"order_id": 1000, "total": 200.00}
    exec_date = datetime(2026, 1, 20, tzinfo=timezone.utc)

    file_path_str = local_writer.write(
        payload=test_data,
        dataset_name="woocommerce",
        filename="single_order.json",
        execution_date=exec_date,
    )
    file_path = Path(file_path_str)

    with open(file_path, "r", encoding="utf-8") as f:
        saved_payload = json.load(f)

    assert saved_payload["data"] == test_data
