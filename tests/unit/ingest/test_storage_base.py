"""Unit tests for the BaseStorageWriter abstract template class.

Validates:
1. Canonical Hive partition computation (monthly and daily granularity).
2. Canonical relative path construction and input validation.
3. Payload serialization engine (Pydantic models, dicts, strings, bytes, non-standard types).
4. Template Method orchestration and delegation to _persist.
"""

from datetime import datetime, timezone
import json
import pytest

from pydantic import BaseModel
from src.ingest.storage.base import BaseStorageWriter


class DummyModel(BaseModel):
    id: int
    name: str


class ConcreteStorageWriter(BaseStorageWriter):
    """Minimal concrete subclass for testing BaseStorageWriter template behavior."""

    def __init__(self) -> None:
        self.last_relative_path: str = ""
        self.last_data: bytes = b""

    def _persist(
        self,
        relative_path: str,
        data: bytes,
        dataset_name: str,
        execution_date: datetime,
    ) -> str:
        self.last_relative_path = relative_path
        self.last_data = data
        return f"mock://storage/{relative_path}"


def test_build_hive_partition_monthly_and_daily() -> None:
    dt = datetime(2026, 8, 15, 14, 30, tzinfo=timezone.utc)

    # Monthly default
    monthly = BaseStorageWriter.build_hive_partition(dt, include_day=False)
    assert monthly == "year=2026/month=08"

    # Daily granularity
    daily = BaseStorageWriter.build_hive_partition(dt, include_day=True)
    assert daily == "year=2026/month=08/day=15"


def test_build_hive_partition_invalid_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="must be a datetime instance"):
        BaseStorageWriter.build_hive_partition("2026-08-15")  # type: ignore[arg-type]


def test_build_relative_path_sanitizes_slashes_and_whitespace() -> None:
    dt = datetime(2026, 8, 15, tzinfo=timezone.utc)
    rel_path = BaseStorageWriter.build_relative_path(
        dataset_name=" /woocommerce/ ",
        filename=" orders.json ",
        execution_date=dt,
    )
    assert rel_path == "woocommerce/year=2026/month=08/orders.json"


def test_build_relative_path_empty_inputs_raise_value_error() -> None:
    dt = datetime(2026, 8, 15, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="dataset_name cannot be empty"):
        BaseStorageWriter.build_relative_path("", "file.json", dt)

    with pytest.raises(ValueError, match="filename cannot be empty"):
        BaseStorageWriter.build_relative_path("woocommerce", "   ", dt)


def test_serialize_payload_handles_pydantic_model() -> None:
    model = DummyModel(id=1, name="Test")
    serialized = BaseStorageWriter.serialize_payload(model)
    assert isinstance(serialized, bytes)
    parsed = json.loads(serialized.decode("utf-8"))
    assert parsed == {"id": 1, "name": "Test"}


def test_serialize_payload_compact_by_default() -> None:
    data = {"key1": "val1", "key2": "val2"}
    compact = BaseStorageWriter.serialize_payload(data)
    # Compact JSON has no newlines and minimal separators
    assert b"\n" not in compact
    assert b": " not in compact
    assert compact == b'{"key1":"val1","key2":"val2"}'


def test_serialize_payload_supports_indent() -> None:
    data = {"key": "val"}
    formatted = BaseStorageWriter.serialize_payload(data, indent=2)
    assert b"\n" in formatted


def test_serialize_payload_handles_non_standard_types_via_default_str() -> None:
    dt = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    data = {"event_time": dt}
    serialized = BaseStorageWriter.serialize_payload(data)
    parsed = json.loads(serialized.decode("utf-8"))
    assert "2026-08-15" in parsed["event_time"]


def test_serialize_payload_handles_raw_bytes_and_string() -> None:
    assert BaseStorageWriter.serialize_payload(b"raw_bytes") == b"raw_bytes"
    assert BaseStorageWriter.serialize_payload('{"raw": "str"}') == b'{"raw": "str"}'


def test_serialize_payload_none_raises_value_error() -> None:
    with pytest.raises(ValueError, match="payload cannot be None"):
        BaseStorageWriter.serialize_payload(None)


def test_template_method_orchestration() -> None:
    writer = ConcreteStorageWriter()
    dt = datetime(2026, 11, 1, tzinfo=timezone.utc)

    result_uri = writer.write(
        payload={"order_id": 500},
        dataset_name="woocommerce",
        filename="batch.json",
        execution_date=dt,
    )

    assert result_uri == "mock://storage/woocommerce/year=2026/month=11/batch.json"
    assert writer.last_relative_path == "woocommerce/year=2026/month=11/batch.json"
    assert json.loads(writer.last_data.decode("utf-8")) == {"order_id": 500}
