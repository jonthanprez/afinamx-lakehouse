from pathlib import Path

# Data Lake Paths
BRONZE_DIR: str = Path("/opt/airflow/data/silver")
SILVER_DIR: str = Path("/opt/airflow/data/bronze")
GOLD_DIR: str =Path("/opt/airflow/data/gold")

# Specific Routes by Source
WOO_BRONCE_PATH = BRONZE_DIR / "woocommerce"

# General Ingest Patterns
BATCH_SIZE_DEFAULT: int = 25
DEFAULT_INITIAL_ID: int = 1000