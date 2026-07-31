"""Resilient API Client for WooCommerce Bronze Layer Ingestion.

Supports the Double Switch (Data Provider: Simulator vs Real API; Storage: Local vs S3)
and implements enterprise resilience patterns:
1. Exponential Backoff Retries, 2. Persistent Circuit Breaker State, 3. Native Rate Limiting,
and 4. Auditability.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.ingest import config
from src.ingest.storage.base import BaseStorageWriter
from src.ingest.storage.factory import StorageWriterFactory
from src.ingest.woocommerce.data_simulator import WooCommerceDataSimulator
from src.ingest.woocommerce.state_manager import WooCommerceStateManager

logger = logging.getLogger(__name__)


class WooCommerceCircuitBreakerError(Exception):
    """Raised when the Circuit Breaker is open due to sustained historical failures."""

    pass


class WooCommerceAPIClient:
    """Orchestrator client for extracting and ingesting WooCommerce orders."""

    def __init__(
        self,
        use_simulator: Optional[bool] = None,
        storage_writer: Optional[BaseStorageWriter] = None,
        state_manager: Optional[WooCommerceStateManager] = None,
        max_circuit_failures: int = 5,
    ) -> None:
        """Initializes WooCommerce API client."""
        # Switch 1: Data Provider (Simulator vs Real API)
        if use_simulator is not None:
            self.use_simulator = use_simulator
        else:
            self.use_simulator = getattr(config, "USE_SIMULATOR", True)

        # Switch 2: Persistence (Injected or via Factory)
        self.storage_writer = (
            storage_writer or StorageWriterFactory.get_storage_writer()
        )
        self.state_manager = state_manager or WooCommerceStateManager()

        # Circuit Breaker Threshold
        self.max_circuit_failures = max_circuit_failures

        # Local Data Simulator
        self.simulator = WooCommerceDataSimulator() if self.use_simulator else None

        # Resilient HTTP Session
        self.http_session = self._build_resilient_session()

    def extract_and_load(
        self,
        batch_size: int = 50,
        execution_id: Optional[str] = None,
        execution_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Orchestrates incremental extraction from checkpoint and persistence to Bronze."""
        exec_id = execution_id or f"exec_{uuid.uuid4().hex[:8]}"
        ref_date = execution_date or datetime.now(timezone.utc)

        # 1. Load Checkpoint State
        current_state = self.state_manager.load_state()
        last_order_id = current_state.get("last_order_id", 1000)
        last_updated_at = current_state.get("last_updated_at")
        consecutive_failures = current_state.get("consecutive_failures", 0)

        # Fail-Fast Circuit Breaker Guard Check
        if consecutive_failures >= self.max_circuit_failures:
            logger.critical(
                f"CIRCUIT BREAKER OPEN in State ({consecutive_failures}/{self.max_circuit_failures} failures). "
                "Aborting execution without firing network requests."
            )
            raise WooCommerceCircuitBreakerError(
                f"Circuit breaker open due to {consecutive_failures} historical failures. "
                f"Reset state file at '{self.state_manager.state_file_path}' to resume."
            )

        logger.info(
            f"Starting WooCommerce ingestion [ID: {exec_id}]. "
            f"Source: {'Local Simulator' if self.use_simulator else 'Real API'}. "
            f"Storage: {self.storage_writer.__class__.__name__} | Watermark ID: {last_order_id}"
        )

        # 2. Extract Data according to Data Provider Switch
        try:
            if self.use_simulator:
                raw_orders, new_last_id, max_ts = self._fetch_from_simulator(
                    last_order_id=last_order_id, count=batch_size
                )
            else:
                raw_orders, new_last_id, max_ts = self._fetch_from_real_api(
                    last_order_id=last_order_id,
                    last_updated_at=last_updated_at,
                    batch_size=batch_size,
                )
        except Exception as e:
            # Persist failure counter in state file
            failures = self.state_manager.register_failure(str(e))
            logger.error(
                f"Ingestion task failed. Updated persistent failure counter to: {failures}"
            )
            raise

        # Handle Empty Result
        if not raw_orders:
            logger.info(f"No new orders found beyond ID {last_order_id}.")
            return {
                "status": "SKIPPED",
                "execution_id": exec_id,
                "records_ingested": 0,
                "last_order_id": last_order_id,
            }

        # 3. Create Audit Envelope
        bronze_envelope = {
            "metadata": {
                "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                "source_system": "woocommerce",
                "use_simulator": self.use_simulator,
                "execution_id": exec_id,
                "record_count": len(raw_orders),
                "extracted_range": {
                    "start_order_id": last_order_id + 1,
                    "end_order_id": new_last_id,
                },
            },
            "payload": raw_orders,
        }

        filename = f"batch_orders_{last_order_id + 1}_to_{new_last_id}.json"

        # 4. Write Payload to Bronze
        storage_result = self.storage_writer.write(
            payload=bronze_envelope,
            dataset_name="woocommerce",
            filename=filename,
            execution_date=ref_date,
        )

        # 5. Atomic State Checkpoint Update (Resets consecutive_failures to 0)
        new_watermark_ts = max_ts or datetime.now(timezone.utc).isoformat()
        self.state_manager.update_state(
            last_order_id=new_last_id,
            last_updated_at=new_watermark_ts,
            status="SUCCESS",
        )

        logger.info(
            f"Ingestion finished successfully. {len(raw_orders)} orders stored in: {storage_result}"
        )

        return {
            "status": "SUCCESS",
            "execution_id": exec_id,
            "records_ingested": len(raw_orders),
            "last_order_id": new_last_id,
            "storage_location": storage_result,
        }

    def _fetch_from_simulator(
        self, last_order_id: int, count: int
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Generates synthetic orders using the local simulator."""
        logger.info(f"Generating {count} simulated orders after ID={last_order_id}...")
        orders = self.simulator.generate_orders_batch(
            start_order_id=last_order_id + 1, count=count
        )
        max_id = max((o["id"] for o in orders), default=last_order_id)
        max_ts = max(
            (o.get("date_modified_gmt") for o in orders if o.get("date_modified_gmt")),
            default=None,
        )
        return orders, max_id, max_ts

    def _fetch_from_real_api(
        self,
        last_order_id: int,
        last_updated_at: Optional[str],
        batch_size: int,
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Extracts orders from WooCommerce API using ISO timestamp pagination."""
        api_url = getattr(
            config, "WOOCOMMERCE_API_URL", "https://tienda.example.com/wp-json/wc/v3"
        )
        endpoint = f"{api_url.rstrip('/')}/orders"

        params: Dict[str, Any] = {
            "page": 1,
            "per_page": batch_size,
            "order": "asc",
            "orderby": "date",
        }

        if last_updated_at:
            params["after"] = last_updated_at

        auth = (
            getattr(config, "WOOCOMMERCE_CONSUMER_KEY", ""),
            getattr(config, "WOOCOMMERCE_CONSUMER_SECRET", ""),
        )

        logger.info(f"Querying WooCommerce API: GET {endpoint} | params={params}")

        response = self.http_session.get(
            endpoint, params=params, auth=auth, timeout=(5.0, 30.0)
        )
        response.raise_for_status()
        orders = response.json()

        if not isinstance(orders, list):
            raise ValueError(
                f"Unexpected API response format: expected list, got {type(orders)}"
            )

        # Disambiguate orders with identical second-timestamps using order ID
        filtered_orders = [o for o in orders if o.get("id", 0) > last_order_id]
        max_id = max((o["id"] for o in filtered_orders), default=last_order_id)
        max_ts = max(
            (
                o.get("date_modified_gmt")
                for o in filtered_orders
                if o.get("date_modified_gmt")
            ),
            default=last_updated_at,
        )

        return filtered_orders, max_id, max_ts

    def _build_resilient_session(self) -> requests.Session:
        """Configures HTTP Session with Exponential Backoff and Native 429 Rate Limiting."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,  # Request-level HTTP retries
            backoff_factor=2,  # Wait 2s, 4s, 8s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,  # Native HTTP 429 Retry-After handling
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
