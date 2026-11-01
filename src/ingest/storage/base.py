"""Base persistence contract and Template Method implementation for Lakehouse Bronze storage."""

from abc import ABC, abstractmethod
from datetime import datetime
import json
from typing import Any, Dict, List, Optional, Union

from src.common.logger import get_logger

logger = get_logger(__name__)


class BaseStorageWriter(ABC):
    """Abstract template for Bronze layer persistence writers.

    Enforces Medallion architecture conventions:
    1. Canonical Hive-style partitioning (year=YYYY/month=MM or year=YYYY/month=MM/day=DD).
    2. Robust payload serialization (compact JSON by default, resilient with default=str).
    3. Input validation prior to physical I/O execution.
    """

    # --------------------------------------------------------------------------
    # 1. HIVE PARTITIONING & PATH CANONICAL RULES (Centralized Enforcement)
    # --------------------------------------------------------------------------
    @staticmethod
    def build_hive_partition(
        execution_date: datetime,
        include_day: bool = False,
    ) -> str:
        """Constructs canonical Hive partition directory path.

        :param execution_date: Datetime timestamp representing logical run execution.
        :param include_day: Whether to include 'day=DD' granularity (recommended for high volumes).
        :return: Partition path string e.g. 'year=2026/month=08' or 'year=2026/month=08/day=15'.
        :raises ValueError: If execution_date is not a valid datetime instance.
        """
        if not isinstance(execution_date, datetime):
            raise ValueError(
                f"execution_date must be a datetime instance, got {type(execution_date).__name__}"
            )

        base_partition = f"year={execution_date.year}/month={execution_date.month:02d}"
        if include_day:
            return f"{base_partition}/day={execution_date.day:02d}"
        return base_partition

    @classmethod
    def build_relative_path(
        cls,
        dataset_name: str,
        filename: str,
        execution_date: datetime,
        include_day: bool = False,
    ) -> str:
        """Constructs the canonical relative storage path.

        Format: <dataset_name>/year=YYYY/month=MM[/day=DD]/<filename>

        :param dataset_name: Name of the dataset/subsystem (e.g., 'woocommerce').
        :param filename: Target file name (e.g., 'orders_batch_101.json').
        :param execution_date: Datetime for partition computation.
        :param include_day: Whether to append day partition level.
        :return: Standardized relative storage key/path.
        """
        clean_dataset = dataset_name.strip("/ ")
        clean_filename = filename.strip("/ ")

        if not clean_dataset:
            raise ValueError("dataset_name cannot be empty or whitespace.")
        if not clean_filename:
            raise ValueError("filename cannot be empty or whitespace.")

        hive_partition = cls.build_hive_partition(
            execution_date, include_day=include_day
        )
        return f"{clean_dataset}/{hive_partition}/{clean_filename}"

    # --------------------------------------------------------------------------
    # 2. PAYLOAD SERIALIZATION ENGINE
    # --------------------------------------------------------------------------
    @staticmethod
    def serialize_payload(
        payload: Union[Dict[str, Any], List[Any], str, bytes, Any],
        indent: Optional[int] = None,
    ) -> bytes:
        """Serializes supported payload types into standardized UTF-8 encoded bytes.

        By default produces compact JSON (no indentation, minimal separators)
        to optimize storage cost, network transfer, and distributed analytical engines.

        :param payload: Input data structure (Pydantic model, dict, list, str, bytes).
        :param indent: Optional indentation level for human-readable output (default: None).
        :return: UTF-8 encoded byte array ready for network transfer or disk flush.
        :raises ValueError: If payload is None.
        :raises TypeError: If payload cannot be serialized to JSON.
        """
        if payload is None:
            raise ValueError("payload cannot be None.")

        # 1. Pydantic V2 model_dump_json
        if hasattr(payload, "model_dump_json"):
            return payload.model_dump_json(
                by_alias=True,
                indent=indent,
            ).encode("utf-8")

        # 2. Pydantic V2 model_dump fallback
        if hasattr(payload, "model_dump"):
            separators = None if indent is not None else (",", ":")
            return json.dumps(
                payload.model_dump(by_alias=True),
                ensure_ascii=False,
                indent=indent,
                separators=separators,
                default=str,
            ).encode("utf-8")

        # 3. Already bytes
        if isinstance(payload, bytes):
            return payload

        # 4. String / Raw JSON string
        if isinstance(payload, str):
            return payload.encode("utf-8")

        # 5. Native Dict, List, or generic JSON-serializable structures
        separators = None if indent is not None else (",", ":")
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
            default=str,
        ).encode("utf-8")

    # --------------------------------------------------------------------------
    # 3. TEMPLATE METHOD: write
    # --------------------------------------------------------------------------
    def write(
        self,
        payload: Union[Dict[str, Any], List[Any], str, bytes, Any],
        dataset_name: str,
        filename: str,
        execution_date: datetime,
        include_day: bool = False,
        indent: Optional[int] = None,
    ) -> str:
        """Writes a payload to the storage backend enforcing Hive partitioning.

        Orchestrates:
        1. Validation & Relative path resolution (Canonical Hive partition).
        2. Payload serialization to compact/optimized bytes.
        3. Delegation to concrete physical persistence layer (_persist).

        :param payload: Data to persist (Pydantic model, dictionary, list, string, or bytes).
        :param dataset_name: Name of the source/dataset (e.g., 'woocommerce').
        :param filename: Output file name (e.g., 'orders_batch_101.json').
        :param execution_date: Date for Hive partitions (year=YYYY/month=MM[/day=DD]).
        :param include_day: Whether to include day partition (default: False).
        :param indent: Optional indentation spaces (default: None for compact JSON).
        :return: Complete URI/Path of the persisted resource.
        """
        # 1. Canonical relative path with Hive partitioning
        relative_path = self.build_relative_path(
            dataset_name=dataset_name,
            filename=filename,
            execution_date=execution_date,
            include_day=include_day,
        )

        logger.debug(
            "Preparing payload for storage persistence",
            extra={
                "dataset_name": dataset_name,
                "relative_path": relative_path,
                "execution_date": execution_date.isoformat(),
            },
        )

        # 2. Canonical serialization
        data_bytes = self.serialize_payload(payload=payload, indent=indent)

        # 3. Physical persistence delegation
        return self._persist(
            relative_path=relative_path,
            data=data_bytes,
            dataset_name=dataset_name,
            execution_date=execution_date,
        )

    # --------------------------------------------------------------------------
    # 4. PHYSICAL I/O PRIMITIVE (Subclasses must implement)
    # --------------------------------------------------------------------------
    @abstractmethod
    def _persist(
        self,
        relative_path: str,
        data: bytes,
        dataset_name: str,
        execution_date: datetime,
    ) -> str:
        """Physical persistence hook for concrete writers (Disk / S3 / GCS).

        :param relative_path: Canonical relative path (e.g. 'woocommerce/year=2026/month=08/file.json').
        :param data: UTF-8 encoded payload bytes ready for storage.
        :param dataset_name: Contextual dataset name for logging/tagging.
        :param execution_date: Orchestration execution timestamp.
        :return: Absolute physical URI where data was persisted.
        """
        pass
