"""Unit tests for the structlog log scrubber processor (T-053).

Verifies that scrub_sensitive_fields() redacts all six sensitive field name
variants — including uppercase — and leaves non-sensitive fields intact.
"""

from __future__ import annotations

import pytest

from app.logging_config import scrub_sensitive_fields


@pytest.mark.unit()
class TestScrubSensitiveFields:
    def test_openai_key_is_redacted(self) -> None:
        event_dict = {"openai_key": "sk-real-key", "message": "test"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["openai_key"] == "[REDACTED]"
        assert result["message"] == "test"

    def test_api_key_is_redacted(self) -> None:
        event_dict = {"api_key": "some-api-key", "level": "info"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["api_key"] == "[REDACTED]"
        assert result["level"] == "info"

    def test_authorization_is_redacted(self) -> None:
        event_dict = {"authorization": "Bearer eyJhbGc...", "endpoint": "/api/v1/analyze"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["authorization"] == "[REDACTED]"
        assert result["endpoint"] == "/api/v1/analyze"

    def test_x_openai_key_is_redacted(self) -> None:
        event_dict = {"x_openai_key": "sk-another-key", "run_id": "abc-123"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["x_openai_key"] == "[REDACTED]"
        assert result["run_id"] == "abc-123"

    def test_openai_key_uppercase_is_redacted(self) -> None:
        """Case-insensitive matching: OPENAI_KEY must also be redacted."""
        event_dict = {"OPENAI_KEY": "sk-uppercase-key", "event": "startup"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["OPENAI_KEY"] == "[REDACTED]"
        assert result["event"] == "startup"

    def test_api_key_uppercase_is_redacted(self) -> None:
        """Mixed-case API_KEY variant must be redacted."""
        event_dict = {"API_KEY": "raw-key-value", "ticker": "AAPL"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["API_KEY"] == "[REDACTED]"
        assert result["ticker"] == "AAPL"

    def test_all_six_variants_in_one_event(self) -> None:
        """All six sensitive field variants in a single event dict are all redacted."""
        event_dict = {
            "openai_key": "sk-1",
            "api_key": "sk-2",
            "authorization": "Bearer tok",
            "x_openai_key": "sk-3",
            "OPENAI_KEY": "sk-4",
            "API_KEY": "sk-5",
            "safe_field": "visible",
        }
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result["openai_key"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["authorization"] == "[REDACTED]"
        assert result["x_openai_key"] == "[REDACTED]"
        assert result["OPENAI_KEY"] == "[REDACTED]"
        assert result["API_KEY"] == "[REDACTED]"
        assert result["safe_field"] == "visible"

    def test_non_sensitive_fields_unchanged(self) -> None:
        """Fields not in the sensitive set are never modified."""
        event_dict = {"event": "request_received", "ticker": "AAPL", "run_id": "uuid-here"}
        result = scrub_sensitive_fields(None, "info", event_dict)
        assert result == {"event": "request_received", "ticker": "AAPL", "run_id": "uuid-here"}

    def test_empty_event_dict_unchanged(self) -> None:
        result = scrub_sensitive_fields(None, "info", {})
        assert result == {}
