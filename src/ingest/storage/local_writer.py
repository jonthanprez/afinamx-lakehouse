"""Data persistence writer for the local file system (DEV Environment)."""

from datetime import datetime
import os
from pathlib import Path
import tempfile
from typing import Optional, Union

from src.common.logger import get_logger
from src.ingest.config import config
from src.ingest.exceptions import StorageError
from src.ingest.storage.base import BaseStorageWriter

logger = get_logger(__name__)


class LocalStorageWriter(BaseStorageWriter):
    """Data writer for the local file system using POSIX atomic renames."""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None) -> None:
        """Initializes the LocalStorageWriter.

        :param base_dir: Base directory path. Defaults to config.bronze_dir.
        """
        self.base_dir = Path(base_dir) if base_dir else Path(config.bronze_dir)
        logger.debug(
            "LocalStorageWriter initialized",
            extra={"base_dir": str(self.base_dir)},
        )

    def _persist(
        self,
        relative_path: str,
        data: bytes,
        dataset_name: str,
        execution_date: datetime,
    ) -> str:
        """Persists payload bytes to disk using atomic temporary file replacement.

        :param relative_path: Canonical Hive path (<dataset>/year=YYYY/month=MM/<file>).
        :param data: UTF-8 encoded bytes ready to write.
        :param dataset_name: Dataset name for context logging.
        :param execution_date: Logical run timestamp.
        :return: Absolute file path in standardized POSIX format (forward slashes).
        :raises StorageError: If disk I/O, permissions, or rename operations fail.
        """
        target_file_path = self.base_dir / relative_path
        target_dir = target_file_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Writing local dataset to path",
            extra={
                "dataset_name": dataset_name,
                "target_file_path": target_file_path.as_posix(),
                "execution_date": execution_date.isoformat(),
            },
        )

        temp_path: Optional[str] = None
        write_success = False

        try:
            # 1. Atomic write: write binary bytes to hidden temp file in target directory
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target_dir,
                delete=False,
                prefix=".tmp_",
            ) as tmp_file:
                tmp_file.write(data)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())  # Ensure physical disk flush
                temp_path = tmp_file.name

            # 2. OS Atomic swap
            os.replace(temp_path, target_file_path)
            write_success = True

            logger.info(
                "Successfully wrote local file",
                extra={
                    "dataset_name": dataset_name,
                    "target_file_path": target_file_path.as_posix(),
                },
            )
            # Standardized POSIX path format (forward slashes across platforms)
            return target_file_path.resolve().as_posix()

        except (OSError, PermissionError) as e:
            error_msg = f"Failed to write local dataset '{dataset_name}' to {target_file_path.as_posix()}: {e}"
            logger.error(
                "Failed to write local dataset",
                exc_info=True,
                extra={
                    "dataset_name": dataset_name,
                    "target_file_path": target_file_path.as_posix(),
                    "error": str(e),
                },
            )
            raise StorageError(error_msg) from e

        except Exception as e:
            error_msg = (
                f"Unexpected failure writing local dataset '{dataset_name}': {e}"
            )
            logger.error(
                "Unexpected failure writing local dataset",
                exc_info=True,
                extra={"dataset_name": dataset_name, "error": str(e)},
            )
            raise StorageError(error_msg) from e

        finally:
            # Guaranteed cleanup: delete temporary file if atomic rename was not completed
            if not write_success and temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.debug(
                        "Cleaned up orphaned temporary file",
                        extra={"temp_path": temp_path},
                    )
                except OSError:
                    pass
