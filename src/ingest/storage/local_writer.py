import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.ingest.config import BRONZE_DIR
from src.ingest.storage.base import BaseStorageWriter

logger = logging.getLogger(__name__)


class LocalStorageWriter(BaseStorageWriter):
    """Data writer for the local file system (DEV Environment)."""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(BRONZE_DIR)
        logger.debug("LocalStorageWriter initialized with base_dir: %s", self.base_dir)

    def write(
        self,
        payload: Dict[str, Any],
        dataset_name: str,
        filename: str,
        execution_date: datetime,
    ) -> str:
        # 1. Build Hive partition path
        hive_partition = (
            Path(f"year={execution_date.year}") / f"month={execution_date.month:02d}"
        )
        target_dir = self.base_dir / dataset_name / hive_partition
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file_path = target_dir / filename

        logger.info(
            "Writing local dataset '%s' to path: %s",
            dataset_name,
            target_file_path,
        )

        # 2. Inject operational metadata envelope
        enveloped_payload = {
            "_metadata": {
                "execution_date": execution_date.isoformat(),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "dataset_name": dataset_name,
            },
            "data": payload,
        }

        # 3. True Atomic Write via Temporary File + Atomic Rename
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=target_dir,
                delete=False,
                encoding="utf-8",
                prefix=".tmp_",
            ) as tmp_file:
                json.dump(enveloped_payload, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())  # Force buffer flush to physical disk
                temp_path = tmp_file.name

            # OS atomic swap: replaces target_file_path instantly
            os.replace(temp_path, target_file_path)
            logger.info("Successfully wrote local file: %s", target_file_path)

        except Exception as e:
            logger.error(
                "Failed to write local dataset '%s' to %s: %s",
                dataset_name,
                target_file_path,
                e,
                exc_info=True,
            )
            raise

        return str(target_file_path.resolve())
