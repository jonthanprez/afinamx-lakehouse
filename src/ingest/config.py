"""Global configuration module for the Lakehouse ingestion subsystem.

Management of local absolute paths and AWS S3 storage URIs via the ENVIRONMENT
parameter/environment variable, backed by a validated Pydantic model.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# ------------------------------------------------------------------------------
# 1. BASE RESOLUTION CONSTANTS
# ------------------------------------------------------------------------------
DEFAULT_ROOT: Path = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------------------
# 2. INGEST CONFIGURATION MODEL
# ------------------------------------------------------------------------------
class IngestConfig(BaseModel):
    """Structured and validated configuration model for the ingestion subsystem."""

    model_config = {"arbitrary_types_allowed": True}

    # Storage Environments & AWS
    environment: Literal["dev", "prod"] = Field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "dev").strip().lower()  # type: ignore[assignment]
    )
    s3_bucket_name: str = Field(
        default_factory=lambda: os.getenv("S3_BUCKET_NAME", "afinamx-lakehouse-prod")
    )
    aws_conn_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("AWS_CONN_ID", None)
    )

    # Base Paths
    project_root: Path = Field(
        default_factory=lambda: Path(os.getenv("AIRFLOW_HOME", DEFAULT_ROOT))
    )
    local_data_dir: Optional[Path] = None

    # WooCommerce Source Configuration
    woocommerce_api_url: str = Field(
        default_factory=lambda: os.getenv(
            "WOOCOMMERCE_API_URL", "https://tienda.example.com/wp-json/wc/v3"
        )
    )
    woocommerce_consumer_key: str = Field(
        default_factory=lambda: os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
    )
    woocommerce_consumer_secret: str = Field(
        default_factory=lambda: os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")
    )
    default_start_order_id: int = Field(
        default_factory=lambda: int(os.getenv("DEFAULT_START_ORDER_ID", "1000"))
    )

    # Logging Configuration
    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip().upper()
    )

    # Simulator & Chaos Configuration
    use_simulator: bool = Field(
        default_factory=lambda: os.getenv("USE_SIMULATOR", "true").strip().lower()
        in ("true", "1", "yes")
    )
    simulator_enable_anomalies: bool = Field(
        default_factory=lambda: os.getenv("SIMULATOR_ENABLE_ANOMALIES", "true")
        .strip()
        .lower()
        in ("true", "1", "yes")
    )
    simulator_anomaly_rate: float = Field(
        default_factory=lambda: float(os.getenv("SIMULATOR_ANOMALY_RATE", "0.15")),
        ge=0.0,
        le=1.0,
    )

    # --------------------------------------------------------------------------
    # Field Validators
    # --------------------------------------------------------------------------
    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("use_simulator", "simulator_enable_anomalies", mode="before")
    @classmethod
    def _normalize_bool(cls, value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)

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
        """Returns base URI depending on environment (local path or s3 URI)."""
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
# 3. GLOBAL SINGLETON INSTANCE & BACKWARD-COMPATIBLE EXPORTS
# ------------------------------------------------------------------------------
config = IngestConfig()

ENVIRONMENT: str = config.environment
S3_BUCKET_NAME: str = config.s3_bucket_name
AWS_CONN_ID: Optional[str] = config.aws_conn_id

PROJECT_ROOT: Path = config.project_root
assert config.local_data_dir is not None
LOCAL_DATA_DIR: Path = config.local_data_dir
METADATA_DIR: Path = config.metadata_dir

STORAGE_BASE_URI: str = config.storage_base_uri
BRONZE_DIR: Union[Path, str] = config.bronze_dir
SILVER_DIR: Union[Path, str] = config.silver_dir
GOLD_DIR: Union[Path, str] = config.gold_dir

WOOCOMMERCE_METADATA_DIR: Path = config.woocommerce_metadata_dir
WOOCOMMERCE_STATE_FILE: Path = config.woocommerce_state_file
WOOCOMMERCE_CUSTOMERS_FILE: Path = config.woocommerce_customers_file

WOOCOMMERCE_API_URL: str = config.woocommerce_api_url
WOOCOMMERCE_CONSUMER_KEY: str = config.woocommerce_consumer_key
WOOCOMMERCE_CONSUMER_SECRET: str = config.woocommerce_consumer_secret
DEFAULT_START_ORDER_ID: int = config.default_start_order_id

LOG_LEVEL: str = config.log_level

USE_SIMULATOR: bool = config.use_simulator
SIMULATOR_ENABLE_ANOMALIES: bool = config.simulator_enable_anomalies
SIMULATOR_ANOMALY_RATE: float = config.simulator_anomaly_rate


def ensure_local_directories() -> None:
    """Create base directory tree for local DEV environment.

    Honors dynamically patched module attributes (such as in unit tests).
    """
    if ENVIRONMENT == "dev":
        dirs_to_create = [
            Path(LOCAL_DATA_DIR),
            Path(BRONZE_DIR),
            Path(SILVER_DIR),
            Path(GOLD_DIR),
            Path(WOOCOMMERCE_METADATA_DIR),
        ]
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)
