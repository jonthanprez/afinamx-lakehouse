"""Factory module for instantiating the appropriate StorageWriter.

Dynamically switches between local file system storage (DEV) and AWS S3 (PROD).
"""

from typing import Any, Optional

from src.common.logger import get_logger
from src.ingest.config import config
from src.ingest.storage.base import BaseStorageWriter
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter

logger = get_logger(__name__)


class StorageWriterFactory:
    """Factory responsible for resolving and returning required storage writer instances."""

    @staticmethod
    def get_storage_writer(
        storage_type: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseStorageWriter:
        """Returns an instance of LocalStorageWriter or S3StorageWriter.

        :param storage_type: Explicit storage target ('local', 'dev', 's3', 'prod').
                             If None, defaults to config.environment.
        :param kwargs: Optional keyword arguments passed to the concrete writer constructor
                       (e.g., base_dir, bucket_name, aws_conn_id, prefix, s3_client).
        :return: Concrete instance inheriting from BaseStorageWriter.
        :raises ValueError: If an unsupported environment or target type is specified.
        """
        raw_target = storage_type or config.environment
        stype = raw_target.strip().lower()

        logger.info(
            "Resolving StorageWriter for target",
            extra={"storage_type": stype, "raw_target": raw_target},
        )

        if stype in ["local", "dev"]:
            base_dir = kwargs.get("base_dir", config.bronze_dir)
            return LocalStorageWriter(base_dir=base_dir)

        if stype in ["s3", "prod"]:
            bucket_name = kwargs.get("bucket_name", config.s3_bucket_name)
            aws_conn_id = kwargs.get("aws_conn_id", config.aws_conn_id)
            prefix = kwargs.get("prefix", "bronze")
            s3_client = kwargs.get("s3_client")
            return S3StorageWriter(
                bucket_name=bucket_name,
                aws_conn_id=aws_conn_id,
                prefix=prefix,
                s3_client=s3_client,
            )

        raise ValueError(
            f"Unsupported storage type or environment: '{raw_target}'. "
            "Allowed values: 'local', 'dev', 's3', 'prod'."
        )
