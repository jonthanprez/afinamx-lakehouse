from src.ingest.config import ENVIRONMENT
from src.ingest.storage.base import BaseStorageWriter
from src.ingest.storage.local_writer import LocalStorageWriter
from src.ingest.storage.s3_writer import S3StorageWriter


class StorageWriterFactory:
    @staticmethod
    def get_writer() -> BaseStorageWriter:
        if ENVIRONMENT == "prod":
            return S3StorageWriter()
        return LocalStorageWriter()
