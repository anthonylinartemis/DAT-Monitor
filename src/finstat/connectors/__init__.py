"""Connectors module - document discovery and fetching."""

from finstat.core.config import SourceConfig

from .base import BaseConnector
from .html_table import HtmlTableConnector
from .sec_edgar import SecEdgarConnector


def get_connector(config: SourceConfig) -> BaseConnector:
    """Factory function to get the appropriate connector for a source config."""
    connectors = {
        "html_table": HtmlTableConnector,
        "sec_edgar": SecEdgarConnector,
    }

    connector_class = connectors.get(config.connector)
    if connector_class is None:
        raise ValueError(f"Unknown connector type: {config.connector}")

    return connector_class(config)


__all__ = [
    "BaseConnector",
    "HtmlTableConnector",
    "SecEdgarConnector",
    "get_connector",
]
