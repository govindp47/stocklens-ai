"""LLM provider interface contract.

All concrete provider implementations (Ollama, OpenAI-compatible, etc.)
must satisfy this Protocol.  The Protocol is @runtime_checkable so the
orchestrator can assert provider correctness at startup via isinstance().
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Structural interface for any LLM provider injected into the pipeline.

    Concrete implementations (T-024, T-025) satisfy this Protocol
    structurally — they do not need to inherit from it.

    Runtime check example::

        assert isinstance(provider, LLMProvider), (
            f"{provider!r} does not satisfy LLMProvider Protocol"
        )
    """

    @property
    def model_name(self) -> str:
        """Identifier for the underlying model (e.g. ``"llama3:8b"``).

        Used for logging and report metadata.
        """
        ...

    async def complete(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Send ``prompt`` to the model and return the raw text response.

        Args:
            prompt: The full prompt string (system + user content combined).
            max_tokens: Hard cap on generated tokens.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            The model's text response as a plain string.

        Raises:
            ExternalProviderError: On network failure, timeout, or non-2xx
                response from the provider API.
        """
        ...
