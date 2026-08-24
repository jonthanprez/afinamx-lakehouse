"""Data models and type definitions for WooCommerce ingestion and simulation."""

from typing import TypedDict


class Product(TypedDict):
    id: int
    sku: str
    name: str
    brand: str
    category: str
    price: float
    cost: float


class Customer(TypedDict):
    id: int
    first_name: str
    last_name: str
    email: str
    address: str
    city: str
    state: str
    postcode: str
    country: str


class LineItem(TypedDict):
    product_id: int
    sku: str
    name: str
    brand: str
    category: str
    quantity: int
    unit_price: str
    total: str


class Order(TypedDict, total=False):
    id: int
    status: str
    currency: str
    date_created: str
    date_modified_gmt: str
    total: str
    payment_method: str
    customer: Customer
    line_items: list[LineItem]


class SimulatorState(TypedDict):
    last_order_id: int
    updated_at: str
