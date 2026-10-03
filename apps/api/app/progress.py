"""How far along scoring is, for the progress bar on the applications page.

Scoring runs in this process (a background task on a worker thread), so the
progress lives here too: a small in-memory map from application id to which
reader is running and how many are done. It is gone when scoring finishes or
the server restarts, which is right: a finished application has a result, and
a restart re-reads nothing half-done.
"""

import threading
import time
from dataclasses import dataclass
from uuid import UUID


@dataclass
class Progress:
    done: int
    total: int
    step: str
    started: float


_lock = threading.Lock()
_running: dict[UUID, Progress] = {}


def start(application_id: UUID, step: str = "Preparing the evidence") -> None:
    with _lock:
        _running[application_id] = Progress(0, 0, step, time.monotonic())


def update(application_id: UUID, done: int, total: int, step: str) -> None:
    with _lock:
        current = _running.get(application_id)
        started = current.started if current else time.monotonic()
        _running[application_id] = Progress(done, total, step, started)


def finish(application_id: UUID) -> None:
    with _lock:
        _running.pop(application_id, None)


def get(application_id: UUID) -> Progress | None:
    with _lock:
        return _running.get(application_id)
