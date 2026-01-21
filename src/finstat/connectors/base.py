"""Base connector class."""

from abc import ABC, abstractmethod

from finstat.core.config import SourceConfig
from finstat.pipeline.types import DocumentCandidate, RawDocument


class BaseConnector(ABC):
    """
    Abstract base class for document connectors.

    Connectors are responsible for:
    1. Discovering documents from a source (discover method)
    2. Fetching document content (fetch method)
    """

    def __init__(self, config: SourceConfig):
        self.config = config

    @abstractmethod
    def discover(self) -> list[DocumentCandidate]:
        """
        Discover documents from the source.

        Returns:
            List of DocumentCandidate objects representing discovered documents.
        """
        pass

    @abstractmethod
    def fetch(self, candidate: DocumentCandidate) -> RawDocument:
        """
        Fetch document content.

        Args:
            candidate: The document candidate to fetch.

        Returns:
            RawDocument with the fetched content.
        """
        pass
