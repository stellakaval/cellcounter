"""In-process background worker (no Celery/Redis — this is a single-user local tool).

A single daemon thread drains a ``queue.Queue`` of image IDs and processes them one at a
time. Sequential processing keeps the slow StarDist model on one thread; the model itself
stays loaded across images because ``segment._STARDIST_MODEL`` is a module global.

A thread (not asyncio) is used so the blocking TensorFlow inference never stalls uvicorn's
event loop — status polls stay responsive while images process.
"""

from __future__ import annotations

import queue
import threading

_job_queue: "queue.Queue[int]" = queue.Queue()
_worker_thread: threading.Thread | None = None


def enqueue(image_id: int) -> None:
    _job_queue.put(image_id)


def _worker_loop() -> None:
    # Imported here to avoid importing the heavy logic stack at module import time.
    from .services import processing

    while True:
        image_id = _job_queue.get()
        try:
            processing.process_image(image_id)
        except Exception:  # never let one bad image kill the worker
            pass
        finally:
            _job_queue.task_done()


def start_worker() -> None:
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="cc-worker")
    _worker_thread.start()


def join() -> None:
    """Block until the queue is drained (used by integration tests)."""
    _job_queue.join()
