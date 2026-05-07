"""Celery application instance — shared by tasks and FastAPI.

Usage:
    # Start worker:
    celery -A app.workers.celery_app worker --loglevel=info

    # From FastAPI or anywhere else:
    from app.workers.celery_app import celery_app
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "esg_catalyst",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Keep results for 24 hours so /extraction/status can query them
    result_expires=86400,
    # Prevent worker from prefetching too many tasks (long-running pipeline)
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
