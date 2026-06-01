"""Celery application instance — shared by workers and FastAPI.

This module creates the ``celery_app`` singleton that is imported by:
  - ``app.workers.tasks`` (task registration)
  - ``app.api.pipeline`` and ``app.api.reports`` (``send_task`` calls)

Keep this module light — no pipeline logic, no ORM imports.  Heavy imports
belong in ``tasks.py`` where they are loaded only inside the worker process.

Starting the worker
-------------------
From the project root with ``PYTHONPATH=backend``::

    celery -A app.workers.celery_app worker --loglevel=info

For production / large Arabic documents (prevents OOM / stale event-loop
after hours of CPU inference)::

    celery -A app.workers.celery_app worker --loglevel=info --max-tasks-per-child=1

.. note::
    ``--max-tasks-per-child=1`` is a RUNTIME flag passed to the ``celery``
    CLI command (or the ``command:`` in docker-compose).  It is NOT
    configurable here.  See "Flagged for reconciliation" in REFACTOR_config.md
    for the docker-compose change that adds this flag permanently.

Task routing (future)
---------------------
All tasks currently go to the default queue.  When Iteration 3 (LangGraph)
lands, add named queues here and mirror them in docker-compose ``command:``.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "esg_catalyst",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Task modules that Celery auto-discovers on worker startup.
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # ── Serialisation ────────────────────────────────────────────────────────
    # JSON only — avoids pickle security issues and keeps tasks portable
    # across Python versions.
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # ── Time zone ────────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,

    # ── Result retention ─────────────────────────────────────────────────────
    # 24 hours — long enough for /pipeline/status polling but avoids unbounded
    # Redis growth on a busy worker.
    result_expires=86400,

    # ── Prefetch / late-ack ──────────────────────────────────────────────────
    # worker_prefetch_multiplier=1: worker fetches one task at a time.
    # Pipeline tasks are long-running (10–90 min CPU), so prefetching would
    # queue a second task behind a running one, preventing other workers from
    # picking it up.
    worker_prefetch_multiplier=1,
    # task_acks_late=True: task is acknowledged only after it completes (or
    # raises).  If the worker process crashes mid-task, the task is requeued
    # rather than silently dropped.
    task_acks_late=True,
)
