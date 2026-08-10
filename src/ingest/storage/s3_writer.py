import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.ingest.config import S3_BUCKET_NAME
from src.ingest.exceptions import StorageError
from src.ingest.storage.base import BaseStorageWriter

logger = logging.getLogger(__name__)


class S3StorageWriter(BaseStorageWriter):
    """Direct AWS S3 storage writer (PROD Environment or Cloud Integration Tests)."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        aws_conn_id: Optional[str] = None,
    ) -> None:
        """Initializes the S3 storage writer.

        :param bucket_name: S3 Bucket name. Defaults to S3_BUCKET_NAME from config.
        :param aws_conn_id: Optional Airflow hook ID if instantiated inside Airflow.
        """
        # Fallback to S3_BUCKET_NAME from config.py if not provided
        self.bucket_name = bucket_name or S3_BUCKET_NAME
        self.s3_client = boto3.client("s3")
        logger.debug(
            "S3StorageWriter initialized with bucket_name: %s", self.bucket_name
        )

    def write(
        self,
        payload: Union[Dict[str, Any], str, bytes],
        dataset_name: str,
        filename: str,
        execution_date: datetime,  # Strict: Required logical execution date
    ) -> str:
        """Writes JSON payload with operational metadata directly to AWS S3.

        :param payload: Data payload dictionary to store.
        :param dataset_name: Dataset entity subfolder (e.g., 'woocommerce').
        :param filename: Target file name (e.g., 'orders.json').
        :param execution_date: Orchestrator timestamp for Hive partitioning.
        :return: Complete s3:// URI path of the written object.
        """
        # 1. Hive partition path driven purely by logical event time
        hive_partition = f"year={execution_date.year}/month={execution_date.month:02d}"

        # S3 Object Key: bronze/<dataset_name>/year=YYYY/month=MM/<filename>
        s3_key = f"bronze/{dataset_name}/{hive_partition}/{filename}"
        s3_uri = f"s3://{self.bucket_name}/{s3_key}"

        logger.info("Writing dataset '%s' to S3 path: %s", dataset_name, s3_uri)

        # 2. Inject operational lakehouse metadata envelope
        enveloped_payload = {
            "_metadata": {
                "execution_date": execution_date.isoformat(),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "dataset_name": dataset_name,
            },
            "data": payload,
        }

        # 3. Serialize to UTF-8 encoded byte array
        json_bytes = json.dumps(enveloped_payload, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )

        # 4. Atomic S3 PutObject execution
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_bytes,
                ContentType="application/json; charset=utf-8",
            )
            logger.info("Successfully wrote S3 object: %s", s3_uri)
        except (ClientError, BotoCoreError) as e:
            error_msg = f"Critical failure writing object to AWS S3 ({s3_uri}): {e}"
            logger.error(error_msg, exc_info=True)
            # Re-raise wrapped in our custom StorageError
            raise StorageError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected failure writing dataset '{dataset_name}' to S3 ({s3_uri}): {e}"
            logger.error(error_msg, exc_info=True)
            raise StorageError(error_msg) from e

        return s3_uri
