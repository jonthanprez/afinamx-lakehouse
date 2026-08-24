from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Union


class BaseStorageWriter(ABC):
    """Abstract interface for the persistence layer in the Bronze layer.

    Ensures that any destination (Local or AWS S3) adheres to the write
    contract and Hive-style partitioning.
    """

    @abstractmethod
    def write(
        self,
        payload: Union[Dict[str, Any], str, bytes],
        dataset_name: str,
        filename: str,
        execution_date: datetime,
    ) -> str:
        """Writes a file to the Bronze layer using Hive partitioning.

        :param payload: Data to persist (Dictionary, JSON string, or bytes).
        :param dataset_name: Name of the source/dataset (e.g., 'woocommerce').
        :param filename: Name of the output file (e.g., 'orders_batch_101.json').
        :param execution_date: Date for Hive partitions (year=YYYY/month=MM/day=DD).
        :return: Full URI path of the saved file's location (e.g., 's3://...').
        """
        pass
