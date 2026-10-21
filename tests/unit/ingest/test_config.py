"""Unit tests for src.ingest.config module.

Verifies IngestConfig Pydantic model validation, environment switches, path resolutions,
directory creation, and backward-compatible module-level exports without requiring
unstable module reloading (importlib.reload).
"""

from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
import pytest

import src.ingest.config as config
from src.ingest.config import IngestConfig
from src.ingest.exceptions import IngestionError, StorageError

# -----------------------------------------------------------------------------
# 1. INGESTCONFIG MODEL & ISOLATED INSTANTIATION TESTS
# -----------------------------------------------------------------------------


def test_ingest_config_dev_mode_defaults() -> None:
    """Verify DEV mode defaults resolve local Path instances for medallion layers."""
    cfg = IngestConfig(environment="dev")

    assert cfg.environment == "dev"
    assert (cfg.project_root / "src").exists()
    assert (cfg.project_root / "src" / "ingest").exists()
    assert isinstance(cfg.bronze_dir, Path)
    assert isinstance(cfg.silver_dir, Path)
    assert isinstance(cfg.gold_dir, Path)
    assert "bronze" in str(cfg.bronze_dir)
    assert cfg.storage_base_uri == str(cfg.local_data_dir)


def test_ingest_config_prod_mode_switch() -> None:
    """Verify PROD mode resolves medallion layers to AWS S3 URIs without module reload."""
    cfg = IngestConfig(
        environment="prod",
        s3_bucket_name="my-production-bucket",
    )

    assert cfg.environment == "prod"
    assert cfg.storage_base_uri == "s3://my-production-bucket"
    assert cfg.bronze_dir == "s3://my-production-bucket/bronze"
    assert cfg.silver_dir == "s3://my-production-bucket/silver"
    assert cfg.gold_dir == "s3://my-production-bucket/gold"


def test_ingest_config_log_level_normalization() -> None:
    """Verify log_level normalization to uppercase and custom values."""
    cfg_default = IngestConfig()
    assert cfg_default.log_level in ("INFO", "DEBUG", "WARNING", "ERROR")

    cfg_custom = IngestConfig(log_level="debug")  # type: ignore[arg-type]
    assert cfg_custom.log_level == "DEBUG"


def test_ingest_config_isolated_instantiation(tmp_path: Path) -> None:
    """Verify IngestConfig can be instantiated with custom paths without mutating globals."""
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


# -----------------------------------------------------------------------------
# 2. LOCAL DIRECTORY INITIALIZATION TESTS
# -----------------------------------------------------------------------------


def test_ensure_local_directories_creation(mock_lakehouse_dirs: dict) -> None:
    """Verify ensure_local_directories creates required folders in dev mode."""
    with patch("src.ingest.config.ENVIRONMENT", "dev"):
        config.ensure_local_directories()

        assert Path(config.LOCAL_DATA_DIR).exists()
        assert Path(config.WOOCOMMERCE_METADATA_DIR).exists()


def test_ensure_local_directories_noop_in_prod() -> None:
    """Verify ensure_local_directories skips directory creation in PROD mode cleanly."""
    prod_cfg = IngestConfig(environment="prod")
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        prod_cfg.ensure_local_directories()
        mock_mkdir.assert_not_called()


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
# 3. BACKWARD-COMPATIBLE MODULE-LEVEL EXPORTS
# -----------------------------------------------------------------------------


def test_config_module_level_exports() -> None:
    """Verify all expected top-level constants and singletons remain available."""
    assert hasattr(config, "config")
    assert isinstance(config.config, IngestConfig)
    assert hasattr(config, "ENVIRONMENT")
    assert hasattr(config, "S3_BUCKET_NAME")
    assert hasattr(config, "BRONZE_DIR")
    assert hasattr(config, "SILVER_DIR")
    assert hasattr(config, "GOLD_DIR")
    assert hasattr(config, "WOOCOMMERCE_API_URL")
    assert hasattr(config, "WOOCOMMERCE_CONSUMER_KEY")
    assert hasattr(config, "WOOCOMMERCE_CONSUMER_SECRET")
    assert hasattr(config, "AWS_CONN_ID")
    assert hasattr(config, "DEFAULT_START_ORDER_ID")
    assert config.DEFAULT_START_ORDER_ID == 1000


# -----------------------------------------------------------------------------
# 4. EXCEPTION HIERARCHY TESTS
# -----------------------------------------------------------------------------


def test_custom_exceptions_inheritance() -> None:
    """Verify StorageError inherits cleanly from IngestionError."""
    error = StorageError("Disk write failed")
    assert isinstance(error, IngestionError)
    assert str(error) == "Disk write failed"
