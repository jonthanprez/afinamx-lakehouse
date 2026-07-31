"""Module for managing WooCommerce ingestion state and extraction checkpoints.

Guarantees atomic reading and updating of the extraction cursor (last_order_id and
last_updated_at) to ensure incremental, idempotent executions.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.ingest import config

logger = logging.getLogger(__name__)


class WooCommerceStateManager:
    """Persistence manager for the WooCommerce extraction state/cursor."""

    def __init__(self, state_file_path: Optional[Path] = None) -> None:
        """Initializes the state manager.

        :param state_file_path: Custom path to state JSON file. Defaults to config.WOOCOMMERCE_STATE_FILE.
        """
        self.state_file_path = state_file_path or config.WOOCOMMERCE_STATE_FILE

    def load_state(self) -> Dict[str, Any]:
        """Loads the last recorded state from metadata storage.

        :return: Dictionary containing state schema (last_order_id, last_updated_at, etc.).
        :raises RuntimeError: If state file exists but is corrupted (prevents cursor reset).
        """
        if not self.state_file_path.exists():
            logger.info(
                f"No previous state file found at '{self.state_file_path}'. "
                "Initializing default state."
            )
            return self._get_default_state()

        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                logger.info(
                    f"State loaded successfully from '{self.state_file_path}': "
                    f"last_order_id={state_data.get('last_order_id')}"
                )
                return state_data

        except (json.JSONDecodeError, OSError) as e:
            logger.critical(
                f"State file '{self.state_file_path}' exists but is corrupted or unreadable: {e}. "
                "Halting pipeline execution to prevent illegal cursor resets."
            )
            raise RuntimeError(
                f"Corrupted ingestion state file at '{self.state_file_path}'."
            ) from e

    def register_failure(self, error_message: str) -> int:
        """Records a failure in the state, incrementing the Circuit Breaker counter.

        :param error_message: Error message to record.
        :return: Number of consecutive failures after incrementing the counter.
        """
        state = self.load_state()
        failures = state.get("consecutive_failures", 0) + 1

        state["consecutive_failures"] = failures
        state["last_execution_status"] = "FAILED"
        state["last_error_message"] = str(error_message)
        state["last_execution_timestamp"] = datetime.now(timezone.utc).isoformat()

        self._save_state(state)
        logger.warning(f"Failure recorded in StateManager. Current counter: {failures}")
        return failures

    def update_state(
        self,
        last_order_id: int,
        last_updated_at: Optional[str] = None,
        status: str = "SUCCESS",
    ) -> Dict[str, Any]:
        """Atomically updates and persists state after a successful batch ingestion.

        :param last_order_id: Highest processed order ID in the batch.
        :param last_updated_at: UTC ISO-8601 timestamp of the latest processed change.
        :param status: Execution operational status ('SUCCESS', 'FAILED', etc.).
        :return: Updated state dictionary.
        """
        current_state = (
            self.load_state()
            if self.state_file_path.exists()
            else self._get_default_state()
        )

        # Enforce monotonic cursor advancement
        current_max_id = current_state.get("last_order_id", 0)
        if last_order_id < current_max_id:
            logger.warning(
                f"Provided last_order_id ({last_order_id}) is smaller than current state "
                f"({current_max_id}). Retaining higher cursor id."
            )
            last_order_id = current_max_id

        current_time = datetime.now(timezone.utc).isoformat()
        new_state: Dict[str, Any] = {
            "dataset_name": "woocommerce",
            "last_order_id": last_order_id,
            "last_updated_at": last_updated_at or current_time,
            "last_execution_timestamp": current_time,
            "last_execution_status": status,
            "consecutive_failures": 0,
            "last_error_message": None,
        }

        self._save_state(new_state)
        return new_state

    def _save_state(self, state_data: Dict[str, Any]) -> None:
        """Writes state dictionary safely to disk via temp file replacement.

        :param state_data: State dictionary to serialize.
        """
        try:
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic swap via temporary file
            temp_file = self.state_file_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

            temp_file.replace(self.state_file_path)
            logger.info(
                f"State updated atomically at '{self.state_file_path}': "
                f"last_order_id={state_data.get('last_order_id')}"
            )
        except Exception as e:
            logger.critical(
                f"Critical error saving state file at '{self.state_file_path}': {e}"
            )
            raise RuntimeError(f"I/O error updating ingestion checkpoint: {e}") from e

    def _get_default_state(self) -> Dict[str, Any]:
        """Generates initial default state schema."""
        default_start_id = getattr(config, "DEFAULT_START_ORDER_ID", 1000)
        return {
            "dataset_name": "woocommerce",
            "last_order_id": default_start_id,
            "last_updated_at": None,
            "last_execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_execution_status": "INITIALIZED",
            "consecutive_failures": 0,
            "last_error_message": None,
        }
