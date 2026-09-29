"""Unit tests verifying structured JSON logging across src.ingest.storage modules."""

import io
import json
import logging
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure boto3 and botocore are available (or mocked) before importing S3StorageWriter
if "boto3" not in sys.modules:
    mock_boto3 = MagicMock()
    mock_botocore = MagicMock()
    mock_botocore_exceptions = MagicMock()
    mock_botocore_exceptions.BotoCoreError = Exception
    mock_botocore_exceptions.ClientError = Exception
    mock_botocore.exceptions = mock_botocore_exceptions
    sys.modules["boto3"] = mock_boto3
    sys.modules["botocore"] = mock_botocore
    sys.modules["botocore.exceptions"] = mock_botocore_exceptions

from src.common.logger import setup_logging
from src.ingest.storage.factory import StorageWriterFactory
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter


class TestStorageStructuredLogging(unittest.TestCase):
    """Test suite for structured JSON logs in storage components."""

    def setUp(self):
        self.stream = io.StringIO()
        setup_logging(level=logging.DEBUG, stream=self.stream)

    def _get_log_records(self):
        """Parse all emitted JSON log lines."""
        lines = [line for line in self.stream.getvalue().split("\n") if line.strip()]
        return [json.loads(line) for line in lines]

    def test_local_storage_writer_emits_structured_logs(self):
        """Verify LocalStorageWriter emits structured JSON logs during initialization and writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = LocalStorageWriter(base_dir=tmpdir)
            exec_date = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

            writer.write(
                payload={"order_id": 101, "total": 99.99},
                dataset_name="woocommerce",
                filename="orders.json",
                execution_date=exec_date,
            )

        logs = self._get_log_records()
        self.assertTrue(len(logs) >= 2)

        # Verify initialization log
        init_log = next(
            log for log in logs if log["message"] == "LocalStorageWriter initialized"
        )
        self.assertEqual(init_log["level"], "DEBUG")
        self.assertIn("base_dir", init_log)

        # Verify write log
        write_log = next(
            log for log in logs if log["message"] == "Writing local dataset to path"
        )
        self.assertEqual(write_log["level"], "INFO")
        self.assertEqual(write_log["dataset_name"], "woocommerce")
        self.assertEqual(write_log["execution_date"], exec_date.isoformat())
        self.assertIn("target_file_path", write_log)

        # Verify success log
        success_log = next(
            log for log in logs if log["message"] == "Successfully wrote local file"
        )
        self.assertEqual(success_log["level"], "INFO")
        self.assertEqual(success_log["dataset_name"], "woocommerce")

    def test_s3_storage_writer_emits_structured_logs(self):
        """Verify S3StorageWriter emits structured JSON logs with S3 metadata."""
        mock_s3 = MagicMock()
        with patch("boto3.client", return_value=mock_s3):
            writer = S3StorageWriter(bucket_name="my-test-bucket")
            exec_date = datetime(2026, 9, 29, 14, 0, 0, tzinfo=timezone.utc)

            s3_uri = writer.write(
                payload={"customer_id": 42},
                dataset_name="customers",
                filename="batch_01.json",
                execution_date=exec_date,
            )

        logs = self._get_log_records()

        # Check write log
        write_log = next(
            log for log in logs if log["message"] == "Writing dataset to S3"
        )
        self.assertEqual(write_log["level"], "INFO")
        self.assertEqual(write_log["dataset_name"], "customers")
        self.assertEqual(write_log["bucket_name"], "my-test-bucket")
        self.assertEqual(write_log["s3_uri"], s3_uri)

        # Check success log
        success_log = next(
            log for log in logs if log["message"] == "Successfully wrote S3 object"
        )
        self.assertEqual(success_log["level"], "INFO")
        self.assertEqual(
            success_log["s3_key"], "bronze/customers/year=2026/month=09/batch_01.json"
        )

    def test_storage_writer_factory_emits_structured_logs(self):
        """Verify StorageWriterFactory emits structured JSON logs with target type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.ingest.config.BRONZE_DIR", Path(tmpdir)):
                StorageWriterFactory.get_storage_writer("local")

        logs = self._get_log_records()
        factory_log = next(
            log
            for log in logs
            if log["message"] == "Resolving StorageWriter for target"
        )
        self.assertEqual(factory_log["level"], "INFO")
        self.assertEqual(factory_log["storage_type"], "local")
        self.assertEqual(factory_log["raw_target"], "local")


if __name__ == "__main__":
    unittest.main()
