"""Global configuration module for the Lakehouse ingestion subsystem.

Management of local absolute paths and AWS S3 storage URIs via the ENVIRONMENT
parameter/environment variable.
"""

import os
from pathlib import Path
from typing import Union

# ------------------------------------------------------------------------------
# 1. STORAGE ENVIRONMENTS AND BUCKETS
# ------------------------------------------------------------------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev").lower()
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "afinamx-lakehouse-prod")

# ------------------------------------------------------------------------------
# 2. PROJECT PATHS DETERMINATION
# ------------------------------------------------------------------------------
DEFAULT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(os.getenv("AIRFLOW_HOME", DEFAULT_ROOT))

LOCAL_DATA_DIR = PROJECT_ROOT / "data"
METADATA_DIR = LOCAL_DATA_DIR / "metadata"

# ------------------------------------------------------------------------------
# 3. MEDALLION ABSTRACTION (DEV VS PROD SWITCH)
# ------------------------------------------------------------------------------
# Paths are exported as Path objects in DEV and URI strings in PROD
STORAGE_BASE_URI: str
BRONZE_DIR: Union[Path, str]
SILVER_DIR: Union[Path, str]
GOLD_DIR: Union[Path, str]

if ENVIRONMENT == "prod":
    # S3 URIs for Cloud Deployment
    STORAGE_BASE_URI = f"s3://{S3_BUCKET_NAME}"
    BRONZE_DIR = f"{STORAGE_BASE_URI}/bronze"
    SILVER_DIR = f"{STORAGE_BASE_URI}/silver"
    GOLD_DIR = f"{STORAGE_BASE_URI}/gold"
else:
    # Local Path objects for DEV
    STORAGE_BASE_URI = str(LOCAL_DATA_DIR)
    BRONZE_DIR = LOCAL_DATA_DIR / "bronze"
    SILVER_DIR = LOCAL_DATA_DIR / "silver"
    GOLD_DIR = LOCAL_DATA_DIR / "gold"

# ------------------------------------------------------------------------------
# 4. SOURCE-SPECIFIC METADATA
# ------------------------------------------------------------------------------
WOOCOMMERCE_METADATA_DIR = METADATA_DIR / "woocommerce"
WOOCOMMERCE_STATE_FILE = WOOCOMMERCE_METADATA_DIR / "state.json"
WOOCOMMERCE_CUSTOMERS_FILE = WOOCOMMERCE_METADATA_DIR / "customers.json"


# ------------------------------------------------------------------------------
# 5. ENVIRONMENT INITIALIZATION
# ------------------------------------------------------------------------------
def ensure_local_directories() -> None:
    """Create base directory tree for local DEV environment."""
    if ENVIRONMENT == "dev":
        dirs_to_create = [
            LOCAL_DATA_DIR,
            Path(BRONZE_DIR),
            Path(SILVER_DIR),
            Path(GOLD_DIR),
            WOOCOMMERCE_METADATA_DIR,
        ]
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)


# Execute auto-creation upon module import in DEV mode
ensure_local_directories()
