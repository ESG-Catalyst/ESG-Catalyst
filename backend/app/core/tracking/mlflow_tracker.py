"""MLflow tracking helpers for the extraction pipeline (M3).

All public functions are safe no-ops if MLflow is unreachable or the
package is missing — never break the pipeline.
"""

from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

try:
    import mlflow as _mlflow
except Exception as _exc:  # pragma: no cover
    # Fail-safe: a missing OR broken-but-installed mlflow (import raising
    # non-ImportError) must never break the pipeline — tracking is optional.
    _mlflow = None  # type: ignore[assignment]
    logger.warning("mlflow.import_failed", error=str(_exc))


@contextmanager
def start_extraction_run(
    experiment: str = "esg-extraction",
    run_name: Optional[str] = None,
) -> Iterator[Any]:
    """Yield an active MLflow run, or None if tracking is unavailable.

    Failures while *starting* the run (server unreachable, package missing,
    etc.) are swallowed and a warning is logged — the caller still gets
    ``None`` and the pipeline continues.

    Exceptions raised inside the caller's ``with`` body are NOT swallowed:
    they propagate normally so the real error is visible (the MLflow run is
    still ended in ``finally``). Yielding a second time from the ``except``
    here would make CPython raise ``RuntimeError("generator didn't stop
    after throw()")`` and mask the caller's true exception — so the
    ``yield`` is deliberately kept out of the start-up ``try/except``.
    """
    if _mlflow is None:
        yield None
        return

    # Start the run. A failure here is non-fatal: log it and yield None so
    # the pipeline still runs untracked. No `yield` inside this try/except.
    run = None
    try:
        _mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        _mlflow.set_experiment(experiment)
        run = _mlflow.start_run(run_name=run_name)
    except Exception as exc:
        logger.warning("mlflow.run_start_failed", error=str(exc))
        run = None

    # Single yield in its own try/finally — caller-body exceptions propagate
    # untouched; the run is always ended.
    try:
        yield run
    finally:
        if run is not None:
            try:
                _mlflow.end_run()
            except Exception as exc:
                logger.warning("mlflow.run_end_failed", error=str(exc))


def log_params(params: dict[str, Any]) -> None:
    if _mlflow is None:
        return
    try:
        _mlflow.log_params({k: ("" if v is None else str(v)) for k, v in params.items()})
    except Exception as exc:
        logger.warning("mlflow.log_params_failed", error=str(exc))


def log_metrics(metrics: dict[str, float]) -> None:
    if _mlflow is None:
        return
    try:
        _mlflow.log_metrics({k: float(v) for k, v in metrics.items() if v is not None})
    except Exception as exc:
        logger.warning("mlflow.log_metrics_failed", error=str(exc))


def log_metric(key: str, value: float) -> None:
    if _mlflow is None:
        return
    try:
        _mlflow.log_metric(key, float(value))
    except Exception as exc:
        logger.warning("mlflow.log_metric_failed", key=key, error=str(exc))


def log_json_artifact(name: str, payload: Any) -> None:
    """Write *payload* as JSON and log it as an MLflow artifact."""
    if _mlflow is None:
        return
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            _mlflow.log_artifact(str(path))
    except Exception as exc:
        logger.warning("mlflow.log_artifact_failed", name=name, error=str(exc))


def sanitize_metric_key(key: str) -> str:
    """MLflow metric keys allow alnum, '_', '-', '.', ' ', '/'. Replace others."""
    return "".join(c if c.isalnum() or c in "_-. /" else "_" for c in key)