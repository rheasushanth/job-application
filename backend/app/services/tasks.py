"""Background task abstraction.

Call sites use `enqueue(fn, *args)` and never care which backend runs it:

  * Default: a bounded thread pool in-process. No Redis needed, so the app is
    runnable from a clean checkout.
  * Production: set REDIS_URL and the same calls dispatch to Celery.

Discovery and scoring are I/O-bound (HTTP + database), so threads are a real
win even under the GIL.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
_inflight: set[Future] = set()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=settings.task_worker_threads,
                    thread_name_prefix="jobmatch-task",
                )
    return _executor


def backend_name() -> str:
    return "celery+redis" if settings.celery_enabled else "thread-pool"


def enqueue(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Schedule work off the request path. Returns an opaque task reference."""
    if settings.celery_enabled:
        try:
            from app.services.celery_app import run_task

            result = run_task.delay(f"{fn.__module__}.{fn.__qualname__}", args, kwargs)
            return str(result.id)
        except Exception:
            logger.exception("Celery dispatch failed; running in a local thread instead")

    future = _get_executor().submit(_guard, fn, *args, **kwargs)
    _inflight.add(future)
    future.add_done_callback(_inflight.discard)
    return f"thread:{id(future)}"


def _guard(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Never let a background exception die silently."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception("Background task %s failed", getattr(fn, "__qualname__", fn))
        raise


def wait_for_idle(timeout: float = 120.0) -> bool:
    """Block until queued work drains. Used by tests and graceful shutdown."""
    import concurrent.futures

    pending = list(_inflight)
    if not pending:
        return True
    done, not_done = concurrent.futures.wait(pending, timeout=timeout)
    return not not_done


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=False)
        _executor = None
