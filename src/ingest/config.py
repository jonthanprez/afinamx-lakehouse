"""Global configuration module for the Lakehouse ingestion subsystem.

Management of local absolute paths and AWS S3 storage URIs via the ENVIRONMENT
parameter/environment variable, backed by a validated Pydantic BaseSettings model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ------------------------------------------------------------------------------
# 1. BASE RESOLUTION CONSTANTS
# ------------------------------------------------------------------------------
DEFAULT_ROOT: Path = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------------------
# 2. INGEST CONFIGURATION MODEL
# ------------------------------------------------------------------------------
class IngestConfig(BaseSettings):
    """Structured and validated configuration model for the ingestion subsystem."""

    # Pydantic Settings reads automatically from environment variables and .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        validate_default=True,
    )

    # Storage Environments & AWS
    environment: Literal["dev", "prod"] = "dev"
    s3_bucket_name: str = "afinamx-lakehouse-prod"
    aws_conn_id: Optional[str] = None

    # Base Paths
    project_root: Path = Field(default=DEFAULT_ROOT, validation_alias="AIRFLOW_HOME")
    local_data_dir: Optional[Path] = None

    # WooCommerce Source Configuration
    woocommerce_api_url: str = "https://tienda.example.com/wp-json/wc/v3"
    woocommerce_consumer_key: str = ""
    woocommerce_consumer_secret: str = ""
    default_start_order_id: int = 1000

    # Logging Configuration
    log_level: str = "INFO"

    # Simulator & Chaos Configuration
    use_simulator: bool = True
    simulator_enable_anomalies: bool = True
    simulator_anomaly_rate: float = Field(default=0.15, ge=0.0, le=1.0)

    # --------------------------------------------------------------------------
    # Field Validators
    # --------------------------------------------------------------------------
    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _resolve_paths(self) -> IngestConfig:
        if self.local_data_dir is None:
            self.local_data_dir = self.project_root / "data"
        return self

    # --------------------------------------------------------------------------
    # Medallion & Storage Properties
    # --------------------------------------------------------------------------
    @property
    def storage_base_uri(self) -> str:
        """Returns base storage URI (local path or s3 URI)."""
        if self.environment == "prod":
            return f"s3://{self.s3_bucket_name}"
        return str(self.local_data_dir)

    @property
    def bronze_dir(self) -> Union[Path, str]:
        """Returns Bronze layer storage path (Path in dev, s3 URI in prod)."""
        if self.environment == "prod":
            return f"{self.storage_base_uri}/bronze"
        assert self.local_data_dir is not None
        return self.local_data_dir / "bronze"

    @property
    def silver_dir(self) -> Union[Path, str]:
        """Returns Silver layer storage path (Path in dev, s3 URI in prod)."""
        if self.environment == "prod":
            return f"{self.storage_base_uri}/silver"
        assert self.local_data_dir is not None
        return self.local_data_dir / "silver"

    @property
    def gold_dir(self) -> Union[Path, str]:
        """Returns Gold layer storage path (Path in dev, s3 URI in prod)."""
        if self.environment == "prod":
            return f"{self.storage_base_uri}/gold"
        assert self.local_data_dir is not None
        return self.local_data_dir / "gold"

    # --------------------------------------------------------------------------
    # Metadata Paths Properties
    # --------------------------------------------------------------------------
    @property
    def metadata_dir(self) -> Path:
        """Directory for Lakehouse state and extraction metadata."""
        assert self.local_data_dir is not None
        return self.local_data_dir / "metadata"

    @property
    def woocommerce_metadata_dir(self) -> Path:
        """Directory for WooCommerce checkpoint state and customer pool."""
        return self.metadata_dir / "woocommerce"

    @property
    def woocommerce_state_file(self) -> Path:
        """JSON checkpoint file tracking extraction watermarks."""
        return self.woocommerce_metadata_dir / "state.json"

    @property
    def woocommerce_customers_file(self) -> Path:
        """JSON pool file caching generated customer records."""
        return self.woocommerce_metadata_dir / "customers.json"

    # --------------------------------------------------------------------------
    # Directory Management
    # --------------------------------------------------------------------------
    def ensure_local_directories(self) -> None:
        """Create base directory tree for local DEV environment."""
        if self.environment == "dev":
            assert self.local_data_dir is not None
            dirs_to_create = [
                self.local_data_dir,
                Path(self.bronze_dir),
                Path(self.silver_dir),
                Path(self.gold_dir),
                self.woocommerce_metadata_dir,
            ]
            for directory in dirs_to_create:
                directory.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------
# 3. GLOBAL SINGLETON INSTANCE
# ------------------------------------------------------------------------------
config: IngestConfig = IngestConfig()
