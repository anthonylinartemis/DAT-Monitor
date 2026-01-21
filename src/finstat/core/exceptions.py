"""Custom exceptions for the finstat package."""


class FinstatError(Exception):
    """Base exception for all finstat errors."""

    pass


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigError(FinstatError):
    """Error in configuration."""

    pass


class ConfigNotFoundError(ConfigError):
    """Configuration file not found."""

    pass


class ConfigValidationError(ConfigError):
    """Configuration validation failed."""

    pass


# =============================================================================
# Connector Errors
# =============================================================================


class ConnectorError(FinstatError):
    """Error in connector operation."""

    pass


class DiscoveryError(ConnectorError):
    """Error during document discovery."""

    pass


class FetchError(ConnectorError):
    """Error fetching a document."""

    pass


class RateLimitError(ConnectorError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after: {retry_after}s")


# =============================================================================
# Storage Errors
# =============================================================================


class StorageError(FinstatError):
    """Error in storage operation."""

    pass


class StorageWriteError(StorageError):
    """Error writing to storage."""

    pass


class StorageReadError(StorageError):
    """Error reading from storage."""

    pass


# =============================================================================
# Parser Errors
# =============================================================================


class ParserError(FinstatError):
    """Error in document parsing."""

    pass


class UnsupportedFormatError(ParserError):
    """Document format not supported."""

    pass


class CorruptedDocumentError(ParserError):
    """Document is corrupted or unreadable."""

    pass


class EncryptedDocumentError(ParserError):
    """Document is password-protected."""

    pass


class EmptyDocumentError(ParserError):
    """Document has no extractable text."""

    pass


# =============================================================================
# Extraction Errors
# =============================================================================


class ExtractionError(FinstatError):
    """Error in LLM extraction."""

    pass


class LLMError(ExtractionError):
    """Error from LLM API."""

    pass


class LLMRateLimitError(LLMError):
    """LLM API rate limit exceeded."""

    pass


class LLMTimeoutError(LLMError):
    """LLM API timeout."""

    pass


class ValidationError(ExtractionError):
    """Extraction result failed validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Validation failed: {errors}")


class SchemaNotFoundError(ExtractionError):
    """Extraction schema not found."""

    pass


# =============================================================================
# Pipeline Errors
# =============================================================================


class PipelineError(FinstatError):
    """Error in pipeline execution."""

    pass


class DuplicateDocumentError(PipelineError):
    """Document already exists (by SHA256)."""

    def __init__(self, sha256: str, existing_id: int):
        self.sha256 = sha256
        self.existing_id = existing_id
        super().__init__(f"Duplicate document: {sha256} (existing ID: {existing_id})")


# =============================================================================
# Export Errors
# =============================================================================


class ExportError(FinstatError):
    """Error in export operation."""

    pass
