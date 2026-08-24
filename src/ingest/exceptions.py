# -----------------------------------------------------------------------------
# 1. INGESTION BASE EXCEPTION
# -----------------------------------------------------------------------------
class IngestionError(Exception):
    """Base exception for any failure within the `src/ingest` package."""

    pass


# -----------------------------------------------------------------------------
# 2. STORAGE ERRORS (Storage Writers: Local / S3)
# -----------------------------------------------------------------------------
class StorageError(IngestionError):
    """Triggered when a write operation to storage (local disk or AWS S3) fails."""

    pass


# -----------------------------------------------------------------------------
# 3. SPECIFIC WOOCOMMERCE ERRORS
# -----------------------------------------------------------------------------
class WooCommerceError(IngestionError):
    """Base exception for specific WooCommerce connector errors."""

    pass


class WooCommerceCircuitBreakerError(WooCommerceError):
    """Triggered when the WooCommerce Circuit Breaker is OPEN."""

    pass


class WooCommerceAPIError(WooCommerceError):
    """Thrown when the WooCommerce API responds with a 4xx or 5xx code."""

    pass
