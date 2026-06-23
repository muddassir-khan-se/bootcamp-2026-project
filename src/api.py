from __future__ import annotations

import sqlite3
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "tickets.db"
SLA_SECONDS = 60

DB_LOCK = threading.Lock()

CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    claimed_by TEXT,
    claimed_at TEXT,
    escalated_at TEXT,
    sla_deadline TEXT NOT NULL
)
"""

NOTIFY_LOG_PATH = Path(__file__).resolve().parent.parent / "notify.log"


def init_db() -> None:
    with db_connection() as conn:
        conn.execute(CREATE_TICKETS_SQL)
        conn.commit()


@contextmanager
def db_connection() -> Generator[sqlite3.Connection, None, None]:
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def create_ticket(subject: str) -> Dict[str, Any]:
    ticket_id = str(uuid.uuid4())
    created_at = now_iso()
    deadline = (datetime.utcnow() + timedelta(seconds=SLA_SECONDS)).isoformat()
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO tickets (id, subject, created_at, status, sla_deadline) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, subject, created_at, "open", deadline),
        )
        conn.commit()
    return get_ticket(ticket_id)


def claim_ticket(ticket_id: str, agent: str) -> Dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("ticket_not_found")
        if row["status"] != "open":
            return dict(row)

        conn.execute(
            "UPDATE tickets SET status = ?, claimed_by = ?, claimed_at = ? WHERE id = ?",
            ("claimed", agent, now_iso(), ticket_id),
        )
        conn.commit()
    return get_ticket(ticket_id)


def get_ticket(ticket_id: str) -> Dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("ticket_not_found")
        return dict(row)


def notify_manager(ticket_id: str, breach_time: str) -> None:
    message = f"[notify_manager] Ticket {ticket_id} breached SLA at {breach_time}\n"
    with open(NOTIFY_LOG_PATH, "a", encoding="utf-8") as fd:
        fd.write(message)


def escalate_open_tickets() -> int:
    now = now_iso()
    escalated = 0
    with db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM tickets WHERE status = ? AND sla_deadline <= ?", ("open", now)
        )
        rows = cursor.fetchall()
        for ticket in rows:
            conn.execute(
                "UPDATE tickets SET status = ?, escalated_at = ? WHERE id = ? AND status = ?",
                ("escalated", now_iso(), ticket["id"], "open"),
            )
            if conn.total_changes > 0:
                notify_manager(ticket["id"], now)
                escalated += 1
        conn.commit()
    return escalated


class SlaMonitor(threading.Thread):
    def __init__(self, interval_seconds: int = 5) -> None:
        super().__init__(daemon=True)
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            escalate_open_tickets()
            self.stop_event.wait(self.interval_seconds)

    def stop(self) -> None:
        self.stop_event.set()
