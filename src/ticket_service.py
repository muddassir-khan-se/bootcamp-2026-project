from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import List

from .db import db_connection
from .models import Ticket

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
NOTIFY_LOG = "notify.log"


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
    created_at = datetime.utcnow()
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
        cursor = conn.execute("UPDATE tickets SET status = ?, claimed_by = ?, claimed_at = ? WHERE id = ? AND status = ?", ("claimed", agent, datetime.utcnow().isoformat(), ticket_id, "open"))
        conn.commit()
        if cursor.rowcount == 0:
            return get_ticket(ticket_id)
    return get_ticket(ticket_id)


def get_due_tickets() -> List[Ticket]:
    now_iso = datetime.utcnow().isoformat()
    with db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM tickets WHERE status = ? AND sla_deadline <= ?",
            ("open", now_iso),
        )
        return [_row_to_ticket(row) for row in cursor.fetchall()]


def escalate_ticket(ticket_id: str) -> Ticket:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE tickets SET status = ?, escalated_at = ? WHERE id = ? AND status = ?",
            ("escalated", datetime.utcnow().isoformat(), ticket_id, "open"),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return get_ticket(ticket_id)
    return get_ticket(ticket_id)


def notify_manager(ticket_id: str, breach_time: str) -> None:
    message = f"[notify_manager] Ticket {ticket_id} breached SLA at {breach_time}\n"
    with open(NOTIFY_LOG, "a", encoding="utf-8") as fd:
        fd.write(message)


def escalate_due_tickets() -> int:
    escalated = 0
    for ticket in get_due_tickets():
        updated = escalate_ticket(ticket.id)
        if updated.status == "escalated":
            notify_manager(ticket.id, updated.escalated_at.isoformat())
            escalated += 1
    return escalated
