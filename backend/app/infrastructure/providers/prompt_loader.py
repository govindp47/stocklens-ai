"""Jinja2-based prompt template loader with injection-safe autoescaping.

PromptLoader loads templates from a directory, caches compiled Template objects,
and renders them with keyword arguments.  ``autoescape=True`` is required to
neutralise prompt injection from untrusted article content.
"""

from __future__ import annotations

import jinja2


def _format_number(value: object) -> str:
    """Compact number formatter for the Jinja2 environment.

    Examples:
        1_234_567_890 → "1.23B"
        2_710_000_000_000 → "2.71T"
        54_321 → "54.3K"
    """
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)

    if abs(n) >= 1_000_000_000_000:
        return f"{n / 1_000_000_000_000:.2f}T"
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class PromptLoader:
    """Load, cache, and render Jinja2 prompt templates.

    Args:
        template_dir: Path to the directory containing ``.j2`` template files.
            Can be relative (resolved from the current working directory at
            startup) or absolute.

    Usage::

        loader = PromptLoader("app/prompts")
        prompt = loader.render("sentiment.j2", ticker="AAPL",
                               company_name="Apple Inc.", title="Apple beats earnings")
    """

    def __init__(self, template_dir: str) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=True,  # prevents prompt injection via article content
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["format_number"] = _format_number
        self._cache: dict[str, jinja2.Template] = {}

    def render(self, template_name: str, **kwargs: object) -> str:
        """Render a named template with the given keyword arguments.

        Args:
            template_name: Filename of the template (e.g. ``"sentiment.j2"``).
            **kwargs: Variables passed to the template context.

        Returns:
            Rendered prompt string.

        Raises:
            jinja2.TemplateNotFound: If the template file does not exist.
        """
        if template_name not in self._cache:
            self._cache[template_name] = self._env.get_template(template_name)
        return self._cache[template_name].render(**kwargs)
