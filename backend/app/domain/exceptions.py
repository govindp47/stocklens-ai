"""Domain exception hierarchy for StockLens AI.

All exceptions raised within the domain layer inherit from StockLensBaseError.
Infrastructure and pipeline layers must catch these exceptions and translate them
into appropriate API responses or pipeline failure records.
"""

from __future__ import annotations


class StockLensBaseError(Exception):
    """Base class for all StockLens domain errors."""


class ExternalProviderError(StockLensBaseError):
    """Raised when an external data provider (yfinance, RSS, LLM API) fails.

    Attributes:
        error_code: Machine-readable error identifier (e.g. 'YFINANCE_TIMEOUT').
        user_message: Safe, user-facing message — must not contain stack traces.
        is_retryable: Whether the caller should retry this operation.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        user_message: str,
        is_retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.error_code: str = error_code
        self.user_message: str = user_message
        self.is_retryable: bool = is_retryable


class LLMParseError(StockLensBaseError):
    """Raised when LLM output cannot be parsed into the expected schema.

    Stores the raw LLM output for debugging without propagating it to the user.

    Attributes:
        step_name: The pipeline step that triggered the LLM call.
        raw_output: The verbatim LLM response that failed to parse.
    """

    def __init__(
        self,
        message: str,
        *,
        step_name: str,
        raw_output: str,
    ) -> None:
        super().__init__(message)
        self.step_name: str = step_name
        self.raw_output: str = raw_output


class PipelineTimeoutError(StockLensBaseError):
    """Raised when the pipeline watchdog cancels a run that exceeds the timeout."""


class TickerNotResolvableError(StockLensBaseError):
    """Raised when a ticker symbol cannot be resolved to a known company."""


class RateLimitExceededError(StockLensBaseError):
    """Raised when an incoming request is rejected by the rate limiter."""
