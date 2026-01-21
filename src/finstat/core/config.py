"""Configuration loading and validation."""

import hashlib
import warnings
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# =============================================================================
# Settings (from environment / .env)
# =============================================================================


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    These are runtime settings that may differ between environments.
    Use .env file for local development.
    """

    model_config = SettingsConfigDict(
        env_prefix="FINSTAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://finstat:finstat@localhost:5432/finstat",
        validation_alias="DATABASE_URL",
    )
    db_pool_size: int = 5
    db_echo: bool = False  # Set True to log SQL queries

    # Anthropic
    anthropic_api_key: str = Field(
        default="",
        validation_alias="ANTHROPIC_API_KEY",
    )

    # Paths
    config_dir: Path = Field(default=Path("./config"))
    data_dir: Path = Field(default=Path("./data"))

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"  # "json" or "console"

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v:
            # Allow empty for dry-run mode, but warn
            warnings.warn(
                "ANTHROPIC_API_KEY not set. LLM extraction will fail.",
                stacklevel=2,
            )
        return v


# =============================================================================
# YAML Config Models (Pydantic)
# =============================================================================


class RateLimitConfig(BaseModel):
    """Rate limiting configuration for HTTP requests."""

    requests_per_second: float = 2.0
    delay_between_documents: float = 0.5
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


class PaginationConfig(BaseModel):
    """Pagination configuration for discovery."""

    type: str = "none"  # "none", "numbered", "next_link"
    next_selector: str | None = None
    max_pages: int = 10


class TypePattern(BaseModel):
    """Pattern for matching document types."""

    pattern: str  # Regex pattern
    doc_type: str  # e.g., "SEC_8K"


class DiscoveryConfig(BaseModel):
    """Configuration for document discovery."""

    selectors: dict[str, str]  # CSS selectors for various elements
    date_format: str = "%b %d, %Y"
    type_patterns: list[TypePattern]
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)


class FilterConfig(BaseModel):
    """Configuration for filtering discovered documents."""

    include_doc_types: list[str] = Field(default_factory=list)
    exclude_doc_types: list[str] = Field(default_factory=list)
    lookback_days: int = 30


class ExtractionConfig(BaseModel):
    """Configuration for which extraction schemas to run."""

    schema_name: str = Field(alias="schema")  # Schema name, e.g., "sec_8k"
    enabled: bool = True


class SourceConfig(BaseModel):
    """
    Configuration for a single source.

    Loaded from config/sources/*.yaml
    """

    name: str
    connector: str  # Connector type, e.g., "html_table"
    base_url: str
    is_active: bool = True
    discovery: DiscoveryConfig
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    extraction: list[ExtractionConfig] = Field(default_factory=list)

    def get_config_hash(self) -> str:
        """Generate hash of this config for change detection."""
        config_str = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(config_str.encode()).hexdigest()


class SchemaField(BaseModel):
    """Definition of a field in an extraction schema."""

    name: str
    type: str  # "string", "number", "date", "array", "object"
    required: bool = False
    description: str = ""
    items: dict[str, Any] | None = None  # For array types
    properties: dict[str, Any] | None = None  # For object types


class ExtractionSchemaConfig(BaseModel):
    """
    Configuration for an extraction schema.

    Loaded from config/schemas/*.yaml
    """

    name: str
    version: str
    description: str = ""
    system_prompt: str
    fields: list[SchemaField]
    evidence_fields: list[str] = Field(default_factory=list)  # Fields that require evidence
    max_input_chars: int = 150000


class ExportColumnConfig(BaseModel):
    """Configuration for an export column."""

    name: str
    source: str  # e.g., "extraction.company_name"
    format: str | None = None
    transform: str | None = None


class ExportConfig(BaseModel):
    """
    Configuration for an export format.

    Loaded from config/exports/*.yaml
    """

    name: str
    description: str = ""
    schema_name: str = Field(alias="schema")  # Which extraction schema this exports
    format: str = "csv"  # "csv" or "json"
    columns: list[ExportColumnConfig]
    output_path: str = "./exports/{export_name}_{timestamp}.csv"


# =============================================================================
# Config Loader
# =============================================================================


class ConfigLoader:
    """
    Loads and caches configuration from YAML files.

    Usage:
        loader = ConfigLoader(Path("./config"))
        settings = loader.settings
        source = loader.load_source("strategy_financial")
        schema = loader.load_schema("sec_8k")
    """

    def __init__(self, config_dir: Path | None = None):
        self.settings = Settings()
        self.config_dir = config_dir or self.settings.config_dir
        self._source_cache: dict[str, SourceConfig] = {}
        self._schema_cache: dict[str, ExtractionSchemaConfig] = {}
        self._export_cache: dict[str, ExportConfig] = {}

    def load_source(self, name: str) -> SourceConfig:
        """Load a source configuration by name."""
        if name in self._source_cache:
            return self._source_cache[name]

        source_file = self.config_dir / "sources" / f"{name}.yaml"
        if not source_file.exists():
            raise FileNotFoundError(f"Source config not found: {source_file}")

        with open(source_file) as f:
            data = yaml.safe_load(f)

        # Handle nested "source:" key in YAML
        if "source" in data:
            data = data["source"]

        config = SourceConfig(**data)
        self._source_cache[name] = config
        return config

    def load_schema(self, name: str) -> ExtractionSchemaConfig:
        """Load an extraction schema by name."""
        if name in self._schema_cache:
            return self._schema_cache[name]

        schema_file = self.config_dir / "schemas" / f"{name}.yaml"
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema config not found: {schema_file}")

        with open(schema_file) as f:
            data = yaml.safe_load(f)

        if "schema" in data:
            data = data["schema"]

        config = ExtractionSchemaConfig(**data)
        self._schema_cache[name] = config
        return config

    def load_export(self, name: str) -> ExportConfig:
        """Load an export configuration by name."""
        if name in self._export_cache:
            return self._export_cache[name]

        export_file = self.config_dir / "exports" / f"{name}.yaml"
        if not export_file.exists():
            raise FileNotFoundError(f"Export config not found: {export_file}")

        with open(export_file) as f:
            data = yaml.safe_load(f)

        if "export" in data:
            data = data["export"]

        config = ExportConfig(**data)
        self._export_cache[name] = config
        return config

    def list_sources(self) -> list[str]:
        """List all available source configurations."""
        sources_dir = self.config_dir / "sources"
        if not sources_dir.exists():
            return []
        return [f.stem for f in sources_dir.glob("*.yaml")]

    def list_schemas(self) -> list[str]:
        """List all available extraction schemas."""
        schemas_dir = self.config_dir / "schemas"
        if not schemas_dir.exists():
            return []
        return [f.stem for f in schemas_dir.glob("*.yaml")]

    def list_exports(self) -> list[str]:
        """List all available export configurations."""
        exports_dir = self.config_dir / "exports"
        if not exports_dir.exists():
            return []
        return [f.stem for f in exports_dir.glob("*.yaml")]


# Singleton instance
_config_loader: ConfigLoader | None = None


def get_config() -> ConfigLoader:
    """Get the global config loader instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def get_settings() -> Settings:
    """Get application settings."""
    return get_config().settings
