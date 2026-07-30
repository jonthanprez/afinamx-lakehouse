from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Union


class BaseStorageWriter(ABC):
    """Interfaz abstracta para la capa de persistencia en capa Bronze.

    Garantiza que cualquier destino (Local o AWS S3) respete el contrato
    de escritura y el particionamiento estilo Hive.
    """

    @abstractmethod
    def write(
        self,
        payload: Union[Dict[str, Any], str, bytes],
        dataset_name: str,
        filename: str,
        execution_date: Optional[datetime] = None,
    ) -> str:
        """Escribe un archivo en la capa Bronze usando particionado Hive.

        :param payload: Datos a persistir (Diccionario, String JSON o Bytes).
        :param dataset_name: Nombre de la fuente/dataset (ej. 'woocommerce').
        :param filename: Nombre del archivo de salida (ej. 'orders_batch_101.json').
        :param execution_date: Fecha para particiones Hive (año=YYYY/mes=MM/dia=DD).
                              Si es None, debe tomar UTC actual.
        :return: Ruta URI completa de la ubicación del archivo guardado (ej. 's3://...').
        """
        pass
