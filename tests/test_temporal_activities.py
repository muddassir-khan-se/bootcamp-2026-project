"""
Tests for Temporal Activities — Carfullfy SLA Engine.

Activities are pure Python functions that wrap SQLite operations.
They can be tested directly without a running Temporal server by
calling them inside Temporal's activity testing context.

Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import pytest

from src.ticket_service import init_ticket_table, get_ticket
from src.temporal_activities import (
    ClaimTicketInput,
    EscalateTicketInput,
    NotifyManagerInput,
    SaveTicketInput,
    claim_ticket_activity,
    escalate_ticket_activity,
    notify_manager_activity,
    save_ticket_activity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run an async coroutine synchronously in tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# save_ticket_activity
# ---------------------------------------------------------------------------

def test_save_ticket_activity_creates_row(tmp_path, monkeypatch):
    """save_ticket_activity inserts a ticket into SQLite with the given ID."""
    import uuid
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket_id = str(uuid.uuid4())
    result = run(save_ticket_activity(SaveTicketInput(ticket_id=ticket_id, subject="Engine noise")))

    assert result.ticket_id == ticket_id
    assert result.subject == "Engine noise"
    assert result.status == "open"
    assert result.sla_deadline != ""


def test_save_ticket_activity_sets_sla_deadline(tmp_path, monkeypatch):
    """sla_deadline should be 60 seconds after created_at."""
    import uuid
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket_id = str(uuid.uuid4())
    result = run(save_ticket_activity(SaveTicketInput(ticket_id=ticket_id, subject="Brakes squeaking")))

    created = datetime.fromisoformat(result.created_at)
    deadline = datetime.fromisoformat(result.sla_deadline)
    delta = (deadline - created).total_seconds()
    assert 59 <= delta <= 61  # Allow 1-second tolerance for test timing


# ---------------------------------------------------------------------------
# escalate_ticket_activity
# ---------------------------------------------------------------------------

def test_escalate_ticket_activity_escalates_open_ticket(tmp_path, monkeypatch):
    """escalate_ticket_activity marks an open ticket as escalated."""
    import uuid
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket_id = str(uuid.uuid4())
    run(save_ticket_activity(SaveTicketInput(ticket_id=ticket_id, subject="Oil leak")))

    # Force deadline to the past so escalation is valid
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "UPDATE tickets SET sla_deadline = ? WHERE id = ?",
            ("1970-01-01T00:00:00+00:00", ticket_id),
        )
        conn.commit()

    status = run(escalate_ticket_activity(EscalateTicketInput(ticket_id=ticket_id)))
    assert status == "escalated"

    ticket = get_ticket(ticket_id)
    assert ticket.status == "escalated"
    assert ticket.escalated_at is not None


def test_escalate_ticket_activity_idempotent_on_claimed(tmp_path, monkeypatch):
    """Escalating an already-claimed ticket returns 'claimed' without changing it."""
    import uuid
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket_id = str(uuid.uuid4())
    run(save_ticket_activity(SaveTicketInput(ticket_id=ticket_id, subject="Flat tyre")))
    run(claim_ticket_activity(ClaimTicketInput(ticket_id=ticket_id, agent="agent-1")))

    # Escalating an already-claimed ticket should not change status
    status = run(escalate_ticket_activity(EscalateTicketInput(ticket_id=ticket_id)))
    assert status == "claimed"


# ---------------------------------------------------------------------------
# claim_ticket_activity
# ---------------------------------------------------------------------------

def test_claim_ticket_activity_claims_open_ticket(tmp_path, monkeypatch):
    """claim_ticket_activity assigns an agent and returns 'claimed'."""
    import uuid
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket_id = str(uuid.uuid4())
    run(save_ticket_activity(SaveTicketInput(ticket_id=ticket_id, subject="Window stuck")))

    status = run(claim_ticket_activity(ClaimTicketInput(ticket_id=ticket_id, agent="agent-42")))
    assert status == "claimed"

    ticket = get_ticket(ticket_id)
    assert ticket.status == "claimed"
    assert ticket.claimed_by == "agent-42"
    assert ticket.claimed_at is not None


def test_claim_ticket_activity_returns_status_on_conflict(tmp_path, monkeypatch):
    """Claiming an already-claimed ticket returns the current status, not an exception."""
    import uuid
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))
    init_ticket_table()

    ticket_id = str(uuid.uuid4())
    run(save_ticket_activity(SaveTicketInput(ticket_id=ticket_id, subject="AC broken")))
    run(claim_ticket_activity(ClaimTicketInput(ticket_id=ticket_id, agent="agent-1")))

    # Second claim should return the current status without raising
    status = run(claim_ticket_activity(ClaimTicketInput(ticket_id=ticket_id, agent="agent-2")))
    assert status == "claimed"


# ---------------------------------------------------------------------------
# notify_manager_activity
# ---------------------------------------------------------------------------

def test_notify_manager_activity_writes_log(tmp_path, monkeypatch):
    """notify_manager_activity appends an entry to notify.log."""
    log_file = tmp_path / "notify.log"
    monkeypatch.setenv("NOTIFY_LOG_PATH", str(log_file))

    run(notify_manager_activity(NotifyManagerInput(
        ticket_id="test-id-123",
        breach_time="2026-07-17T12:00:00+00:00",
    )))

    assert log_file.exists()
    content = log_file.read_text()
    assert "test-id-123" in content
    assert "2026-07-17T12:00:00+00:00" in content
