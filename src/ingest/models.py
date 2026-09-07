"""Data models and validation schemas for WooCommerce ingestion and simulation."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class IngestionBaseModel(BaseModel):
    """Base model with shared configuration across the ingestion layer."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class Product(IngestionBaseModel):
    """Catalog product representation for inventory and simulation."""

    id: int = Field(..., gt=0, description="Unique product ID")
    sku: str = Field(..., min_length=3, description="Stock Keeping Unit code")
    name: str = Field(..., min_length=1, description="Commercial product name")
    brand: str = Field(..., min_length=1, description="Manufacturer or brand name")
    category: str = Field(..., min_length=1, description="Catalog category name")
    price: float = Field(..., ge=0.0, description="Retail price")
    cost: float = Field(..., ge=0.0, description="Unit acquisition cost")


class Customer(IngestionBaseModel):
    """WooCommerce customer entity with billing and demographic details."""

    id: int = Field(..., gt=0, description="Unique customer ID")
    first_name: str = Field(..., min_length=1, description="First name")
    last_name: str = Field(..., min_length=1, description="Last name")
    email: str = Field(..., min_length=5, description="Contact email address")
    address: str = Field(..., description="Street address")
    city: str = Field(..., description="City")
    state: str = Field(..., description="State or province code")
    postcode: str = Field(..., description="Postal code")
    country: str = Field(default="MX", description="ISO Alpha-2 country code")


class LineItem(IngestionBaseModel):
    """Individual line item purchased within an order."""

    product_id: int = Field(..., gt=0, description="Referenced product ID")
    sku: str = Field(..., description="Product SKU code")
    name: str = Field(..., description="Product name snapshot")
    brand: str = Field(..., description="Brand name snapshot")
    category: str = Field(..., description="Category snapshot")
    quantity: int = Field(..., gt=0, description="Quantity purchased")
    unit_price: str = Field(..., description="Unit price as string formatted number")
    total: str = Field(..., description="Line total amount as string formatted number")


class Order(IngestionBaseModel):
    """WooCommerce order event matching v3 REST API JSON payload."""

    id: int = Field(..., gt=0, description="Unique order transaction ID")
    status: str = Field(..., description="Order processing status")
    currency: str = Field(default="MXN", description="Currency ISO code")
    date_created: str = Field(..., description="Creation timestamp in ISO 8601")
    date_modified_gmt: Optional[str] = Field(
        default=None, description="GMT modification timestamp in ISO 8601"
    )
    total: str = Field(..., description="Total order amount as string formatted number")
    payment_method: Optional[str] = Field(
        default="unknown", description="Payment gateway identifier"
    )
    customer: Optional[Customer] = Field(
        default=None, description="Customer snapshot associated with order"
    )
    line_items: list[LineItem] = Field(
        default_factory=list, description="List of line items included in the order"
    )


class SimulatorState(IngestionBaseModel):
    """Checkpoint metadata state for the incremental order simulator."""

    last_order_id: int = Field(
        default=1000, ge=0, description="Last processed order identifier"
    )
    updated_at: str = Field(
        ..., description="ISO 8601 timestamp of last checkpoint update"
    )


class ExtractedRange(IngestionBaseModel):
    """Range of processed order identifiers within a single extraction batch."""

    start_order_id: int = Field(..., ge=0, description="Starting order ID of batch")
    end_order_id: int = Field(..., ge=0, description="Ending order ID of batch")


class IngestionMetadata(IngestionBaseModel):
    """Operational audit metadata envelope for Bronze Layer raw payloads."""

    dataset_name: str = Field(
        ..., description="Dataset entity name (e.g., 'woocommerce')"
    )
    execution_date: str = Field(
        ..., description="Logical orchestrator execution date ISO 8601"
    )
    ingested_at: str = Field(
        ..., description="Physical UTC ingestion timestamp ISO 8601"
    )
    source_system: str = Field(default="woocommerce", description="System of origin")
    use_simulator: bool = Field(
        default=False, description="Flag indicating if synthetic data was used"
    )
    execution_id: str = Field(..., description="Unique extraction run identifier")
    record_count: int = Field(
        ..., ge=0, description="Total count of records extracted in batch"
    )
    extracted_range: Optional[ExtractedRange] = Field(
        default=None, description="Extracted identifier range bounds"
    )


class BronzeEnvelope(IngestionBaseModel):
    """Unified Bronze Layer storage container with metadata envelope and data payload."""

    metadata: IngestionMetadata = Field(
        ..., alias="_metadata", description="Operational audit metadata"
    )
    data: list[dict] = Field(..., description="Raw domain data records")


class IngestionState(IngestionBaseModel):
    """Persistent state schema for tracking cursor watermarks and circuit breaker health."""

    dataset_name: str = Field(default="woocommerce", description="Target dataset name")
    last_order_id: int = Field(
        default=1000, ge=0, description="Highest processed order ID"
    )
    last_updated_at: Optional[str] = Field(
        default=None, description="Timestamp watermark of latest modification"
    )
    last_execution_timestamp: str = Field(
        ..., description="ISO 8601 timestamp of the last execution"
    )
    last_execution_status: str = Field(
        default="INITIALIZED",
        description="Status code of the last execution (SUCCESS, FAILED, etc.)",
    )
    consecutive_failures: int = Field(
        default=0,
        ge=0,
        description="Consecutive failure count for Circuit Breaker",
    )
    last_error_message: Optional[str] = Field(
        default=None, description="Details of the last recorded error if failed"
    )
