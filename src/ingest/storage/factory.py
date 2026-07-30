"""Factory module for instantiating the appropriate StorageWriter.

Dynamically switches between local file system storage (DEV) and AWS S3 (PROD).
"""

import logging
from typing import Optional

from src.ingest import config
from src.ingest.storage.base import BaseStorageWriter
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter

logger = logging.getLogger(__name__)


class StorageWriterFactory:
    """Factory responsible for resolving and returning required storage writer instances."""

    @staticmethod
    def get_storage_writer(
        storage_type: Optional[str] = None,
    ) -> BaseStorageWriter:
        """Returns an instance of LocalStorageWriter or S3StorageWriter.

        :param storage_type: Explicit storage target ('local', 'dev', 's3', 'prod').
                             If None, defaults to config.ENVIRONMENT.
        :return: Concrete instance inheriting from BaseStorageWriter.
        :raises ValueError: If an unsupported environment or target type is specified.
        """
        raw_target = storage_type or config.ENVIRONMENT
        stype = raw_target.strip().lower()

        logger.info(f"Resolving StorageWriter for target: '{stype}'")

        if stype in ["local", "dev"]:
            return LocalStorageWriter(base_dir=config.BRONZE_DIR)

        if stype in ["s3", "prod"]:
            aws_conn_id = getattr(config, "AWS_CONN_ID", None)
            return S3StorageWriter(
                bucket_name=config.S3_BUCKET_NAME,
                aws_conn_id=aws_conn_id,
            )

        raise ValueError(
            f"Unsupported storage type or environment: '{raw_target}'. "
            "Allowed values: 'local', 'dev', 's3', 'prod'."
        )
