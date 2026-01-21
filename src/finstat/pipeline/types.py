"""Pipeline data types that flow through the system."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class DocumentStatus(str, Enum):
    """Document processing status - stored in DB."""

    DISCOVERED = "discovered"
    FETCHED = "fetched"
    PARSED = "parsed"
    EXTRACTED = "extracted"
    ERROR = "error"


class RunStatus(str, Enum):
    """Pipeline run status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some documents succeeded, some failed


@dataclass
class DocumentCandidate:
    """
    Output of connector.discover().
    Represents a document found on a webpage but not yet downloaded.
    """

    source_name: str
    url: str  # Direct URL to the document (PDF)
    title: str
    doc_type: str  # e.g., "SEC_8K"
    filing_date: date | None
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)  # Connector-specific extras


@dataclass
class RawDocument:
    """
    Output of connector.fetch().
    Raw bytes downloaded from the URL.
    """

    candidate: DocumentCandidate
    content: bytes
    content_type: str  # e.g., "application/pdf"
    sha256: str  # Hex-encoded SHA256 of content
    final_url: str  # After redirects
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass
class ParsedDocument:
    """
    Output of parser.parse().
    Text extracted from the raw document.
    """

    document_id: int  # FK to documents table
    text: str
    page_count: int
    parser_name: str  # e.g., "pymupdf"
    parser_version: str  # e.g., "1.23.0"
    parsed_at: datetime = field(default_factory=datetime.utcnow)
    tables: list[dict[str, Any]] | None = None  # Future: extracted tables
    sections: list[dict[str, Any]] | None = None  # Future: document sections


@dataclass
class Evidence:
    """
    Supporting text snippet for an extracted field.
    Critical for auditability - lets humans verify LLM extractions.
    """

    field_name: str  # Which field this supports
    snippet: str  # The actual text from the document
    page_number: int | None = None  # If known


@dataclass
class ExtractionResult:
    """
    Output of extractor.extract().
    Structured data pulled from the document via LLM.
    """

    document_id: int
    schema_name: str  # e.g., "sec_8k"
    schema_version: str  # e.g., "1.0.0"
    llm_model: str  # e.g., "claude-sonnet-4-20250514"
    prompt_version: str  # e.g., "v1"
    data: dict[str, Any]  # The actual extracted fields
    evidence: list[Evidence]  # Supporting snippets
    input_tokens: int
    output_tokens: int
    extraction_time_ms: int
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    confidence_score: float | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class RunMetrics:
    """Aggregated metrics for a pipeline run."""

    documents_discovered: int = 0
    documents_fetched: int = 0
    documents_parsed: int = 0
    documents_extracted: int = 0
    documents_skipped: int = 0  # Already processed
    documents_errored: int = 0
