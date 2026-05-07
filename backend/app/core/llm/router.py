"""Model Abstraction Layer — ALL LLM calls go through ModelRouter.

Never call OpenRouter / OpenAI directly from pipeline code.
Swapping a model = change one line in .env.  Zero code changes elsewhere.

Usage:
    from app.core.llm.router import model_router

    llm = model_router.get_model("extraction")
    response = await llm.ainvoke([...])
"""

from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI

from app.config import settings

logger = structlog.get_logger(__name__)

# OpenRouter uses the OpenAI-compatible API at this base URL.
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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

    def list_tasks(self) -> dict[str, str]:
        """Return the current task → model_id mapping (useful for /health)."""
        return dict(settings.models)


# ── Singleton ────────────────────────────────────────────────────────────
model_router = ModelRouter()
