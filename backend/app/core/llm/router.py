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

from typing import Any, Optional, Sequence

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.exceptions import LLMUnavailableError

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
        # Keyed by (model_id, max_tokens): the SAME model can serve two tasks
        # with different completion caps (e.g. extraction=2000, report=3000),
        # so the cap must be part of the cache identity — otherwise the first
        # task to build a shared model would leak its cap to the other.
        self._cache: dict[tuple[str, Optional[int]], BaseChatModel] = {}

    # ── public API ───────────────────────────────────────────────────────
    def get_model(self, task: str) -> BaseChatModel:
        """Return a LangChain ChatModel for the given *task*.

        The model is built with the per-task completion cap from
        ``settings.model_max_tokens`` (see ``_build_openrouter`` for why an
        uncapped request 402s on OpenRouter).

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
        max_tokens = settings.model_max_tokens.get(task)
        return self._get_or_build(model_id, task, max_tokens)

    def get_fallback_model(self, task: str) -> BaseChatModel | None:
        """Return the configured free-tier fallback for *task*, or None.

        The fallback inherits the same per-task completion cap as the primary.
        """
        fallback_id = settings.model_fallbacks.get(task)
        if not fallback_id:
            return None
        max_tokens = settings.model_max_tokens.get(task)
        return self._get_or_build(fallback_id, f"{task}_fallback", max_tokens)

    def _get_or_build(
        self, model_id: str, label: str, max_tokens: Optional[int]
    ) -> BaseChatModel:
        """Build (or return cached) model for *model_id* at the given cap."""
        key = (model_id, max_tokens)
        if key not in self._cache:
            self._cache[key] = self._build(model_id, label, max_tokens)
        return self._cache[key]

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
        failures propagate immediately without attempting the fallback.

        Args:
            task: Task key (``"extraction"``, ``"scoring"``, ``"report"``).
            messages: LangChain message sequence to forward to the model.
            **kwargs: Extra arguments forwarded to ``ainvoke``.

        Returns:
            The raw LangChain ``AIMessage`` returned by whichever model
            succeeds (primary or fallback).

        Raises:
            LLMUnavailableError: When the primary fails with a credit /
                quota error AND the fallback also fails (or is not
                configured). The original exception is chained via
                ``__cause__``.
        """
        primary = self.get_model(task)
        try:
            return await primary.ainvoke(messages, **kwargs)
        except Exception as primary_exc:
            if not _is_credit_error(primary_exc):
                raise

            fallback = self.get_fallback_model(task)
            if fallback is None:
                logger.error(
                    "model_router.no_fallback_configured",
                    task=task,
                    primary=settings.models[task],
                    error=str(primary_exc),
                )
                raise LLMUnavailableError(
                    f"Primary model for task {task!r} is unavailable and no fallback "
                    f"is configured. Primary error: {primary_exc}"
                ) from primary_exc

            logger.warning(
                "model_router.fallback_activated",
                task=task,
                primary=settings.models[task],
                fallback=settings.model_fallbacks[task],
                reason=str(primary_exc)[:200],
                message="Primary model unavailable, using free fallback",
            )
            try:
                return await fallback.ainvoke(messages, **kwargs)
            except Exception as fallback_exc:
                logger.error(
                    "model_router.fallback_failed",
                    task=task,
                    primary=settings.models[task],
                    fallback=settings.model_fallbacks[task],
                    primary_error=str(primary_exc)[:200],
                    fallback_error=str(fallback_exc)[:200],
                )
                raise LLMUnavailableError(
                    f"Both primary and fallback models for task {task!r} are "
                    f"unavailable. Primary: {primary_exc}; Fallback: {fallback_exc}"
                ) from fallback_exc

    def list_tasks(self) -> dict[str, str]:
        """Return the current task → model_id mapping (useful for /health)."""
        return dict(settings.models)

    # ── internals ────────────────────────────────────────────────────────
    def _build(
        self, model_id: str, task: str, max_tokens: Optional[int] = None
    ) -> BaseChatModel:
        """Dispatch to the correct provider based on the model_id prefix.

        Args:
            model_id: Full model ID including provider prefix
                      (e.g. ``"groq/llama-3.1-70b-versatile"`` or
                      ``"openrouter/qwen/qwen-2.5-7b-instruct:free"``).
            task: Human-readable task name for logging only.
            max_tokens: Per-task completion cap to bake into the model, or None.
        """
        logger.info(
            "model_router.loading", task=task, model_id=model_id, max_tokens=max_tokens
        )

        if model_id.startswith("groq/"):
            return self._build_groq(model_id, task, max_tokens)

        # Default: treat as OpenRouter (handles both "openrouter/..." and bare IDs)
        return self._build_openrouter(model_id, task, max_tokens)

    def _build_openrouter(
        self, model_id: str, task: str, max_tokens: Optional[int] = None
    ) -> ChatOpenAI:
        """Instantiate a ChatOpenAI client pointed at OpenRouter.

        Args:
            model_id: Full model ID, optionally prefixed with ``openrouter/``.
            task: Human-readable task name for logging only.
            max_tokens: Completion cap. CRITICAL for OpenRouter billing — an
                uncapped request defaults to the model's full output ceiling
                (e.g. 64000 for Claude Sonnet) and OpenRouter's affordability
                pre-check reserves credit for that whole ceiling, so even a
                tiny prompt 402s on a low balance. langchain_openai emits this
                as ``max_completion_tokens`` (OpenAI's current field), which
                OpenRouter honors. MUST be set at construction — call-time
                kwargs are not forwarded by langchain_openai 1.x.
        """
        # Strip the "openrouter/" prefix if present — OpenRouter expects
        # just the provider/model portion (e.g. "anthropic/claude-3.5-sonnet").
        openrouter_model = model_id.removeprefix("openrouter/")

        kwargs: dict[str, Any] = dict(
            model=openrouter_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=_OPENROUTER_BASE_URL,
            temperature=0.0,
            max_retries=2,
            request_timeout=120,
        )
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs)

    def _build_groq(
        self, model_id: str, task: str, max_tokens: Optional[int] = None
    ) -> BaseChatModel:
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

        kwargs: dict[str, Any] = dict(
            model=groq_model,
            groq_api_key=settings.groq_api_key,
            temperature=0.0,
            max_retries=2,
            request_timeout=60,  # Groq responds much faster than OpenRouter
        )
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        return ChatGroq(**kwargs)


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
