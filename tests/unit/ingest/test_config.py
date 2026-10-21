"""Unit tests for src.ingest.config module.

Verifies top-level constants, environment switches, path resolutions,
directory creation initialization, and IngestConfig Pydantic model validation.
"""

import importlib
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
import pytest

import src.ingest.config as config
from src.ingest.config import IngestConfig
from src.ingest.exceptions import IngestionError, StorageError

# -----------------------------------------------------------------------------
# 1. ENVIRONMENT & STORAGE SWITCH TESTS (BACKWARD COMPATIBILITY)
# -----------------------------------------------------------------------------


def test_config_dev_mode_defaults(set_testing_environment: None) -> None:
    """Verify DEV environment sets local Path instances for medallion layers."""
    # Reload config to apply mocked environment variables from conftest
    importlib.reload(config)

    assert config.ENVIRONMENT == "dev"
    assert (config.DEFAULT_ROOT / "src").exists()
    assert (config.DEFAULT_ROOT / "src" / "ingest").exists()
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


def test_config_log_level_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify LOG_LEVEL defaults to INFO and honors environment overrides."""
    # 1. Default level
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    importlib.reload(config)
    assert config.LOG_LEVEL == "INFO"

    # 2. Override level
    monkeypatch.setenv("LOG_LEVEL", "debug")
    importlib.reload(config)
    assert config.LOG_LEVEL == "DEBUG"

    # Cleanup
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    importlib.reload(config)


def test_config_explicit_attributes_exposed() -> None:
    """Verify newly formalized attributes are exposed at module level."""
    assert hasattr(config, "WOOCOMMERCE_API_URL")
    assert hasattr(config, "WOOCOMMERCE_CONSUMER_KEY")
    assert hasattr(config, "WOOCOMMERCE_CONSUMER_SECRET")
    assert hasattr(config, "AWS_CONN_ID")
    assert hasattr(config, "DEFAULT_START_ORDER_ID")
    assert config.DEFAULT_START_ORDER_ID == 1000


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
# 3. INGESTCONFIG PYDANTIC MODEL TESTS
# -----------------------------------------------------------------------------


def test_ingest_config_isolated_instantiation(tmp_path: Path) -> None:
    """Verify IngestConfig can be instantiated in isolation without mutating globals."""
    custom_root = tmp_path / "custom_root"
    cfg = IngestConfig(
        environment="dev",
        project_root=custom_root,
        s3_bucket_name="custom-test-bucket",
        simulator_anomaly_rate=0.25,
    )

    assert cfg.environment == "dev"
    assert cfg.s3_bucket_name == "custom-test-bucket"
    assert cfg.simulator_anomaly_rate == 0.25
    assert cfg.bronze_dir == custom_root / "data" / "bronze"
    assert isinstance(cfg.bronze_dir, Path)
    assert (
        cfg.woocommerce_state_file
        == custom_root / "data" / "metadata" / "woocommerce" / "state.json"
    )


def test_ingest_config_prod_mode_properties() -> None:
    """Verify IngestConfig in prod mode computes S3 URIs."""
    cfg = IngestConfig(
        environment="prod",
        s3_bucket_name="afina-prod-lakehouse",
    )

    assert cfg.environment == "prod"
    assert cfg.storage_base_uri == "s3://afina-prod-lakehouse"
    assert cfg.bronze_dir == "s3://afina-prod-lakehouse/bronze"
    assert cfg.silver_dir == "s3://afina-prod-lakehouse/silver"
    assert cfg.gold_dir == "s3://afina-prod-lakehouse/gold"


def test_ingest_config_validation_rules() -> None:
    """Verify validation boundaries on anomaly rate and normalization."""
    # 1. Invalid anomaly rate > 1.0
    with pytest.raises(ValidationError):
        IngestConfig(simulator_anomaly_rate=1.5)

    # 2. Invalid anomaly rate < 0.0
    with pytest.raises(ValidationError):
        IngestConfig(simulator_anomaly_rate=-0.1)

    # 3. Case normalization for environment and log_level
    cfg = IngestConfig(environment="PROD", log_level="warning")  # type: ignore[arg-type]
    assert cfg.environment == "prod"
    assert cfg.log_level == "WARNING"


def test_ingest_config_ensure_local_directories_method(tmp_path: Path) -> None:
    """Verify ensure_local_directories method on model creates directories."""
    data_dir = tmp_path / "lakehouse_test_data"
    cfg = IngestConfig(
        environment="dev",
        local_data_dir=data_dir,
    )
    cfg.ensure_local_directories()

    assert data_dir.exists()
    assert (data_dir / "bronze").exists()
    assert (data_dir / "silver").exists()
    assert (data_dir / "gold").exists()
    assert (data_dir / "metadata" / "woocommerce").exists()


# -----------------------------------------------------------------------------
# 4. EXCEPTION HIERARCHY TESTS
# -----------------------------------------------------------------------------


def test_custom_exceptions_inheritance() -> None:
    """Verify StorageError inherits cleanly from IngestionError."""
    error = StorageError("Disk write failed")
    assert isinstance(error, IngestionError)
    assert str(error) == "Disk write failed"
