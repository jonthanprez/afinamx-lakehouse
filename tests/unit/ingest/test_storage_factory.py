"""Unit tests for the StorageWriterFactory abstraction switch.

Validates the Abstract Factory pattern, runtime dynamic polymorphism,
environment-based resolution (DEV vs PROD), manual overrides, and error guards.
"""

from pathlib import Path
from unittest.mock import PropertyMock, patch
import pytest

from src.ingest.config import IngestConfig, config
from src.ingest.storage.base import BaseStorageWriter
from src.ingest.storage.factory import StorageWriterFactory
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter


def test_factory_resolves_local_writer_via_config() -> None:
    """Verify factory returns LocalStorageWriter when config.environment is dev."""
    with (
        patch.object(config, "environment", "dev"),
        patch.object(
            IngestConfig,
            "bronze_dir",
            new_callable=PropertyMock,
            return_value=Path("/mock/bronze"),
        ),
    ):
        writer = StorageWriterFactory.get_storage_writer()

        assert isinstance(writer, LocalStorageWriter)
        assert isinstance(writer, BaseStorageWriter)
        assert str(writer.base_dir) == "/mock/bronze"


def test_factory_resolves_s3_writer_via_config() -> None:
    """Verify factory returns S3StorageWriter when config.environment is prod."""
    with (
        patch.object(config, "environment", "prod"),
        patch.object(config, "s3_bucket_name", "mock-prod-bucket"),
        patch.object(config, "aws_conn_id", "aws_default"),
        patch("boto3.client"),
    ):
        writer = StorageWriterFactory.get_storage_writer()

        assert isinstance(writer, S3StorageWriter)
        assert isinstance(writer, BaseStorageWriter)
        assert writer.bucket_name == "mock-prod-bucket"


def test_factory_resolves_local_writer_via_manual_override() -> None:
    """Verify manual storage_type='local' overrides global PROD configuration."""
    with (
        patch.object(config, "environment", "prod"),
        patch.object(
            IngestConfig,
            "bronze_dir",
            new_callable=PropertyMock,
            return_value=Path("/mock/bronze"),
        ),
    ):
        writer = StorageWriterFactory.get_storage_writer(storage_type="local")

        assert isinstance(writer, LocalStorageWriter)
        assert str(writer.base_dir) == "/mock/bronze"


def test_factory_resolves_s3_writer_via_manual_override() -> None:
    """Verify manual storage_type='s3' overrides global DEV configuration."""
    with (
        patch.object(config, "environment", "dev"),
        patch.object(config, "s3_bucket_name", "custom-s3-bucket"),
        patch("boto3.client"),
    ):
        writer = StorageWriterFactory.get_storage_writer(storage_type="s3")

        assert isinstance(writer, S3StorageWriter)
        assert writer.bucket_name == "custom-s3-bucket"


@pytest.mark.parametrize(
    "raw_target,expected_class",
    [
        ("dev", LocalStorageWriter),
        ("DEV", LocalStorageWriter),
        (" local ", LocalStorageWriter),
        ("prod", S3StorageWriter),
        ("PROD", S3StorageWriter),
        (" s3 ", S3StorageWriter),
    ],
)
def test_factory_sanitizes_case_and_whitespace(
    raw_target: str, expected_class: type
) -> None:
    """Verify factory handles uppercase and surrounding whitespace gracefully."""
    with (
        patch.object(
            IngestConfig,
            "bronze_dir",
            new_callable=PropertyMock,
            return_value=Path("/mock/bronze"),
        ),
        patch.object(config, "s3_bucket_name", "mock-bucket"),
        patch("boto3.client"),
    ):
        writer = StorageWriterFactory.get_storage_writer(storage_type=raw_target)

        assert isinstance(writer, expected_class)
        assert isinstance(writer, BaseStorageWriter)


def test_factory_rejects_unsupported_environment() -> None:
    """Verify factory raises ValueError when an unsupported storage target is provided."""
    with patch.object(config, "environment", "dev"):
        with pytest.raises(
            ValueError, match="Unsupported storage type or environment: 'staging'"
        ):
            StorageWriterFactory.get_storage_writer(storage_type="staging")
