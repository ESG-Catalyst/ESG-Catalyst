"""Model Abstraction Layer — ALL LLM calls go through ModelRouter.

Never call OpenRouter / Groq / OpenAI directly from pipeline code.
Swapping a model = change one line in .env.  Zero code changes elsewhere.

Supported prefixes:
    openrouter/<provider>/<model>  → OpenRouter API (ChatOpenAI-compatible)
    groq/<model>                   → Groq API (ChatGroq, free tier)

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
from langchain_core.language_models.chat_models import BaseChatModel
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
    "rate_limit_exceeded",      # Groq free-tier rate limit
    "tokens per minute",        # Groq TPM limit message
)


class ModelRouter:
    """Resolve a task name to a LangChain chat model.

    Supports two providers based on the model ID prefix in ``settings.models``:
    - ``openrouter/<provider>/<model>`` → OpenRouter API (paid + free tiers)
    - ``groq/<model>``                 → Groq API (free tier, very fast)

    The mapping from task → model ID lives entirely in ``settings.models``,
    which is populated from environment variables (MODEL_EXTRACTION, etc.).
    """

    def __init__(self) -> None:
        self._cache: dict[str, BaseChatModel] = {}

    # ── public API ───────────────────────────────────────────────────────
    def get_model(self, task: str) -> BaseChatModel:
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

    def get_fallback_model(self, task: str) -> BaseChatModel | None:
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
        "payment required", quota exceeded, Groq rate limit). All other
        failures propagate.

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
    def _build(self, model_id: str, task: str) -> BaseChatModel:
        """Dispatch to the correct provider based on the model_id prefix.

        Args:
            model_id: Full model ID including provider prefix
                      (e.g. ``"groq/llama-3.1-70b-versatile"`` or
                      ``"openrouter/qwen/qwen-2.5-7b-instruct:free"``).
            task: Human-readable task name for logging only.
        """
        logger.info("model_router.loading", task=task, model_id=model_id)

        if model_id.startswith("groq/"):
            return self._build_groq(model_id, task)

        # Default: treat as OpenRouter (handles both "openrouter/..." and bare IDs)
        return self._build_openrouter(model_id, task)

    def _build_openrouter(self, model_id: str, task: str) -> ChatOpenAI:
        """Instantiate a ChatOpenAI client pointed at OpenRouter.

        Args:
            model_id: Full model ID, optionally prefixed with ``openrouter/``.
            task: Human-readable task name for logging only.
        """
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

    def _build_groq(self, model_id: str, task: str) -> BaseChatModel:
        """Instantiate a ChatGroq client for the Groq free-tier API.

        Groq is significantly faster than OpenRouter for open-source models
        (hundreds of tokens/second vs ~20-40). Free tier supports Llama 3.x
        and Gemma 2.

        Args:
            model_id: Full model ID prefixed with ``groq/``
                      (e.g. ``"groq/llama-3.1-70b-versatile"``).
            task: Human-readable task name for logging only.
        """
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise ImportError(
                "langchain-groq is required for groq/ model IDs. "
                "Run: pip install langchain-groq>=0.1.0"
            ) from exc

        if not settings.groq_api_key:
            raise ValueError(
                f"Task '{task}' uses model '{model_id}' which requires GROQ_API_KEY "
                "in .env. Get a free key at https://console.groq.com"
            )

        groq_model = model_id.removeprefix("groq/")

        return ChatGroq(
            model=groq_model,
            groq_api_key=settings.groq_api_key,
            temperature=0.0,
            max_retries=2,
            request_timeout=60,  # Groq responds much faster than OpenRouter
        )


def _is_credit_error(exc: BaseException) -> bool:
    """True if *exc* looks like an HTTP 402 / insufficient-credits / rate-limit error."""
    status = getattr(exc, "status_code", None)
    if status == 402:
        return True
    if status == 429:  # Groq rate limit → trigger fallback
        return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) in (402, 429):
        return True

    msg = str(exc).lower()
    return any(marker in msg for marker in _CREDIT_ERROR_MARKERS)


# ── Singleton ────────────────────────────────────────────────────────────
model_router = ModelRouter()
