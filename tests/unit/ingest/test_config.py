"""Unit tests for src.ingest.config module.

Verifies top-level constants, environment switches, path resolutions,
and directory creation initialization.
"""

import importlib
from pathlib import Path
from unittest.mock import patch
import pytest

import src.ingest.config as config
from src.ingest.exceptions import IngestionError, StorageError


# -----------------------------------------------------------------------------
# 1. ENVIRONMENT & STORAGE SWITCH TESTS
# -----------------------------------------------------------------------------


def test_config_dev_mode_defaults(set_testing_environment: None) -> None:
    """Verify DEV environment sets local Path instances for medallion layers."""
    # Reload config to apply mocked environment variables from conftest
    importlib.reload(config)

    assert config.ENVIRONMENT == "dev"
    assert isinstance(config.BRONZE_DIR, Path)
    assert isinstance(config.SILVER_DIR, Path)
    assert isinstance(config.GOLD_DIR, Path)
    assert "bronze" in str(config.BRONZE_DIR)


def test_config_prod_mode_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify PROD environment switches medallion paths to S3 URIs."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("S3_BUCKET_NAME", "my-production-bucket")

    # Reload module to trigger top-level evaluation under PROD
    importlib.reload(config)

    assert config.ENVIRONMENT == "prod"
    assert config.STORAGE_BASE_URI == "s3://my-production-bucket"
    assert config.BRONZE_DIR == "s3://my-production-bucket/bronze"
    assert config.SILVER_DIR == "s3://my-production-bucket/silver"
    assert config.GOLD_DIR == "s3://my-production-bucket/gold"

    # Cleanup: restore config state to dev
    monkeypatch.setenv("ENVIRONMENT", "dev")
    importlib.reload(config)


# -----------------------------------------------------------------------------
# 2. LOCAL DIRECTORY INITIALIZATION TESTS
# -----------------------------------------------------------------------------


def test_ensure_local_directories_creation(mock_lakehouse_dirs: dict) -> None:
    """Verify ensure_local_directories creates required folders in dev mode."""
    with patch("src.ingest.config.ENVIRONMENT", "dev"):
        config.ensure_local_directories()

        assert Path(config.LOCAL_DATA_DIR).exists()
        assert Path(config.WOOCOMMERCE_METADATA_DIR).exists()


def test_ensure_local_directories_noop_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ensure_local_directories skips directory creation in PROD mode."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    importlib.reload(config)

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        config.ensure_local_directories()
        mock_mkdir.assert_not_called()

    # Cleanup
    monkeypatch.setenv("ENVIRONMENT", "dev")
    importlib.reload(config)


# -----------------------------------------------------------------------------
# 3. EXCEPTION HIERARCHY TESTS
# -----------------------------------------------------------------------------


def test_custom_exceptions_inheritance() -> None:
    """Verify StorageError inherits cleanly from IngestionError."""
    error = StorageError("Disk write failed")
    assert isinstance(error, IngestionError)
    assert str(error) == "Disk write failed"
