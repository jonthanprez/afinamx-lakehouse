import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.common.logger import get_logger
from src.ingest.config import BRONZE_DIR
from src.ingest.exceptions import StorageError
from src.ingest.storage.base import BaseStorageWriter

logger = get_logger(__name__)


class LocalStorageWriter(BaseStorageWriter):
    """Data writer for the local file system (DEV Environment)."""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(BRONZE_DIR)
        logger.debug(
            "LocalStorageWriter initialized",
            extra={"base_dir": str(self.base_dir)},
        )

    def write(
        self,
        payload: Union[Dict[str, Any], str, bytes],
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
            "Writing local dataset to path",
            extra={
                "dataset_name": dataset_name,
                "target_file_path": str(target_file_path),
                "execution_date": execution_date.isoformat(),
            },
        )

        # 2. True Atomic Write via Temporary File + Atomic Rename
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=target_dir,
                delete=False,
                encoding="utf-8",
                prefix=".tmp_",
            ) as tmp_file:
                if hasattr(payload, "model_dump"):
                    json.dump(
                        payload.model_dump(by_alias=True),
                        tmp_file,
                        ensure_ascii=False,
                        indent=2,
                    )
                elif isinstance(payload, (dict, list)):
                    json.dump(
                        payload,
                        tmp_file,
                        ensure_ascii=False,
                        indent=2,
                    )
                elif isinstance(payload, str):
                    tmp_file.write(payload)
                elif isinstance(payload, bytes):
                    tmp_file.write(payload.decode("utf-8"))
                else:
                    json.dump(
                        payload,
                        tmp_file,
                        ensure_ascii=False,
                        indent=2,
                    )
                tmp_file.flush()
                os.fsync(tmp_file.fileno())  # Force buffer flush to physical disk
                temp_path = tmp_file.name

            # OS atomic swap: replaces target_file_path instantly
            os.replace(temp_path, target_file_path)
            logger.info(
                "Successfully wrote local file",
                extra={
                    "dataset_name": dataset_name,
                    "target_file_path": str(target_file_path),
                },
            )

        except (OSError, PermissionError, TypeError, ValueError) as e:
            error_msg = f"Failed to write local dataset '{dataset_name}' to {target_file_path if 'target_file_path' in locals() else target_dir}: {e}"
            logger.error(
                "Failed to write local dataset",
                exc_info=True,
                extra={
                    "dataset_name": dataset_name,
                    "target_file_path": str(
                        target_file_path
                        if "target_file_path" in locals()
                        else target_dir
                    ),
                    "error": str(e),
                },
            )
            # Wrap low-level I/O or serialization error into custom StorageError
            raise StorageError(error_msg) from e

        except Exception as e:
            error_msg = (
                f"Unexpected failure writing local dataset '{dataset_name}': {e}"
            )
            logger.error(
                "Unexpected failure writing local dataset",
                exc_info=True,
                extra={
                    "dataset_name": dataset_name,
                    "error": str(e),
                },
            )
            raise StorageError(error_msg) from e

        return str(target_file_path.resolve())
