"""Data models and type definitions for WooCommerce ingestion and simulation."""

from typing import TypedDict


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


class Order(TypedDict):
    id: int
    status: str
    currency: str
    date_created: str
    total: str
    payment_method: str
    customer: Customer
    line_items: list[LineItem]


class SimulatorState(TypedDict):
    last_order_id: int
    updated_at: str
