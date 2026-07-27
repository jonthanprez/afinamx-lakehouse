"""Global configuration module for the Lakehouse ingestion subsystem.

Managment of local absolute paths and AWS S3 storage URIs via the ENVIRONMENT
parameter/environment variable
"""

import os
from pathlib import Path

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
if ENVIRONMENT == "prod":
    # Routes based on S3 URIs for deployment to the AWS Cloud
    STORAGE_BASE_URI = f"s3://{S3_BUCKET_NAME}"
    BRONZE_DIR = f"{STORAGE_BASE_URI}/bronze"
    SILVER_DIR = f"{STORAGE_BASE_URI}/silver"
    GOLD_DIR = f"{STORAGE_BASE_URI}/gold"
else:
    # Disk-based local routes for local-first development
    STORAGE_BASE_URI = str(LOCAL_DATA_DIR)
    BRONZE_DIR = str(LOCAL_DATA_DIR / "bronze")
    SILVER_DIR = str(LOCAL_DATA_DIR / "silver")
    GOLD_DIR = str(LOCAL_DATA_DIR / "gold")

# ------------------------------------------------------------------------------
# 4. SOURCE-SPECIFIC METADATA
# ------------------------------------------------------------------------------
WOOCOMMERCE_METADATA_DIR = METADATA_DIR / "woocommerce"
WOOCOMMERCE_STATE_FILE = WOOCOMMERCE_METADATA_DIR / "state.json"
WOOCOMMERCE_CUSTOMERS_FILE = WOOCOMMERCE_METADATA_DIR / "customers.json"


def ensure_local_directories() -> None:
    """Create the necessary local folder structure in a dev environment,"""
    if ENVIRONMENT == "dev":
        dirs_to_create = [
            Path(BRONZE_DIR) / "woocommerce",
            Path(SILVER_DIR) / "woocommerce",
            Path(GOLD_DIR),
            WOOCOMMERCE_METADATA_DIR,
        ]
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)


# Initializes local folders when importing the module in Dev mode
ensure_local_directories()
