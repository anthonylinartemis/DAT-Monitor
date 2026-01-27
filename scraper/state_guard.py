"""Oscillation prevention for token holding updates.

Prevents noisy flip-flopping (e.g., MSTR 712k → 709k → 712k alerting
multiple times) by tracking seen values and requiring confirmation
keywords for previously-seen values to be re-accepted.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from scraper.config import CONFIRMATION_KEYWORDS, HOLDINGS_HISTORY_PATH
from scraper.models import HoldingRecord, ScrapedUpdate


def load_history(path: Optional[Path] = None) -> dict[str, HoldingRecord]:
    """Load oscillation history from JSON. Returns {} on first run."""
    path = path or HOLDINGS_HISTORY_PATH
    if not path.exists():
        return {}

    with open(path, "r") as f:
        raw = json.load(f)

    return {key: HoldingRecord.from_json_dict(val) for key, val in raw.items()}


def save_history(
    history: dict[str, HoldingRecord], path: Optional[Path] = None
) -> None:
    """Atomic write: temp file → os.replace() for crash safety."""
    path = path or HOLDINGS_HISTORY_PATH

    raw = {key: record.to_json_dict() for key, record in history.items()}
    serialized = json.dumps(raw, indent=2) + "\n"

    # Write to temp file in the same directory, then atomically replace.
    # Same-directory ensures same filesystem for os.replace() guarantee.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".history_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(serialized)
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _contains_confirmation(text: str) -> bool:
    """Case-insensitive scan for confirmation keywords in context text."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in CONFIRMATION_KEYWORDS)


def should_update(
    update: ScrapedUpdate, history: dict[str, HoldingRecord]
) -> tuple[bool, str]:
    """Core oscillation decision. Returns (should_apply, reason).

    Decision matrix:
    1. Ticker not in history      → YES (first observation)
    2. Value == last_confirmed    → NO  (no change)
    3. Value not in seen_values   → YES (genuinely new value)
    4. Value in seen + confirmed  → YES (confirmed return)
    5. Value in seen + no keyword → NO  (oscillation suppressed)
    """
    key = f"{update.ticker}:{update.token}"

    if key not in history:
        return True, "first observation"

    record = history[key]

    if update.new_value == record.last_confirmed_value:
        return False, "no change from last confirmed value"

    if update.new_value not in record.seen_values:
        return True, "genuinely new value"

    # Value was seen before — require confirmation keyword
    if _contains_confirmation(update.context_text):
        return True, "previously seen value confirmed by keyword"

    return False, "oscillation suppressed (value seen before, no confirmation)"


def record_update(
    update: ScrapedUpdate,
    history: dict[str, HoldingRecord],
    date: str,
) -> dict[str, HoldingRecord]:
    """Return a new history dict with the update recorded.

    Immutable pattern: original dict is not modified.
    """
    key = f"{update.ticker}:{update.token}"
    new_history = dict(history)

    existing = history.get(key)
    if existing:
        new_seen = existing.seen_values | frozenset({update.new_value})
    else:
        new_seen = frozenset({update.new_value})

    new_history[key] = HoldingRecord(
        last_confirmed_value=update.new_value,
        seen_values=new_seen,
        last_update_date=date,
    )

    return new_history
