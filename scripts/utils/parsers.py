"""
Utility functions for parsing and cleaning scraped data.
"""

import re
from typing import Optional


def clean_numeric_string(value: str) -> int:
    """
    Convert various number formats to integer.

    Handles:
    - "4.16M" -> 4160000
    - "12,500" -> 12500
    - "1.5 million" -> 1500000
    - "709,715" -> 709715
    - "4.203" (when near "million") -> 4203000
    """
    if not value:
        return 0

    value = value.strip()

    # Handle "million" suffix
    million_match = re.search(r'([\d,.]+)\s*million', value, re.IGNORECASE)
    if million_match:
        num_str = million_match.group(1).replace(",", "")
        return int(float(num_str) * 1_000_000)

    # Handle "M" suffix (4.16M)
    m_match = re.search(r'([\d,.]+)\s*M\b', value)
    if m_match:
        num_str = m_match.group(1).replace(",", "")
        return int(float(num_str) * 1_000_000)

    # Handle "K" or "thousand" suffix
    k_match = re.search(r'([\d,.]+)\s*(?:K|thousand)\b', value, re.IGNORECASE)
    if k_match:
        num_str = k_match.group(1).replace(",", "")
        return int(float(num_str) * 1_000)

    # Handle plain numbers with commas
    plain_match = re.search(r'([\d,]+)', value)
    if plain_match:
        num_str = plain_match.group(1).replace(",", "")
        return int(num_str)

    return 0


def extract_numbers_from_text(text: str) -> list[int]:
    """Extract all large numbers from text (candidates for token holdings)."""
    numbers = []

    # Pattern for numbers with commas like "709,715" or "4,203,036"
    comma_numbers = re.findall(r'\b(\d{1,3}(?:,\d{3})+)\b', text)
    for num_str in comma_numbers:
        try:
            num = int(num_str.replace(",", ""))
            if num >= 1000:
                numbers.append(num)
        except ValueError:
            continue

    # Pattern for decimal millions like "4.203 million" or "4.2M"
    million_patterns = [
        (r'(\d+\.?\d*)\s*million', 1_000_000),
        (r'(\d+\.?\d*)\s*M\b', 1_000_000),
        (r'(\d+\.?\d*)\s*thousand', 1_000),
        (r'(\d+\.?\d*)\s*K\b', 1_000),
    ]

    for pattern, multiplier in million_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                num = int(float(match) * multiplier)
                if num >= 1000:
                    numbers.append(num)
            except ValueError:
                continue

    return list(set(numbers))


def extract_holdings_with_regex(text: str, pattern: str) -> Optional[int]:
    """
    Apply regex pattern to extract holdings from text.

    The pattern should have a capture group for the numeric value.
    Returns the cleaned integer or None if not found.
    """
    if not pattern or not text:
        return None

    try:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Get the first capture group
            num_str = match.group(1)

            # Check if "million" follows in context
            end_pos = match.end()
            context = text[end_pos:end_pos + 20].lower()

            if "million" in context:
                return int(float(num_str.replace(",", "")) * 1_000_000)

            return clean_numeric_string(num_str)
    except (re.error, IndexError, ValueError):
        pass

    return None


def calculate_change(old_value: int, new_value: int) -> int:
    """Calculate the change between values."""
    return new_value - old_value


def is_reasonable_change(old_value: int, new_value: int, max_drop_ratio: float = 0.5) -> bool:
    """
    Check if a change in holdings is reasonable.

    Rejects changes where holdings dropped by more than max_drop_ratio (default 50%).
    """
    if old_value <= 0:
        return True

    change_ratio = new_value / old_value
    return change_ratio >= max_drop_ratio
