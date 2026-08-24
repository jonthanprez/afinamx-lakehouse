"""Unit tests for the S3StorageWriter class.

Validates AWS S3 Medallion architecture (Hive-partitioned keys),
operational metadata envelopment, serialization, and cloud error handling.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Union
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from src.ingest.exceptions import StorageError
from src.ingest.storage.s3_writer import S3StorageWriter


@pytest.fixture
def mock_s3_client() -> MagicMock:
    """Fixture providing a mocked boto3 S3 client."""
    return MagicMock()


@pytest.fixture
def s3_writer(mock_s3_client: MagicMock) -> S3StorageWriter:
    """Fixture providing an S3StorageWriter with an injected mock S3 client."""
    with patch("boto3.client", return_value=mock_s3_client):
        writer = S3StorageWriter(bucket_name="test-afinamx-lakehouse-bucket")
        writer.s3_client = mock_s3_client
        return writer


def test_s3_writer_initialization_defaults_to_config() -> None:
    """Verify S3StorageWriter falls back to global S3_BUCKET_NAME when bucket is None."""
    with (
        patch("boto3.client") as mock_boto,
        patch(
            "src.ingest.storage.s3_writer.S3_BUCKET_NAME",
            "global-lakehouse-bucket",
        ),
    ):
        writer = S3StorageWriter()
        assert writer.bucket_name == "global-lakehouse-bucket"
        mock_boto.assert_called_once_with("s3")


def test_s3_writer_constructs_hive_partitioned_s3_uri(
    s3_writer: S3StorageWriter, mock_s3_client: MagicMock
) -> None:
    """Verify Hive partitioning (year=YYYY/month=MM) with zero-padded months and S3 URI."""
    test_data: List[Dict[str, str]] = [{"id": "1001", "status": "processing"}]
    exec_date = datetime(2026, 8, 24, 14, 30, 0, tzinfo=timezone.utc)

    s3_uri = s3_writer.write(
        payload=test_data,
        dataset_name="woocommerce",
        filename="batch_01.json",
        execution_date=exec_date,
    )

    # 1. Verify returned URI format
    expected_uri = "s3://test-afinamx-lakehouse-bucket/bronze/woocommerce/year=2026/month=08/batch_01.json"
    assert s3_uri == expected_uri

    # 2. Verify put_object called once with exact S3 key
    mock_s3_client.put_object.assert_called_once()
    call_kwargs = mock_s3_client.put_object.call_args.kwargs

    assert call_kwargs["Bucket"] == "test-afinamx-lakehouse-bucket"
    assert call_kwargs["Key"] == "bronze/woocommerce/year=2026/month=08/batch_01.json"
    assert call_kwargs["ContentType"] == "application/json; charset=utf-8"


def test_s3_writer_persists_valid_json_with_metadata_envelope(
    s3_writer: S3StorageWriter, mock_s3_client: MagicMock
) -> None:
    """Verify payload is wrapped inside operational metadata envelope and UTF-8 encoded."""
    test_data: List[Dict[str, Union[int, float]]] = [
        {"order_id": 1002, "total": 1850.50}
    ]
    exec_date = datetime(2026, 12, 1, 9, 0, 0, tzinfo=timezone.utc)

    s3_writer.write(
        payload=test_data,
        dataset_name="woocommerce",
        filename="orders.json",
        execution_date=exec_date,
    )

    # Inspect bytes payload delivered to AWS S3 put_object
    call_kwargs = mock_s3_client.put_object.call_args.kwargs
    raw_body_bytes: bytes = call_kwargs["Body"]

    assert isinstance(raw_body_bytes, bytes)

    saved_payload = json.loads(raw_body_bytes.decode("utf-8"))

    # Assert envelope structure and contents
    assert "_metadata" in saved_payload
    assert saved_payload["_metadata"]["dataset_name"] == "woocommerce"
    assert saved_payload["_metadata"]["execution_date"] == exec_date.isoformat()
    assert "ingested_at" in saved_payload["_metadata"]
    assert saved_payload["data"] == test_data


def test_s3_writer_handles_dictionary_payload(
    s3_writer: S3StorageWriter, mock_s3_client: MagicMock
) -> None:
    """Verify dictionary payloads are wrapped and serialized accurately."""
    test_data: Dict[str, Any] = {
        "order_id": 9999,
        "status": "completed",
        "total": "320.00",
    }
    exec_date = datetime(2026, 3, 10, tzinfo=timezone.utc)

    s3_writer.write(
        payload=test_data,
        dataset_name="woocommerce",
        filename="single_order.json",
        execution_date=exec_date,
    )

    call_kwargs = mock_s3_client.put_object.call_args.kwargs
    saved_payload = json.loads(call_kwargs["Body"].decode("utf-8"))

    assert saved_payload["data"] == test_data


def test_s3_writer_wraps_client_error_in_storage_error(
    s3_writer: S3StorageWriter, mock_s3_client: MagicMock
) -> None:
    """Verify AWS ClientError (e.g., AccessDenied, NoSuchBucket) raises custom StorageError."""
    mock_s3_client.put_object.side_effect = ClientError(
        error_response={"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        operation_name="PutObject",
    )

    exec_date = datetime(2026, 8, 24, tzinfo=timezone.utc)

    with pytest.raises(
        StorageError, match="Critical failure writing object to AWS S3"
    ) as exc_info:
        s3_writer.write(
            payload={"id": 1},
            dataset_name="woocommerce",
            filename="error_test.json",
            execution_date=exec_date,
        )

    # Verify original exception is chained
    assert isinstance(exc_info.value.__cause__, ClientError)


def test_s3_writer_wraps_botocore_network_error_in_storage_error(
    s3_writer: S3StorageWriter, mock_s3_client: MagicMock
) -> None:
    """Verify low-level BotoCoreError (e.g., connection timeout) raises custom StorageError."""
    mock_s3_client.put_object.side_effect = BotoCoreError()

    exec_date = datetime(2026, 8, 24, tzinfo=timezone.utc)

    with pytest.raises(
        StorageError, match="Critical failure writing object to AWS S3"
    ) as exc_info:
        s3_writer.write(
            payload={"id": 1},
            dataset_name="woocommerce",
            filename="timeout_test.json",
            execution_date=exec_date,
        )

    assert isinstance(exc_info.value.__cause__, BotoCoreError)


def test_s3_writer_wraps_unexpected_exception_in_storage_error(
    s3_writer: S3StorageWriter, mock_s3_client: MagicMock
) -> None:
    """Verify unexpected generic exceptions raise custom StorageError."""
    mock_s3_client.put_object.side_effect = RuntimeError("Unexpected runtime failure")

    exec_date = datetime(2026, 8, 24, tzinfo=timezone.utc)

    with pytest.raises(StorageError, match="Unexpected failure writing dataset"):
        s3_writer.write(
            payload={"id": 1},
            dataset_name="woocommerce",
            filename="unexpected_test.json",
            execution_date=exec_date,
        )
