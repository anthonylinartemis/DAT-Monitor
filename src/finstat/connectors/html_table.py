"""HTML table connector - discovers documents from HTML tables."""

import hashlib
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag
from tenacity import retry, stop_after_attempt, wait_exponential

from finstat.core.config import SourceConfig
from finstat.core.exceptions import DiscoveryError, FetchError
from finstat.core.logging import get_logger
from finstat.pipeline.types import DocumentCandidate, RawDocument

from .base import BaseConnector

log = get_logger(__name__)


class HtmlTableConnector(BaseConnector):
    """
    Connector for sources that list documents in HTML tables.

    Parses HTML pages to discover document links, then fetches the documents.
    """

    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FinstatBot/1.0)",
            },
        )
        self._last_request_time = 0.0

    def __del__(self) -> None:
        self.client.close()

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self.config.rate_limit.requests_per_second > 0:
            min_interval = 1.0 / self.config.rate_limit.requests_per_second
            elapsed = time.time() - self._last_request_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _get_page(self, url: str) -> str:
        """Fetch a page with retry logic."""
        self._rate_limit()
        response = self.client.get(url)
        response.raise_for_status()
        return response.text

    def discover(self) -> list[DocumentCandidate]:
        """
        Discover documents by parsing the source's HTML table.

        Returns:
            List of DocumentCandidate objects.
        """
        log.info("Starting discovery", url=self.config.base_url)
        candidates = []

        try:
            html = self._get_page(self.config.base_url)
            candidates = self._parse_page(html)
            log.info("Discovery complete", count=len(candidates))
        except httpx.HTTPError as e:
            raise DiscoveryError(f"Failed to fetch page: {e}") from e
        except Exception as e:
            raise DiscoveryError(f"Failed to parse page: {e}") from e

        return candidates

    def _parse_page(self, html: str) -> list[DocumentCandidate]:
        """Parse HTML to extract document candidates."""
        soup = BeautifulSoup(html, "lxml")
        selectors = self.config.discovery.selectors
        candidates: list[DocumentCandidate] = []

        # Find the table
        table = soup.select_one(selectors.get("table", "table"))
        if not table:
            log.warning("Table not found with selector", selector=selectors.get("table"))
            return candidates

        # Find rows
        rows = table.select(selectors.get("rows", "tbody tr"))
        log.debug("Found rows", count=len(rows))

        for row in rows:
            try:
                candidate = self._parse_row(row, selectors)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                log.warning("Failed to parse row", error=str(e))
                continue

        return candidates

    def _parse_row(self, row: Tag, selectors: dict[str, str]) -> DocumentCandidate | None:
        """Parse a single table row into a DocumentCandidate."""
        # Extract date
        date_elem = row.select_one(selectors.get("date", "td:nth-child(1)"))
        filing_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            try:
                filing_date = datetime.strptime(date_text, self.config.discovery.date_format).date()
            except ValueError:
                log.debug("Could not parse date", date_text=date_text)

        # Extract title and link
        link_elem = row.select_one(selectors.get("link", "td a"))
        if not link_elem:
            return None

        title = link_elem.get_text(strip=True)
        href_attr = link_elem.get("href")
        if not href_attr:
            return None
        # href can be str or list[str], ensure we have a string
        href = href_attr if isinstance(href_attr, str) else href_attr[0]

        # Make URL absolute
        url = urljoin(self.config.base_url, href)

        # Determine document type
        type_elem = row.select_one(selectors.get("type", "td:nth-child(3)"))
        type_text = type_elem.get_text(strip=True) if type_elem else title

        doc_type = self._determine_doc_type(type_text)
        if not doc_type:
            doc_type = "UNKNOWN"

        return DocumentCandidate(
            source_name=self.config.name,
            url=url,
            title=title,
            doc_type=doc_type,
            filing_date=filing_date,
        )

    def _determine_doc_type(self, text: str) -> str | None:
        """Determine document type from text using configured patterns."""
        for pattern_config in self.config.discovery.type_patterns:
            if re.search(pattern_config.pattern, text, re.IGNORECASE):
                return pattern_config.doc_type
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def fetch(self, candidate: DocumentCandidate) -> RawDocument:
        """
        Fetch a document's content.

        Args:
            candidate: The document to fetch.

        Returns:
            RawDocument with the content.
        """
        self._rate_limit()
        log.info("Fetching document", url=candidate.url)

        try:
            response = self.client.get(candidate.url)
            response.raise_for_status()

            content = response.content
            content_type = response.headers.get("content-type", "application/octet-stream")

            # Extract just the MIME type (remove charset etc.)
            if ";" in content_type:
                content_type = content_type.split(";")[0].strip()

            sha256 = hashlib.sha256(content).hexdigest()

            return RawDocument(
                candidate=candidate,
                content=content,
                content_type=content_type,
                sha256=sha256,
                final_url=str(response.url),
            )

        except httpx.HTTPError as e:
            raise FetchError(f"Failed to fetch document: {e}") from e
