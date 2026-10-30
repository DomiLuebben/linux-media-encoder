"""Bounded background metadata work; no Qt calls, no shutdown wait."""
import logging
import queue
import threading

_tasks = queue.Queue()
_lock = threading.Lock()
_started = False


def _worker():
    while True:
        task = _tasks.get()
        try:
            task()
        except Exception:
            logging.exception("Media metadata probe failed")
        finally:
            _tasks.task_done()
            del task


def submit_probe(task):
    """Run at most four probes concurrently, including across dialogs."""
    global _started
    with _lock:
        if not _started:
            for index in range(4):
                threading.Thread(target=_worker, daemon=True,
                                 name=f"lme-probe-{index}").start()
            _started = True
    _tasks.put(task)
