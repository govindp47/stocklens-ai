from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
import structlog.contextvars
import structlog.processors
import structlog.stdlib

# Fields whose values must never appear in log output
_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {"openai_key", "api_key", "authorization", "x_openai_key"}
)


def scrub_sensitive_fields(
    logger: Any,
    method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor — replaces sensitive field values with [REDACTED].

    Field name matching is case-insensitive so that variants like ``OPENAI_KEY``
    and ``openai_key`` are both redacted.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output with stdlib integration."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure stdlib root logger to output raw messages.
    # structlog's JSONRenderer produces the final JSON string; stdlib just
    # emits it verbatim via %(message)s.
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.contextvars.merge_contextvars,
            scrub_sensitive_fields,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
