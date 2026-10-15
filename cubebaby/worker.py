"""Executa as operações com o pedal fora da thread da interface."""
from __future__ import annotations

import queue
import traceback

from .qt import QtCore, Signal

QObject, QThread = QtCore.QObject, QtCore.QThread


class Job:
    def __init__(self, fn, on_done=None, on_error=None, label=""):
        self.fn, self.on_done, self.on_error, self.label = fn, on_done, on_error, label


class DeviceWorker(QThread):
    """Fila única: o pedal só atende uma transação por vez."""

    done = Signal(object, object)       # (job, resultado)
    failed = Signal(object, str)        # (job, mensagem)
    busy = Signal(str)                  # rótulo da operação em andamento ("" = livre)
    progress = Signal(int, int)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._q: queue.Queue[Job | None] = queue.Queue()
        self.done.connect(lambda job, res: job.on_done and job.on_done(res))
        self.failed.connect(lambda job, msg: job.on_error and job.on_error(msg))

    def submit(self, fn, on_done=None, on_error=None, label=""):
        self._q.put(Job(fn, on_done, on_error, label))

    def stop(self):
        self._q.put(None)
        self.wait(5000)

    def report_progress(self, current: int, total: int):
        self.progress.emit(current, total)

    def run(self):
        while (job := self._q.get()) is not None:
            if job.label:
                self.busy.emit(job.label)
            try:
                self.done.emit(job, job.fn())
            except Exception as e:  # noqa: BLE001 — qualquer falha vira mensagem na interface
                traceback.print_exc()
                self.failed.emit(job, str(e))
            finally:
                if job.label:
                    self.busy.emit("")
