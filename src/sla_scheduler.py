"""
Carfullfy SLA Escalation Engine - SLA Scheduler Daemon Thread.
Periodically scans database for overdue open tickets and executes immediate crash recovery scans on startup.
Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

try:
    from .ticket_service import escalate_due_tickets
except ImportError:
    from ticket_service import escalate_due_tickets


class SlaScheduler(threading.Thread):
    def __init__(self, interval_seconds: int = 5) -> None:
        super().__init__(daemon=True)
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.last_run: Optional[datetime] = None

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.check_and_escalate()
            self.stop_event.wait(self.interval_seconds)

    def check_and_escalate(self) -> int:
        escalated = escalate_due_tickets()
        self.last_run = datetime.now(timezone.utc)
        return escalated

    def stop(self) -> None:
        self.stop_event.set()
