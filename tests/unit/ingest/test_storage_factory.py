"""Unit tests for the StorageWriterFactory abstraction switch.

Verifies dynamic instantiation using both global config and manual overrides.
"""

from unittest.mock import patch
import pytest

from src.ingest.storage.factory import StorageWriterFactory
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter


def test_factory_resolves_local_writer_via_config() -> None:
    """Verify factory returns LocalStorageWriter when config.ENVIRONMENT is dev."""
    with patch("src.ingest.storage.factory.config.ENVIRONMENT", "dev"), patch(
        "src.ingest.storage.factory.config.BRONZE_DIR", "/mock/bronze"
    ):
        writer = StorageWriterFactory.get_storage_writer()

        assert isinstance(writer, LocalStorageWriter)
        # FIX: Cast Path object to string to match our mocked injection
        assert str(writer.base_dir) == "/mock/bronze"


def test_factory_resolves_s3_writer_via_config() -> None:
    """Verify factory returns S3StorageWriter when config.ENVIRONMENT is prod."""
    with patch("src.ingest.storage.factory.config.ENVIRONMENT", "prod"), patch(
        "src.ingest.storage.factory.config.S3_BUCKET_NAME", "mock-prod-bucket"
    ), patch(
        "src.ingest.storage.factory.config.AWS_CONN_ID", "aws_mock", create=True
    ), patch("boto3.client"):  # Shield AWS interactions
        writer = StorageWriterFactory.get_storage_writer()

        assert isinstance(writer, S3StorageWriter)
        assert writer.bucket_name == "mock-prod-bucket"


def test_factory_resolves_local_writer_via_manual_override() -> None:
    """Verify manual storage_type='local' overrides global PROD config."""
    # Simulate being in a PROD environment...
    with patch("src.ingest.storage.factory.config.ENVIRONMENT", "prod"), patch(
        "src.ingest.storage.factory.config.BRONZE_DIR", "/mock/bronze"
    ):
        # ...but explicitly requesting local storage
        writer = StorageWriterFactory.get_storage_writer(storage_type="local ")

        assert isinstance(writer, LocalStorageWriter)


def test_factory_rejects_unsupported_environment() -> None:
    """Verify factory raises ValueError when an unsupported type is provided."""
    with patch("src.ingest.storage.factory.config.ENVIRONMENT", "dev"):
        # Explicitly passing an invalid target
        with pytest.raises(ValueError, match="Unsupported storage type or environment"):
            StorageWriterFactory.get_storage_writer(storage_type="staging")
