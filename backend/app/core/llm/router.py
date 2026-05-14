"""Model Abstraction Layer — ALL LLM calls go through ModelRouter.

Never call OpenRouter / OpenAI directly from pipeline code.
Swapping a model = change one line in .env.  Zero code changes elsewhere.

Usage:
    from app.core.llm.router import model_router

    # Direct (no fallback):
    llm = model_router.get_model("extraction")
    response = await llm.ainvoke([...])

    # With free-tier fallback on HTTP 402 / insufficient credits:
    response = await model_router.ainvoke_with_fallback("extraction", [...])
"""

from __future__ import annotations

from typing import Any, Sequence

import structlog
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from app.config import settings

logger = structlog.get_logger(__name__)

# OpenRouter uses the OpenAI-compatible API at this base URL.
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Substrings that indicate the primary model is unusable for billing reasons.
# Matched case-insensitively against the str() of the underlying exception.
_CREDIT_ERROR_MARKERS = (
    "insufficient credit",
    "insufficient_credits",
    "payment required",
    "402",
    "quota",
    "exceeded your current quota",
    "key limit exceeded",
)


class ModelRouter:
    """Resolve a task name to a LangChain chat model backed by OpenRouter.

    The mapping from task → model ID lives entirely in ``settings.models``,
    which is populated from environment variables (MODEL_EXTRACTION, etc.).
    """

    def __init__(self) -> None:
        self._cache: dict[str, ChatOpenAI] = {}

    # ── public API ───────────────────────────────────────────────────────
    def get_model(self, task: str) -> ChatOpenAI:
        """Return a LangChain ChatModel for the given *task*.

        Args:
            task: One of the keys in ``settings.models``
                  (``"extraction"``, ``"scoring"``, ``"report"``).

        Raises:
            ValueError: If *task* is not mapped in settings.
        """
        if task not in settings.models:
            raise ValueError(
                f"Unknown task {task!r}. "
                f"Configured tasks: {list(settings.models.keys())}"
            )

        model_id = settings.models[task]

        if model_id not in self._cache:
            self._cache[model_id] = self._build(model_id, task)

        return self._cache[model_id]

    def get_fallback_model(self, task: str) -> ChatOpenAI | None:
        """Return the configured free-tier fallback for *task*, or None."""
        fallback_id = settings.model_fallbacks.get(task)
        if not fallback_id:
            return None
        if fallback_id not in self._cache:
            self._cache[fallback_id] = self._build(fallback_id, f"{task}_fallback")
        return self._cache[fallback_id]

    async def ainvoke_with_fallback(
        self,
        task: str,
        messages: Sequence[BaseMessage],
        **kwargs: Any,
    ):
        """Invoke the task's primary model; on HTTP 402 / credit errors, retry on fallback.

        Activates the fallback ONLY when the primary call fails with a
        billing-related error (HTTP 402, "insufficient credits",
        "payment required", quota exceeded). All other failures propagate.

        Raises:
            Exception: The original error if no fallback is configured, or
                the fallback's error if both calls fail.
        """
        primary = self.get_model(task)
        try:
            return await primary.ainvoke(messages, **kwargs)
        except Exception as exc:
            if not _is_credit_error(exc):
                raise

            fallback = self.get_fallback_model(task)
            if fallback is None:
                logger.error(
                    "model_router.no_fallback_configured",
                    task=task,
                    primary=settings.models[task],
                    error=str(exc),
                )
                raise

            logger.warning(
                "model_router.fallback_activated",
                task=task,
                primary=settings.models[task],
                fallback=settings.model_fallbacks[task],
                reason=str(exc)[:200],
                message="Primary model unavailable, using free fallback",
            )
            return await fallback.ainvoke(messages, **kwargs)

    def list_tasks(self) -> dict[str, str]:
        """Return the current task → model_id mapping (useful for /health)."""
        return dict(settings.models)

    # ── internals ────────────────────────────────────────────────────────
    def _build(self, model_id: str, task: str) -> ChatOpenAI:
        """Instantiate a ChatOpenAI pointed at OpenRouter."""
        logger.info("model_router.loading", task=task, model_id=model_id)

        # Strip the "openrouter/" prefix if present — OpenRouter expects
        # just the provider/model portion (e.g. "anthropic/claude-3.5-sonnet").
        openrouter_model = model_id.removeprefix("openrouter/")

        return ChatOpenAI(
            model=openrouter_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=_OPENROUTER_BASE_URL,
            temperature=0.0,
            max_retries=2,
            request_timeout=120,
        )


def _is_credit_error(exc: BaseException) -> bool:
    """True if *exc* looks like an HTTP 402 / insufficient-credits error."""
    status = getattr(exc, "status_code", None)
    if status == 402:
        return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 402:
        return True

    msg = str(exc).lower()
    return any(marker in msg for marker in _CREDIT_ERROR_MARKERS)


# ── Singleton ────────────────────────────────────────────────────────────
model_router = ModelRouter()
