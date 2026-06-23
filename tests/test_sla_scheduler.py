from __future__ import annotations

import sqlite3
import time

from src.sla_scheduler import SlaScheduler
from src.ticket_service import create_ticket, escalate_due_tickets, get_ticket, init_ticket_table


def test_escalation_for_overdue_ticket(tmp_path, monkeypatch):
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket = create_ticket("Overdue ticket")
    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE tickets SET sla_deadline = ? WHERE id = ?", ("1970-01-01T00:00:00", ticket.id))
        conn.commit()

    count = escalate_due_tickets()
    assert count == 1
    updated = get_ticket(ticket.id)
    assert updated.status == "escalated"
    assert updated.escalated_at is not None


def test_scheduler_runs_and_escalates(tmp_path, monkeypatch):
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket = create_ticket("Scheduler ticket")
    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE tickets SET sla_deadline = ? WHERE id = ?", ("1970-01-01T00:00:00", ticket.id))
        conn.commit()

    scheduler = SlaScheduler(interval_seconds=1)
    scheduler.start()
    time.sleep(2)
    scheduler.stop()
    scheduler.join(timeout=5)

    updated = get_ticket(ticket.id)
    assert updated.status == "escalated"
