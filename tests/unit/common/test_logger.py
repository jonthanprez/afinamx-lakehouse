"""Unit tests for structured JSON logging in src.common.logger."""

import io
import json
import logging
import unittest
from datetime import datetime, timezone

from src.common.logger import get_logger, setup_logging


class CustomObject:
    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value


class TestJSONLogger(unittest.TestCase):
    """Tests for the JSONFormatter and structured logging setup."""

    def setUp(self):
        self.stream = io.StringIO()
        setup_logging(level=logging.DEBUG, stream=self.stream)

        self.logger = logging.getLogger("test_json_logger")
        self.logger.setLevel(logging.DEBUG)

    def test_json_formatter_emits_valid_json_with_standard_fields(self):
        """Test that logging a basic message produces valid JSON with expected core keys."""
        self.logger.info("Ingestion pipeline started")

        output = self.stream.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["logger"], "test_json_logger")
        self.assertEqual(data["message"], "Ingestion pipeline started")
        self.assertIn("timestamp", data)
        self.assertIn("module", data)
        self.assertIn("func_name", data)
        self.assertIn("line_no", data)

    def test_json_formatter_includes_extra_metadata(self):
        """Test that custom fields in extra={...} are included at the root level."""
        self.logger.info(
            "Batch written to storage",
            extra={
                "dataset_name": "woocommerce_orders",
                "records_count": 150,
                "execution_date": "2026-10-06",
            },
        )

        output = self.stream.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["dataset_name"], "woocommerce_orders")
        self.assertEqual(data["records_count"], 150)
        self.assertEqual(data["execution_date"], "2026-10-06")
        self.assertEqual(data["message"], "Batch written to storage")

    def test_json_formatter_captures_exception_details(self):
        """Test that exceptions logged with exc_info=True include structured traceback data."""
        try:
            raise ValueError("Invalid configuration parameter")
        except ValueError:
            self.logger.error("Encountered unexpected error", exc_info=True)

        output = self.stream.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["level"], "ERROR")
        self.assertEqual(data["message"], "Encountered unexpected error")
        self.assertIn("exception", data)
        self.assertEqual(data["exception"]["type"], "ValueError")
        self.assertEqual(
            data["exception"]["message"], "Invalid configuration parameter"
        )
        self.assertIn("Traceback", data["exception"]["stack_trace"])

    def test_json_formatter_handles_non_serializable_objects_gracefully(self):
        """Test that non-JSON-serializable objects in extra do not raise serialization errors."""
        now = datetime.now(timezone.utc)
        custom_obj = CustomObject("test_metric", 42)

        self.logger.info(
            "Processing custom data",
            extra={
                "timestamp_obj": now,
                "custom_entity": custom_obj,
            },
        )

        output = self.stream.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["timestamp_obj"], now.isoformat())
        self.assertEqual(data["custom_entity"], {"name": "test_metric", "value": 42})

    def test_setup_logging_configures_root_logger(self):
        """Test the setup_logging helper properly binds JSONFormatter to the root logger."""
        test_stream = io.StringIO()
        setup_logging(level="DEBUG", stream=test_stream)

        root_logger = get_logger("root_test")
        root_logger.debug("Testing setup_logging helper", extra={"source": "unit_test"})

        output = test_stream.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["level"], "DEBUG")
        self.assertEqual(data["message"], "Testing setup_logging helper")
        self.assertEqual(data["source"], "unit_test")


if __name__ == "__main__":
    unittest.main()
