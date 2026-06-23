from __future__ import annotations

import sqlite3
import time

import pytest


def test_ticket_service_create_and_get(tmp_path, monkeypatch):
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))

    from src.ticket_service import create_ticket, get_ticket, init_ticket_table

    init_ticket_table()
    ticket = create_ticket("Test subject")

    assert ticket.subject == "Test subject"
    assert ticket.status == "open"
    assert ticket.sla_deadline is not None

    fetched = get_ticket(ticket.id)
    assert fetched.id == ticket.id
    assert fetched.status == "open"


def test_claim_ticket(tmp_path, monkeypatch):
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))

    from src.ticket_service import claim_ticket, create_ticket, init_ticket_table

    init_ticket_table()
    ticket = create_ticket("Claimed ticket")
    claimed = claim_ticket(ticket.id, "agent-1")

    assert claimed.status == "claimed"
    assert claimed.claimed_by == "agent-1"
    assert claimed.claimed_at is not None


def test_ticket_not_found():
    from src.ticket_service import get_ticket

    with pytest.raises(ValueError, match="ticket_not_found"):
        get_ticket("missing-id")
