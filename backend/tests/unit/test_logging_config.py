from __future__ import annotations

import pytest

from app.logging_config import scrub_sensitive_fields


@pytest.mark.unit()
def test_scrub_sensitive_fields_redacts_known_keys() -> None:
    event_dict = {"openai_key": "sk-secret", "message": "test"}
    result = scrub_sensitive_fields(None, "info", event_dict)
    assert result["openai_key"] == "[REDACTED]"
    assert result["message"] == "test"


@pytest.mark.unit()
def test_scrub_sensitive_fields_redacts_all_sensitive_keys() -> None:
    event_dict = {
        "openai_key": "sk-secret",
        "api_key": "key-value",
        "authorization": "Bearer token",
        "x_openai_key": "another-secret",
        "safe_field": "visible",
    }
    result = scrub_sensitive_fields(None, "info", event_dict)
    assert result["openai_key"] == "[REDACTED]"
    assert result["api_key"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["x_openai_key"] == "[REDACTED]"
    assert result["safe_field"] == "visible"


@pytest.mark.unit()
def test_scrub_sensitive_fields_leaves_clean_dict_unchanged() -> None:
    event_dict = {"event": "startup", "version": "1.0.0"}
    result = scrub_sensitive_fields(None, "info", event_dict)
    assert result == {"event": "startup", "version": "1.0.0"}
