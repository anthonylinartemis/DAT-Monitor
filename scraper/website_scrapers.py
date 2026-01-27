"""Website scrapers for companies without SEC filings.

Scrapes live dashboards (e.g., Metaplanet analytics) for token holdings,
purchase history, and treasury metrics. Produces ScrapedUpdate objects
for the pipeline and enrichment dicts for data.json.
"""

from __future__ import annotations

import gzip
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Optional

from scraper.models import ScrapedUpdate

logger = logging.getLogger(__name__)

METAPLANET_ANALYTICS_URL = "https://metaplanet.jp/en/analytics"

USER_AGENT = "DAT-Monitor-Bot/1.0 (dat-monitor-github-action)"


# --- HTTP ---


def _http_get(url: str) -> str:
    """Fetch a URL with a standard User-Agent. Returns decoded text."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept-Encoding", "gzip, deflate")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"HTTP {e.code} for {url}: {e.reason}") from e


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --- Metaplanet Parser (pure functions, no I/O) ---


@dataclass(frozen=True)
class MetaplanetPurchase:
    """One row from the Metaplanet purchase history table."""
    date: str
    btc_acquired: float
    avg_cost_usd: float
    acquisition_cost_usd: float
    total_holdings: float

    def to_json_dict(self) -> dict:
        return {
            "date": self.date,
            "btcAcquired": self.btc_acquired,
            "avgCostUsd": self.avg_cost_usd,
            "acquisitionCostUsd": self.acquisition_cost_usd,
            "totalHoldings": self.total_holdings,
        }


@dataclass(frozen=True)
class MetaplanetAnalytics:
    """All data extracted from the Metaplanet analytics page."""
    total_btc: Optional[int]
    btc_per_1000_shares: Optional[float]
    ownership_pct: Optional[float]
    avg_daily_btc: Optional[float]
    bitcoin_nav_usd: Optional[float]
    purchase_history: tuple[MetaplanetPurchase, ...]

    def to_json_dict(self) -> dict:
        result: dict = {}
        if self.total_btc is not None:
            result["totalBtc"] = self.total_btc
        if self.btc_per_1000_shares is not None:
            result["btcPer1000Shares"] = self.btc_per_1000_shares
        if self.ownership_pct is not None:
            result["ownershipPct"] = self.ownership_pct
        if self.avg_daily_btc is not None:
            result["avgDailyBtc"] = self.avg_daily_btc
        if self.bitcoin_nav_usd is not None:
            result["bitcoinNavUsd"] = self.bitcoin_nav_usd
        if self.purchase_history:
            result["purchaseHistory"] = [
                p.to_json_dict() for p in self.purchase_history
            ]
        return result


def _parse_btc_amount(text: str) -> Optional[float]:
    """Parse a BTC amount like '35,102' or '4,279' or '0.02404860'."""
    # Try comma-formatted integer first
    m = re.match(r"([\d,]+(?:\.\d+)?)", text.strip().replace(" ", ""))
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _parse_usd_amount(text: str) -> Optional[float]:
    """Parse a USD amount like '$451.06M', '$3.10B', '$105,412'."""
    text = text.strip().lstrip("$")
    m = re.match(r"([\d,]+(?:\.\d+)?)\s*([MBKmkb])?", text)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").upper()
    if suffix == "B":
        val *= 1_000_000_000
    elif suffix == "M":
        val *= 1_000_000
    elif suffix == "K":
        val *= 1_000
    return val


def parse_metaplanet_analytics(text: str) -> MetaplanetAnalytics:
    """Parse the stripped text from Metaplanet's analytics page.

    Extracts total BTC, key metrics, and purchase history.
    Designed to be resilient — returns None for any field it can't parse.
    """
    total_btc = _extract_total_btc(text)
    btc_per_1000 = _extract_metric(text, r"BTC per 1,000 Shares.*?₿([\d.,]+)")
    ownership = _extract_metric(text, r"Bitcoin Ownership.*?([\d.]+)%")
    avg_daily = _extract_metric(text, r"Average BTC Purchased Daily.*?₿([\d.,]+)")
    nav = _extract_nav(text)
    purchases = _extract_purchase_history(text)

    return MetaplanetAnalytics(
        total_btc=int(total_btc) if total_btc and total_btc == int(total_btc) else (int(total_btc) if total_btc else None),
        btc_per_1000_shares=btc_per_1000,
        ownership_pct=ownership,
        avg_daily_btc=avg_daily,
        bitcoin_nav_usd=nav,
        purchase_history=tuple(purchases),
    )


def _extract_total_btc(text: str) -> Optional[float]:
    """Extract total BTC holdings. Looks for ₿XX,XXX patterns near
    'Total BTC' or 'BTC Holdings' context."""
    # Look for ₿ followed by large number (>1000) near holdings context
    for pattern in [
        r"Total BTC Holdings.*?₿\s*([\d,]+)",
        r"BTC Holdings.*?₿\s*([\d,]+)",
        r"₿\s*([\d,]{5,})",  # Any ₿ with 5+ digit chars (incl commas)
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return _parse_btc_amount(m.group(1))
    return None


def _extract_metric(text: str, pattern: str) -> Optional[float]:
    """Extract a single numeric metric using a regex pattern."""
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_nav(text: str) -> Optional[float]:
    """Extract Bitcoin NAV value like '$3.10B'."""
    m = re.search(r"Bitcoin NAV.*?\$([\d,.]+)\s*([BMK])", text, re.IGNORECASE)
    if m:
        return _parse_usd_amount(f"${m.group(1)}{m.group(2)}")
    return None


def _extract_purchase_history(text: str) -> list[MetaplanetPurchase]:
    """Extract the purchase history table rows.

    Looks for date patterns (Mon DD, YYYY) followed by BTC amounts.
    """
    purchases: list[MetaplanetPurchase] = []

    # Match: date, BTC acquired (₿X,XXX), avg cost ($X), acq cost ($X), total (₿X,XXX)
    # The page renders rows as text sequences after HTML stripping:
    # "Dec 30, 2025 ₿4,279 $105,412 $451.06M ₿35,102"
    date_pattern = r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4})"
    row_pattern = (
        date_pattern
        + r"\s+₿\s*([\d,.]+)"      # BTC acquired
        + r"\s+\$([\d,.]+[MBK]?)"   # avg cost
        + r"\s+\$([\d,.]+[MBK]?)"   # acquisition cost
        + r"\s+₿\s*([\d,.]+)"       # total holdings
    )

    for m in re.finditer(row_pattern, text, re.IGNORECASE):
        try:
            btc_acq = _parse_btc_amount(m.group(2))
            avg_cost = _parse_usd_amount(m.group(3))
            acq_cost = _parse_usd_amount(m.group(4))
            total = _parse_btc_amount(m.group(5))

            if btc_acq is not None and total is not None:
                purchases.append(MetaplanetPurchase(
                    date=m.group(1).strip(),
                    btc_acquired=btc_acq,
                    avg_cost_usd=avg_cost or 0,
                    acquisition_cost_usd=acq_cost or 0,
                    total_holdings=total,
                ))
        except (ValueError, IndexError):
            continue

    return purchases


# --- Orchestrator ---


def fetch_metaplanet_updates(
    data: dict,
) -> tuple[list[ScrapedUpdate], dict | None]:
    """Fetch Metaplanet analytics and return pipeline updates + enrichment.

    Returns:
        (updates, analytics_dict) — updates for the pipeline,
        analytics_dict to store on the company entry (or None on failure).
    """
    logger.info("Fetching Metaplanet analytics from %s", METAPLANET_ANALYTICS_URL)

    try:
        html = _http_get(METAPLANET_ANALYTICS_URL)
    except (ValueError, urllib.error.URLError) as e:
        logger.warning("Failed to fetch Metaplanet analytics: %s", e)
        return [], None

    text = _strip_html(html)
    analytics = parse_metaplanet_analytics(text)

    logger.info(
        "Metaplanet parsed: total_btc=%s, purchases=%d, nav=%s",
        analytics.total_btc,
        len(analytics.purchase_history),
        analytics.bitcoin_nav_usd,
    )

    updates: list[ScrapedUpdate] = []

    if analytics.total_btc is not None:
        # Build context from latest purchase for classifier
        if analytics.purchase_history:
            latest = analytics.purchase_history[0]
            context = (
                f"Metaplanet acquired {latest.btc_acquired:.0f} Bitcoin "
                f"for treasury holdings. Total: {analytics.total_btc:,} BTC. "
                f"Source: {METAPLANET_ANALYTICS_URL}"
            )
        else:
            context = (
                f"Metaplanet holds {analytics.total_btc:,} Bitcoin in treasury. "
                f"Source: {METAPLANET_ANALYTICS_URL}"
            )

        updates.append(ScrapedUpdate(
            ticker="MTPLF",
            token="BTC",
            new_value=analytics.total_btc,
            context_text=context,
            source_url=METAPLANET_ANALYTICS_URL,
        ))

    analytics_dict = analytics.to_json_dict() if analytics.total_btc else None
    return updates, analytics_dict


def build_website_updates(
    data: dict,
) -> tuple[list[ScrapedUpdate], dict[str, dict]]:
    """Run all website scrapers. Returns (updates, enrichments).

    enrichments is {ticker: analytics_dict} to merge into data.json
    company entries.
    """
    all_updates: list[ScrapedUpdate] = []
    enrichments: dict[str, dict] = {}

    # Metaplanet
    mtplf_updates, mtplf_analytics = fetch_metaplanet_updates(data)
    all_updates.extend(mtplf_updates)
    if mtplf_analytics:
        enrichments["MTPLF"] = mtplf_analytics

    logger.info(
        "Website scrapers: %d update(s), %d enrichment(s)",
        len(all_updates), len(enrichments),
    )
    return all_updates, enrichments
