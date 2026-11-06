"""Background jobs, so the window never freezes.

Light jobs (merge, split, passwords ...) run in a background thread. Heavy jobs
(OCR, orientation checks, conversions) run in a separate worker process: a crash
or a very large document there cannot take the window down, and Cancel can stop
the process outright if the engine does not respond within a few seconds.

A job is a plain function from app.runners: fn(job, **kwargs) -> dict. It must
not touch Qt; it reports progress through job.step() (see services.common.Job).
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue as queue_mod
import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .services.common import Cancelled, Job, UserError

log = logging.getLogger("pps.jobs")


def _describe(exc: BaseException) -> str:
    if isinstance(exc, (UserError,)):
        return str(exc)
    name = type(exc).__name__
    return f"Unexpected error ({name}): {exc}\nDetails are in logs\\pdf_play_station.log."


def run_function(fn: Callable, kwargs: dict, progress, is_cancelled) -> tuple[str, object]:
    """('ok', result) | ('cancelled', None) | ('error', message). Shared by both modes."""
    try:
        return "ok", fn(Job(progress, is_cancelled), **kwargs)
    except Cancelled:
        return "cancelled", None
    except Exception as exc:                          # reported to the user, full trace to the log
        if not isinstance(exc, UserError):
            log.error("Job %s failed:\n%s", getattr(fn, "__name__", fn), traceback.format_exc())
        return "error", _describe(exc)


# ------------------------------------------------------------------ thread mode

class _ThreadWorker(QThread):
    progressed = Signal(int, int, str)
    finished_with = Signal(str, object)

    def __init__(self, fn, kwargs):
        super().__init__()
        self.fn, self.kwargs = fn, kwargs
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        status, payload = run_function(self.fn, self.kwargs, self.progressed.emit, lambda: self._cancel)
        self.finished_with.emit(status, payload)


# ------------------------------------------------------------------ process mode

def _process_main(fn, kwargs, out_q, cancel_event) -> None:
    from . import logger
    logger.setup()

    def progress(done, total, text):
        out_q.put(("progress", (done, total, text)))
    status, payload = run_function(fn, kwargs, progress, cancel_event.is_set)
    out_q.put((status, payload))


class _ProcessWorker(QObject):
    progressed = Signal(int, int, str)
    finished_with = Signal(str, object)

    def __init__(self, fn, kwargs):
        super().__init__()
        ctx = mp.get_context("spawn")
        self.q = ctx.Queue()
        self.cancel_event = ctx.Event()
        self.proc = ctx.Process(target=_process_main, args=(fn, kwargs, self.q, self.cancel_event), daemon=True)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self._done = False
        self._kill_at: Optional[int] = None

    def start(self) -> None:
        self.proc.start()
        self.timer.start()

    def cancel(self) -> None:
        self.cancel_event.set()
        self._kill_at = 50                             # ~5 s grace, then the process is stopped

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue_mod.Empty:
                break
            if kind == "progress":
                self.progressed.emit(*payload)
            else:
                self._finish(kind, payload)
                return
        if self._kill_at is not None:
            self._kill_at -= 1
            if self._kill_at <= 0:
                self.proc.terminate()
                self._finish("cancelled", None)
                return
        if not self.proc.is_alive() and self.q.empty():
            self._finish("error", "The worker process stopped unexpectedly. Details are in the log.")

    def _finish(self, status, payload) -> None:
        if self._done:
            return
        self._done = True
        self.timer.stop()
        self.proc.join(timeout=2)
        self.finished_with.emit(status, payload)


# ------------------------------------------------------------------ runner

class JobRunner(QObject):
    """Runs one job at a time for a tool page."""
    progressed = Signal(int, int, str)
    finished = Signal(str, object)                    # status, result dict or message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None

    @property
    def busy(self) -> bool:
        return self.worker is not None

    def start(self, fn: Callable, kwargs: dict, heavy: bool = False) -> None:
        if self.worker is not None:
            raise RuntimeError("A job is already running.")
        log.info("Job %s started (%s)", fn.__name__, "process" if heavy else "thread")
        self.worker = _ProcessWorker(fn, kwargs) if heavy else _ThreadWorker(fn, kwargs)
        self.worker.progressed.connect(self.progressed.emit)
        self.worker.finished_with.connect(self._done)
        self.worker.start()

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def _done(self, status: str, payload) -> None:
        worker, self.worker = self.worker, None
        if isinstance(worker, QThread):
            worker.wait(2000)
        if worker is not None:
            worker.deleteLater()
        log.info("Job finished: %s", status)
        self.finished.emit(status, payload)
