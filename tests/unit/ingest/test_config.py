"""Unit tests for src.ingest.config module.

Verifies IngestConfig Pydantic BaseSettings model validation, environment switches, path resolutions,
directory creation, and unified singleton instance properties.
"""

from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
import pytest

from src.ingest.config import IngestConfig, config
from src.ingest.exceptions import IngestionError, StorageError


# -----------------------------------------------------------------------------
# 1. INGESTCONFIG MODEL & ISOLATED INSTANTIATION TESTS
# -----------------------------------------------------------------------------


def test_ingest_config_dev_mode_defaults() -> None:
    """Verify DEV mode defaults resolve local POSIX URI strings for medallion layers."""
    cfg = IngestConfig(environment="dev")

    assert cfg.environment == "dev"
    assert (cfg.project_root / "src").exists()
    assert (cfg.project_root / "src" / "ingest").exists()
    assert isinstance(cfg.bronze_dir, str)
    assert isinstance(cfg.silver_dir, str)
    assert isinstance(cfg.gold_dir, str)
    assert "bronze" in cfg.bronze_dir
    assert cfg.local_data_dir is not None
    assert cfg.storage_base_uri == cfg.local_data_dir.as_posix()
    assert cfg.bronze_dir == (cfg.local_data_dir / "bronze").as_posix()
    assert cfg.silver_dir == (cfg.local_data_dir / "silver").as_posix()
    assert cfg.gold_dir == (cfg.local_data_dir / "gold").as_posix()


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
    assert cfg.bronze_dir == (custom_root / "data" / "bronze").as_posix()
    assert isinstance(cfg.bronze_dir, str)
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


def test_ingest_config_alias_choices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify project_root resolves from AIRFLOW_HOME or PROJECT_ROOT via AliasChoices."""
    path_airflow = tmp_path / "airflow_home"
    path_project = tmp_path / "project_root"

    # 1. AIRFLOW_HOME takes priority
    monkeypatch.setenv("AIRFLOW_HOME", str(path_airflow))
    monkeypatch.setenv("PROJECT_ROOT", str(path_project))
    cfg1 = IngestConfig()
    assert cfg1.project_root == path_airflow

    # 2. PROJECT_ROOT is used if AIRFLOW_HOME is unset
    monkeypatch.delenv("AIRFLOW_HOME", raising=False)
    monkeypatch.setenv("PROJECT_ROOT", str(path_project))
    cfg2 = IngestConfig()
    assert cfg2.project_root == path_project


def test_ingest_config_computed_fields_serialization() -> None:
    """Verify computed_fields are included in model_dump and model_dump_json."""
    cfg = IngestConfig(environment="dev")
    data = cfg.model_dump()

    assert "storage_base_uri" in data
    assert "bronze_dir" in data
    assert "silver_dir" in data
    assert "gold_dir" in data
    assert "metadata_dir" in data
    assert "woocommerce_metadata_dir" in data
    assert "woocommerce_state_file" in data
    assert "woocommerce_customers_file" in data

    json_str = cfg.model_dump_json()
    assert "storage_base_uri" in json_str
    assert "bronze_dir" in json_str
    assert "silver_dir" in json_str
    assert "gold_dir" in json_str


# -----------------------------------------------------------------------------
# 2. LOCAL DIRECTORY INITIALIZATION TESTS
# -----------------------------------------------------------------------------


def test_ensure_local_directories_creation(mock_lakehouse_dirs: dict) -> None:
    """Verify ensure_local_directories creates required folders in dev mode."""
    with patch.object(config, "environment", "dev"):
        config.ensure_local_directories()

        assert Path(config.local_data_dir).exists()
        assert Path(config.woocommerce_metadata_dir).exists()


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
# 3. UNIFIED SINGLETON INSTANCE PROPERTIES
# -----------------------------------------------------------------------------


def test_config_singleton_instance_properties() -> None:
    """Verify all expected configuration properties are available on the singleton instance."""
    assert isinstance(config, IngestConfig)
    assert hasattr(config, "environment")
    assert hasattr(config, "s3_bucket_name")
    assert hasattr(config, "bronze_dir")
    assert hasattr(config, "silver_dir")
    assert hasattr(config, "gold_dir")
    assert hasattr(config, "woocommerce_api_url")
    assert hasattr(config, "woocommerce_consumer_key")
    assert hasattr(config, "woocommerce_consumer_secret")
    assert hasattr(config, "aws_conn_id")
    assert hasattr(config, "default_start_order_id")
    assert config.default_start_order_id == 1000


# -----------------------------------------------------------------------------
# 4. EXCEPTION HIERARCHY TESTS
# -----------------------------------------------------------------------------


def test_custom_exceptions_inheritance() -> None:
    """Verify StorageError inherits cleanly from IngestionError."""
    error = StorageError("Disk write failed")
    assert isinstance(error, IngestionError)
    assert str(error) == "Disk write failed"
