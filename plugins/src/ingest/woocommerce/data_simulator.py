import random
import logging
import json
import os
from datetime import datetime
from faker import Faker

from src.ingest.woocommerce.products import PRODUCTS_CATALOG, METHODS_PAYMENT, ORDER_STATUS

logger = logging.getLogger("airflow.task")
fake = Faker(['es_MX'])

def generate_json_order(order_id: int) -> dict:
    