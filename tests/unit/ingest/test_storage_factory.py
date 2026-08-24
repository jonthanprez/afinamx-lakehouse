"""Unit tests for the StorageWriterFactory abstraction switch.

Validates the Abstract Factory pattern, runtime dynamic polymorphism,
environment-based resolution (DEV vs PROD), manual overrides, and error guards.
"""

from unittest.mock import patch
import pytest

from src.ingest.storage.base import BaseStorageWriter
from src.ingest.storage.factory import StorageWriterFactory
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter


def test_factory_resolves_local_writer_via_config() -> None:
    """Verify factory returns LocalStorageWriter when config.ENVIRONMENT is dev."""
    with (
        patch("src.ingest.storage.factory.config.ENVIRONMENT", "dev"),
        patch("src.ingest.storage.factory.config.BRONZE_DIR", "/mock/bronze"),
    ):
        writer = StorageWriterFactory.get_storage_writer()

        assert isinstance(writer, LocalStorageWriter)
        assert isinstance(writer, BaseStorageWriter)
        assert str(writer.base_dir) == "/mock/bronze"


def test_factory_resolves_s3_writer_via_config() -> None:
    """Verify factory returns S3StorageWriter when config.ENVIRONMENT is prod."""
    with (
        patch("src.ingest.storage.factory.config.ENVIRONMENT", "prod"),
        patch("src.ingest.storage.factory.config.S3_BUCKET_NAME", "mock-prod-bucket"),
        patch(
            "src.ingest.storage.factory.config.AWS_CONN_ID", "aws_default", create=True
        ),
        patch("boto3.client"),
    ):
        writer = StorageWriterFactory.get_storage_writer()

        assert isinstance(writer, S3StorageWriter)
        assert isinstance(writer, BaseStorageWriter)
        assert writer.bucket_name == "mock-prod-bucket"


def test_factory_resolves_local_writer_via_manual_override() -> None:
    """Verify manual storage_type='local' overrides global PROD configuration."""
    with (
        patch("src.ingest.storage.factory.config.ENVIRONMENT", "prod"),
        patch("src.ingest.storage.factory.config.BRONZE_DIR", "/mock/bronze"),
    ):
        writer = StorageWriterFactory.get_storage_writer(storage_type="local")

        assert isinstance(writer, LocalStorageWriter)
        assert str(writer.base_dir) == "/mock/bronze"


def test_factory_resolves_s3_writer_via_manual_override() -> None:
    """Verify manual storage_type='s3' overrides global DEV configuration."""
    with (
        patch("src.ingest.storage.factory.config.ENVIRONMENT", "dev"),
        patch("src.ingest.storage.factory.config.S3_BUCKET_NAME", "custom-s3-bucket"),
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
        patch("src.ingest.storage.factory.config.BRONZE_DIR", "/mock/bronze"),
        patch("src.ingest.storage.factory.config.S3_BUCKET_NAME", "mock-bucket"),
        patch("boto3.client"),
    ):
        writer = StorageWriterFactory.get_storage_writer(storage_type=raw_target)

        assert isinstance(writer, expected_class)
        assert isinstance(writer, BaseStorageWriter)


def test_factory_rejects_unsupported_environment() -> None:
    """Verify factory raises ValueError when an unsupported storage target is provided."""
    with patch("src.ingest.storage.factory.config.ENVIRONMENT", "dev"):
        with pytest.raises(
            ValueError, match="Unsupported storage type or environment: 'staging'"
        ):
            StorageWriterFactory.get_storage_writer(storage_type="staging")
