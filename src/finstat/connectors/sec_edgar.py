"""SEC EDGAR connector - discovers 8-K filings from SEC EDGAR API."""

import hashlib
import time
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from finstat.core.config import SourceConfig
from finstat.core.exceptions import DiscoveryError, FetchError
from finstat.core.logging import get_logger
from finstat.pipeline.types import DocumentCandidate, RawDocument

from .base import BaseConnector

log = get_logger(__name__)

# SEC EDGAR API endpoints
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# SEC rate limit: 10 requests per second max
SEC_RATE_LIMIT_SECONDS = 0.15


class SecEdgarConnector(BaseConnector):
    """
    Connector for SEC EDGAR 8-K filings.

    Discovers filings via SEC EDGAR API using CIK numbers.
    Fetches filing documents (HTML/TXT) for extraction.
    """

    def __init__(self, config: SourceConfig):
        super().__init__(config)

        # SEC requires specific User-Agent format
        user_agent = config.discovery.selectors.get(
            "user_agent",
            "FinstatBot/1.0 (contact@example.com)"
        )

        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
        )
        self._last_request_time = 0.0

        # Parse company configurations from discovery.selectors
        self.companies = self._parse_companies()

    def __del__(self) -> None:
        if hasattr(self, 'client'):
            self.client.close()

    def _parse_companies(self) -> list[dict]:
        """Parse company list from config selectors."""
        companies = []
        selectors = self.config.discovery.selectors

        # Companies are stored as cik_XXX: TICKER|NAME|TOKEN format
        for key, value in selectors.items():
            if key.startswith("cik_"):
                cik = key.replace("cik_", "").zfill(10)
                parts = value.split("|")
                if len(parts) >= 3:
                    companies.append({
                        "cik": cik,
                        "ticker": parts[0],
                        "name": parts[1],
                        "token": parts[2],
                    })

        return companies

    def _rate_limit(self) -> None:
        """Enforce SEC rate limiting (10 req/sec max)."""
        min_interval = SEC_RATE_LIMIT_SECONDS
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _get_json(self, url: str) -> dict:
        """Fetch JSON from SEC API with retry logic."""
        self._rate_limit()
        log.debug("Fetching SEC API", url=url)
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _get_content(self, url: str) -> tuple[bytes, str]:
        """Fetch document content with retry logic."""
        self._rate_limit()
        response = self.client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "text/html")
        if ";" in content_type:
            content_type = content_type.split(";")[0].strip()
        return response.content, content_type

    def discover(self) -> list[DocumentCandidate]:
        """
        Discover 8-K filings for all configured companies.

        Returns:
            List of DocumentCandidate objects for recent 8-K filings.
        """
        log.info("Starting SEC EDGAR discovery", companies=len(self.companies))
        candidates = []

        lookback_days = self.config.filters.lookback_days
        cutoff_date = date.today() - timedelta(days=lookback_days)

        for company in self.companies:
            try:
                company_candidates = self._discover_company(company, cutoff_date)
                candidates.extend(company_candidates)
                log.info(
                    "Discovered filings",
                    ticker=company["ticker"],
                    count=len(company_candidates),
                )
            except Exception as e:
                log.error(
                    "Failed to discover filings",
                    ticker=company["ticker"],
                    error=str(e),
                )

        log.info("SEC EDGAR discovery complete", total=len(candidates))
        return candidates

    def _discover_company(
        self,
        company: dict,
        cutoff_date: date,
    ) -> list[DocumentCandidate]:
        """Discover 8-K filings for a single company."""
        cik = company["cik"]
        ticker = company["ticker"]
        token = company["token"]

        # Fetch company submissions from SEC
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        try:
            data = self._get_json(url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                log.warning("CIK not found", cik=cik, ticker=ticker)
                return []
            raise DiscoveryError(f"SEC API error for {ticker}: {e}") from e

        filings = data.get("filings", {}).get("recent", {})
        if not filings:
            return []

        candidates = []
        forms = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        filing_dates = filings.get("filingDate", [])
        primary_documents = filings.get("primaryDocument", [])

        for i, form in enumerate(forms):
            # Only 8-K and 8-K/A filings
            if form not in ("8-K", "8-K/A"):
                continue

            # Parse filing date
            try:
                filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d").date()
            except (ValueError, IndexError):
                continue

            # Check cutoff
            if filing_date < cutoff_date:
                continue

            # Build document URL
            accession = accession_numbers[i].replace("-", "")
            primary_doc = primary_documents[i]
            doc_url = f"{SEC_ARCHIVES_BASE}/{cik.lstrip('0')}/{accession}/{primary_doc}"

            candidates.append(DocumentCandidate(
                source_name=self.config.name,
                url=doc_url,
                title=f"{ticker} 8-K {filing_date.isoformat()}",
                doc_type="SEC_8K",
                filing_date=filing_date,
                metadata={
                    "ticker": ticker,
                    "cik": cik,
                    "token": token,
                    "company_name": company["name"],
                    "accession_number": accession_numbers[i],
                    "form_type": form,
                },
            ))

        return candidates

    def fetch(self, candidate: DocumentCandidate) -> RawDocument:
        """
        Fetch an 8-K filing document.

        For 8-K filings, we try to get the full submission text
        which includes all exhibits.
        """
        log.info(
            "Fetching SEC document",
            url=candidate.url,
            ticker=candidate.metadata.get("ticker"),
        )

        try:
            # Try to fetch the primary document first
            content, content_type = self._get_content(candidate.url)

            # If it's HTML, also try to get the full text version
            # Full text includes all exhibits which may have holdings data
            if "html" in content_type.lower():
                full_text_url = self._get_full_text_url(candidate)
                if full_text_url:
                    try:
                        full_content, full_type = self._get_content(full_text_url)
                        # Use full text if it's larger (has more content)
                        if len(full_content) > len(content):
                            content = full_content
                            content_type = full_type
                            log.debug("Using full submission text", url=full_text_url)
                    except Exception:
                        pass  # Fall back to primary document

            sha256 = hashlib.sha256(content).hexdigest()

            return RawDocument(
                candidate=candidate,
                content=content,
                content_type=content_type,
                sha256=sha256,
                final_url=candidate.url,
            )

        except httpx.HTTPError as e:
            raise FetchError(f"Failed to fetch SEC document: {e}") from e

    def _get_full_text_url(self, candidate: DocumentCandidate) -> str | None:
        """Get the full submission text file URL if available."""
        accession = candidate.metadata.get("accession_number", "")
        cik = candidate.metadata.get("cik", "").lstrip("0")

        if not accession or not cik:
            return None

        # Full submission text file pattern
        accession_clean = accession.replace("-", "")
        return f"{SEC_ARCHIVES_BASE}/{cik}/{accession_clean}/{accession}.txt"
