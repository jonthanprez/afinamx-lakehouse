"""Unit tests verifying structured JSON logging across src.ingest.woocommerce modules."""

import io
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure external dependencies (pydantic, requests, urllib3, faker, boto3) are available or mocked
if "pydantic" not in sys.modules:
    mock_pydantic = MagicMock()

    class MockBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, **kwargs):
            res = {}
            for k, v in self.__dict__.items():
                if hasattr(v, "model_dump"):
                    res[k] = v.model_dump()
                elif isinstance(v, list):
                    res[k] = [
                        item.model_dump() if hasattr(item, "model_dump") else item
                        for item in v
                    ]
                else:
                    res[k] = v
            return res

        def model_dump_json(self, **kwargs):
            return json.dumps(self.model_dump())

        @classmethod
        def model_validate(cls, data):
            if isinstance(data, cls):
                return data
            return cls(**data)

    def mock_field(*args, **kwargs):
        default = kwargs.get("default", None)
        if default is not None:
            return default
        return None

    def mock_config_dict(*args, **kwargs):
        return kwargs

    mock_pydantic.BaseModel = MockBaseModel
    mock_pydantic.Field = mock_field
    mock_pydantic.ConfigDict = mock_config_dict
    sys.modules["pydantic"] = mock_pydantic

if "faker" not in sys.modules:
    mock_faker_mod = MagicMock()
    mock_faker_inst = MagicMock()
    mock_faker_inst.first_name.return_value = "Carlos"
    mock_faker_inst.last_name.return_value = "Hernandez"
    mock_faker_inst.email.return_value = "carlos@example.com"
    mock_faker_inst.street_address.return_value = "Insurgentes Sur 456"
    mock_faker_inst.city.return_value = "CDMX"
    mock_faker_inst.state_abbr.return_value = "CDMX"
    mock_faker_inst.postcode.return_value = "03100"
    mock_faker_mod.Faker.return_value = mock_faker_inst
    sys.modules["faker"] = mock_faker_mod

if "requests" not in sys.modules:
    mock_requests = MagicMock()
    mock_requests_adapters = MagicMock()
    mock_requests.adapters = mock_requests_adapters
    sys.modules["requests"] = mock_requests
    sys.modules["requests.adapters"] = mock_requests_adapters

if "urllib3.util.retry" not in sys.modules:
    mock_urllib3 = MagicMock()
    mock_retry_mod = MagicMock()
    sys.modules["urllib3"] = mock_urllib3
    sys.modules["urllib3.util"] = MagicMock()
    sys.modules["urllib3.util.retry"] = mock_retry_mod

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
from src.ingest.woocommerce.api_client import WooCommerceAPIClient
from src.ingest.woocommerce.data_simulator import WooCommerceDataSimulator
from src.ingest.woocommerce.state_manager import WooCommerceStateManager


class TestWooCommerceStructuredLogging(unittest.TestCase):
    """Test suite for structured JSON logs in WooCommerce components."""

    def setUp(self):
        self.stream = io.StringIO()
        setup_logging(level=logging.DEBUG, stream=self.stream)

    def _get_log_records(self):
        """Parse all emitted JSON log lines."""
        lines = [line for line in self.stream.getvalue().split("\n") if line.strip()]
        return [json.loads(line) for line in lines]

    def test_state_manager_emits_structured_logs(self):
        """Verify WooCommerceStateManager emits structured logs on load, failure, and update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            manager = WooCommerceStateManager(state_file_path=state_file)

            # 1. Default state load
            state = manager.load_state()
            self.assertEqual(state["last_order_id"], 1000)

            # 2. Register failure
            failures = manager.register_failure("API Timeout")
            self.assertEqual(failures, 1)

            # 3. Update state
            manager.update_state(last_order_id=1050, status="SUCCESS")

        logs = self._get_log_records()

        # Check default init log
        init_log = next(
            log for log in logs if log["message"] == "Initializing default state"
        )
        self.assertEqual(init_log["level"], "INFO")
        self.assertIn("state_file", init_log)

        # Check failure log
        fail_log = next(
            log for log in logs if log["message"] == "Failure recorded in StateManager"
        )
        self.assertEqual(fail_log["level"], "WARNING")
        self.assertEqual(fail_log["consecutive_failures"], 1)
        self.assertEqual(fail_log["last_error_message"], "API Timeout")

        # Check update log
        update_logs = [
            log for log in logs if log["message"] == "State updated atomically"
        ]
        self.assertTrue(len(update_logs) >= 1)
        latest_update_log = update_logs[-1]
        self.assertEqual(latest_update_log["level"], "INFO")
        self.assertEqual(latest_update_log["last_order_id"], 1050)
        self.assertEqual(latest_update_log["status"], "SUCCESS")

    def test_data_simulator_emits_structured_logs(self):
        """Verify WooCommerceDataSimulator emits structured logs during initialization and batch generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            customers_file = Path(tmpdir) / "customers.json"

            with (
                patch(
                    "src.ingest.woocommerce.data_simulator.WOOCOMMERCE_STATE_FILE",
                    state_file,
                ),
                patch(
                    "src.ingest.woocommerce.data_simulator.WOOCOMMERCE_CUSTOMERS_FILE",
                    customers_file,
                ),
            ):
                simulator = WooCommerceDataSimulator(customer_pool_size=5)
                batch = simulator.generate_orders_batch(start_order_id=2000, count=3)

        self.assertEqual(len(batch), 3)

        logs = self._get_log_records()

        # Check init log
        init_log = next(
            log
            for log in logs
            if log["message"] == "Initializing WooCommerceDataSimulator"
        )
        self.assertEqual(init_log["level"], "INFO")
        self.assertEqual(init_log["customer_pool_size"], 5)

        # Check batch generation log
        batch_log = next(
            log
            for log in logs
            if log["message"] == "Batch simulation completed successfully"
        )
        self.assertEqual(batch_log["level"], "INFO")
        self.assertEqual(batch_log["records_count"], 3)
        self.assertEqual(batch_log["start_order_id"], 2000)
        self.assertEqual(batch_log["end_order_id"], 2002)

    def test_api_client_emits_structured_logs(self):
        """Verify WooCommerceAPIClient emits structured logs during full extract_and_load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            customers_file = Path(tmpdir) / "customers.json"
            bronze_dir = Path(tmpdir) / "bronze"

            with (
                patch(
                    "src.ingest.woocommerce.data_simulator.WOOCOMMERCE_STATE_FILE",
                    state_file,
                ),
                patch(
                    "src.ingest.woocommerce.data_simulator.WOOCOMMERCE_CUSTOMERS_FILE",
                    customers_file,
                ),
                patch(
                    "src.ingest.woocommerce.state_manager.config.WOOCOMMERCE_STATE_FILE",
                    state_file,
                ),
                patch("src.ingest.config.BRONZE_DIR", bronze_dir),
            ):
                state_mgr = WooCommerceStateManager(state_file_path=state_file)
                mock_writer = MagicMock()
                mock_writer.write.return_value = "/tmp/bronze/test.json"

                client = WooCommerceAPIClient(
                    use_simulator=True,
                    storage_writer=mock_writer,
                    state_manager=state_mgr,
                )
                result = client.extract_and_load(batch_size=2)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["records_ingested"], 2)

        logs = self._get_log_records()

        # Check ingestion start log
        start_log = next(
            log for log in logs if log["message"] == "Starting WooCommerce ingestion"
        )
        self.assertEqual(start_log["level"], "INFO")
        self.assertEqual(start_log["source"], "simulator")
        self.assertEqual(start_log["batch_size"], 2)

        # Check ingestion finished log
        finish_log = next(
            log for log in logs if log["message"] == "Ingestion finished successfully"
        )
        self.assertEqual(finish_log["level"], "INFO")
        self.assertEqual(finish_log["records_ingested"], 2)
        self.assertIn("execution_id", finish_log)


if __name__ == "__main__":
    unittest.main()
