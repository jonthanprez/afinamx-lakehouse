"""Direct AWS S3 storage writer for the Bronze layer (PROD Environment)."""

from datetime import datetime
import mimetypes
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.common.logger import get_logger
from src.ingest.config import config
from src.ingest.exceptions import StorageError
from src.ingest.storage.base import BaseStorageWriter

logger = get_logger(__name__)


class S3StorageWriter(BaseStorageWriter):
    """Direct AWS S3 storage writer executing PutObject operations."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        aws_conn_id: Optional[str] = None,
        prefix: str = "bronze",
        s3_client: Optional[Any] = None,
    ) -> None:
        """Initializes the S3 storage writer.

        :param bucket_name: S3 Bucket name. Defaults to S3_BUCKET_NAME from config.
        :param aws_conn_id: Optional Airflow hook ID if instantiated inside Airflow.
        :param prefix: Medallion layer prefix in S3 (default: 'bronze').
        :param s3_client: Optional injected boto3 S3 client (e.g. for testing/moto).
        :raises ValueError: If bucket_name is empty or None.
        """
        resolved_bucket = bucket_name or config.s3_bucket_name
        if not resolved_bucket or not str(resolved_bucket).strip():
            raise ValueError("bucket_name cannot be empty or None.")

        self.bucket_name = str(resolved_bucket).strip()
        self.aws_conn_id = aws_conn_id
        self.prefix = prefix.strip("/")

        # Dependency injection or resolution via Airflow / Boto3
        if s3_client is not None:
            self.s3_client = s3_client
        elif self.aws_conn_id:
            self.s3_client = self._resolve_airflow_client(self.aws_conn_id)
        else:
            self.s3_client = boto3.client("s3")

        logger.debug(
            "S3StorageWriter initialized",
            extra={
                "bucket_name": self.bucket_name,
                "prefix": self.prefix,
                "aws_conn_id": self.aws_conn_id,
            },
        )

    @staticmethod
    def _resolve_airflow_client(conn_id: str) -> Any:
        """Resolves S3 client from Airflow Connection if available, otherwise falls back to boto3."""
        try:
            from airflow.providers.amazon.aws.hooks.s3 import S3Hook

            return S3Hook(aws_conn_id=conn_id).get_conn()
        except ImportError:
            logger.warning(
                "Airflow AWS provider not installed; falling back to default boto3.client('s3')"
            )
            return boto3.client("s3")

    @staticmethod
    def _detect_content_type(relative_path: str) -> str:
        """Infers appropriate HTTP Content-Type based on file extension."""
        if relative_path.endswith(".json"):
            return "application/json; charset=utf-8"
        if relative_path.endswith((".jsonl", ".ndjson")):
            return "application/x-ndjson; charset=utf-8"
        if relative_path.endswith(".gz"):
            return "application/gzip"
        mime, _ = mimetypes.guess_type(relative_path)
        return mime or "application/octet-stream"

    def _persist(
        self,
        relative_path: str,
        data: bytes,
        dataset_name: str,
        execution_date: datetime,
    ) -> str:
        """Persists payload bytes directly to AWS S3 using PutObject.

        :param relative_path: Canonical Hive path (<dataset>/year=YYYY/month=MM/<file>).
        :param data: UTF-8 encoded bytes ready for upload.
        :param dataset_name: Dataset name for logging.
        :param execution_date: Orchestration execution timestamp.
        :return: Complete s3:// URI string.
        :raises StorageError: If Boto3 client/network operation fails.
        """
        s3_key = f"{self.prefix}/{relative_path}" if self.prefix else relative_path
        s3_uri = f"s3://{self.bucket_name}/{s3_key}"
        content_type = self._detect_content_type(relative_path)

        logger.info(
            "Writing dataset to S3",
            extra={
                "dataset_name": dataset_name,
                "s3_uri": s3_uri,
                "bucket_name": self.bucket_name,
                "s3_key": s3_key,
                "execution_date": execution_date.isoformat(),
            },
        )

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=data,
                ContentType=content_type,
            )
            logger.info(
                "Successfully wrote S3 object",
                extra={
                    "dataset_name": dataset_name,
                    "s3_uri": s3_uri,
                    "bucket_name": self.bucket_name,
                    "s3_key": s3_key,
                },
            )
            return s3_uri

        except (ClientError, BotoCoreError) as e:
            error_msg = f"Critical failure writing object to AWS S3 ({s3_uri}): {e}"
            logger.error(
                "Critical failure writing object to AWS S3",
                exc_info=True,
                extra={
                    "dataset_name": dataset_name,
                    "s3_uri": s3_uri,
                    "bucket_name": self.bucket_name,
                    "s3_key": s3_key,
                    "error": str(e),
                },
            )
            raise StorageError(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected failure writing dataset '{dataset_name}' to S3 ({s3_uri}): {e}"
            logger.error(
                "Unexpected failure writing dataset to S3",
                exc_info=True,
                extra={
                    "dataset_name": dataset_name,
                    "s3_uri": s3_uri,
                    "bucket_name": self.bucket_name,
                    "s3_key": s3_key,
                    "error": str(e),
                },
            )
            raise StorageError(error_msg) from e
