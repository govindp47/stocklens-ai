"""Step 1 — TickerValidator (critical pipeline step).

Validates that the ticker symbol in PipelineContext resolves to a known
security on yfinance.  Uses a two-level cache (TickerCacheRepository) before
hitting the external provider.  A negative cache hit short-circuits the
external call immediately.

This is a *critical* step: failure raises TickerNotResolvableError, which
the orchestrator catches to halt the entire pipeline run.
"""

from __future__ import annotations

import logging
import time

from app.domain.exceptions import ExternalProviderError, TickerNotResolvableError
from app.domain.models.market import CompanyInfo
from app.infrastructure.providers.market_data_provider import MarketDataProvider
from app.infrastructure.repositories.ticker_cache_repository import TickerCacheRepository
from app.pipeline.context import PipelineContext
from app.pipeline.steps.base import BasePipelineStep, StepResult, StepStatus

logger = logging.getLogger(__name__)


class TickerValidator(BasePipelineStep):
    """Validate and cache ticker resolution as the first pipeline step.

    Attributes:
        name: Step identifier used in logging, metrics, and persistence.
        step_index: Execution order index (1 = first step).
        critical: True — any failure halts the entire pipeline.
        max_retries: 2 — transient network errors may be retried; an
            unresolvable ticker raises TickerNotResolvableError (non-retryable)
            so the orchestrator stops before consuming retries.
    """

    name: str = "TickerValidator"
    step_index: int = 1
    critical: bool = True
    max_retries: int = 2

    def __init__(
        self,
        ticker_cache_repo: TickerCacheRepository,
        market_data_provider: MarketDataProvider,
    ) -> None:
        self._ticker_cache_repo = ticker_cache_repo
        self._market_data_provider = market_data_provider

    # ──────────────────────────────────────────────────────────────────────
    # PipelineStep Protocol
    # ──────────────────────────────────────────────────────────────────────

    async def execute(self, context: PipelineContext) -> StepResult:
        """Resolve *context.ticker* and populate *context.outputs.company_info*.

        Flow:
        1. Check TickerCacheRepository.resolve():
           - False → negative cache hit → raise TickerNotResolvableError (no I/O).
           - None  → cache miss → call is_ticker_resolvable() on the provider.
           - True  → known-good → skip external call.
        2. If provider returns False → write negative cache → raise TickerNotResolvableError.
        3. If provider returns True  → write positive cache.
        4. Fetch company info and populate context.outputs.company_info.

        Returns:
            StepResult with status=COMPLETE on success.

        Raises:
            TickerNotResolvableError: When the ticker cannot be resolved.
                This exception is *non-retryable* — the orchestrator treats it
                as a critical failure and halts the pipeline.
            ExternalProviderError: On transient network failures (retryable).
        """
        ticker = context.ticker
        start_ms = int(time.monotonic() * 1000)

        logger.info("Validating ticker", extra={"ticker": ticker, "run_id": str(context.run_id)})

        # 1. Cache lookup
        cached_result = await self._ticker_cache_repo.resolve(ticker)

        if cached_result is False:
            # Negative cache hit — do NOT make any external call
            logger.info(
                "Ticker in negative cache; halting pipeline",
                extra={"ticker": ticker},
            )
            raise TickerNotResolvableError(
                f"Ticker '{ticker}' is known-unresolvable (negative cache)."
            )

        if cached_result is None:
            # Cache miss — hit the external provider
            try:
                is_resolvable = await self._market_data_provider.is_ticker_resolvable(ticker)
            except ExternalProviderError:
                raise  # retryable — orchestrator will retry per max_retries
            except Exception as exc:
                raise ExternalProviderError(
                    f"Unexpected error resolving ticker '{ticker}': {exc}",
                    error_code="YFINANCE_UNEXPECTED_ERROR",
                    user_message="An unexpected error occurred while validating the ticker.",
                    is_retryable=True,
                ) from exc

            # Persist resolution result to cache (both Redis and PostgreSQL)
            if not is_resolvable:
                await self._ticker_cache_repo.set_resolved(ticker, is_resolvable=False)
                logger.info(
                    "Ticker unresolvable; cached negative result",
                    extra={"ticker": ticker},
                )
                raise TickerNotResolvableError(
                    f"Ticker '{ticker}' could not be resolved on yfinance."
                )

            # Positive result — company info is fetched below; metadata written then
        # cached_result is True → already resolved; no external call needed

        # 2. Fetch company info and populate context
        company_info = await self._fetch_and_populate(ticker, context)

        duration_ms = int(time.monotonic() * 1000) - start_ms
        logger.info(
            "Ticker validated",
            extra={
                "ticker": ticker,
                "company": company_info.name,
                "duration_ms": duration_ms,
            },
        )
        return StepResult(
            step_name=self.name,
            step_index=self.step_index,
            status=StepStatus.COMPLETE,
            duration_ms=duration_ms,
            output_summary=f"Resolved '{ticker}' → {company_info.name or ticker}",
        )

    # can_execute() inherits BasePipelineStep default (always True)

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_and_populate(
        self,
        ticker: str,
        context: PipelineContext,
    ) -> CompanyInfo:
        """Fetch company info, write the positive cache entry, and update context."""

        # Build CompanyInfo from quote-level metadata if available
        company_info_from_provider = await self._market_data_provider.get_company_info(ticker)
        company_info = company_info_from_provider or CompanyInfo(ticker=ticker)

        # Persist positive resolution with enriched metadata
        await self._ticker_cache_repo.set_resolved(
            ticker,
            is_resolvable=True,
            company_name=company_info.name,
            exchange=company_info.exchange,
            sector=company_info.sector,
            industry=company_info.industry,
            currency=company_info.currency,
            country=company_info.country,
        )

        context.outputs.company_info = company_info

        return company_info
