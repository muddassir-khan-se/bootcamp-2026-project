"""
Carfullfy SLA Escalation Engine - Core Ticket Business Logic & DB Operations.
Handles creation, claiming, retrieval, atomic state transitions, and SLA escalations.
Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

try:
    from .db import db_connection
    from .models import Ticket
except ImportError:
    from db import db_connection
    from models import Ticket

SLA_SECONDS = 60
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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

def get_notify_log_path() -> Path:
    return Path(os.environ.get("NOTIFY_LOG_PATH", str(_PROJECT_ROOT / "notify.log")))


class TicketConflictError(Exception):
    """Raised when a claim attempt fails because the ticket is no longer open.

    The exception message contains the ticket's current status so the HTTP
    layer can include it in the 409 response body.
    """


def _row_to_ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        id=row["id"],
        subject=row["subject"],
        created_at=datetime.fromisoformat(row["created_at"]),
        status=row["status"],
        claimed_by=row["claimed_by"],
        claimed_at=datetime.fromisoformat(row["claimed_at"]) if row["claimed_at"] else None,
        escalated_at=datetime.fromisoformat(row["escalated_at"]) if row["escalated_at"] else None,
        sla_deadline=datetime.fromisoformat(row["sla_deadline"]) if row["sla_deadline"] else None,
    )


def init_ticket_table() -> None:
    with db_connection() as conn:
        conn.execute(CREATE_TICKETS_SQL)
        conn.commit()


def create_ticket(subject: str) -> Ticket:
    ticket_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    sla_deadline = created_at + timedelta(seconds=SLA_SECONDS)
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO tickets (id, subject, created_at, status, sla_deadline) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, subject, created_at.isoformat(), "open", sla_deadline.isoformat()),
        )
        conn.commit()
    return get_ticket(ticket_id)


def get_ticket(ticket_id: str) -> Ticket:
    with db_connection() as conn:
        cursor = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("ticket_not_found")
        return _row_to_ticket(row)


def claim_ticket(ticket_id: str, agent: str) -> Ticket:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE tickets SET status = ?, claimed_by = ?, claimed_at = ? WHERE id = ? AND status = ?",
            ("claimed", agent, datetime.now(timezone.utc).isoformat(), ticket_id, "open"),
        )
        conn.commit()
        if cursor.rowcount == 0:
            # Ticket either doesn't exist or is no longer open.
            # Read the current row using the same connection (avoids re-acquiring DB_LOCK).
            row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not row:
                raise ValueError("ticket_not_found")
            raise TicketConflictError(row["status"])
        # Fetch the updated row within the same connection.
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return _row_to_ticket(row)


def get_all_tickets() -> List[Ticket]:
    with db_connection() as conn:
        cursor = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC")
        return [_row_to_ticket(row) for row in cursor.fetchall()]


def escalate_ticket(ticket_id: str) -> Ticket:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE tickets SET status = ?, escalated_at = ? WHERE id = ? AND status = ?",
            ("escalated", datetime.now(timezone.utc).isoformat(), ticket_id, "open"),
        )
        conn.commit()
    return get_ticket(ticket_id)


def notify_manager(ticket_id: str, breach_time: str) -> None:
    message = f"[notify_manager] Ticket {ticket_id} breached SLA at {breach_time}\n"
    with open(get_notify_log_path(), "a", encoding="utf-8") as fd:
        fd.write(message)


