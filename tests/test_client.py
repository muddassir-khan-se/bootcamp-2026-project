"""
Integration tests for the Python HTTP client SDK.
These tests spin up a real in-process HTTPServer and mock out the Temporal
Client so no Temporal server is required to run them.

Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import socket
import threading
import asyncio
from http.server import HTTPServer
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.client import (
    TicketClient,
    TicketClientError,
    TicketNotFoundError,
    TicketValidationError,
    TicketServiceUnavailableError,
)
from src.models import Ticket


def get_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def test_server(tmp_path, monkeypatch):
    """
    Spin up a real HTTPServer using our TicketRequestHandler, but mock the
    Temporal client so tests don't require a running Temporal server.
    """
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))

    from src.ticket_service import init_ticket_table, create_ticket, claim_ticket
    import src.server as server_module

    init_ticket_table()

    # ── Mock Temporal machinery ──────────────────────────────────────────────
    # start_workflow: inserts the ticket into SQLite directly (bypassing the
    # workflow) and returns a mock handle.  This keeps the test self-contained.
    async def fake_start_workflow(workflow_run, inp, *, id, task_queue, **kw):
        # inp is TicketWorkflowInput; use its ticket_id and subject.
        from src.temporal_activities import save_ticket_activity, SaveTicketInput
        await save_ticket_activity(SaveTicketInput(ticket_id=inp.ticket_id, subject=inp.subject))
        handle = MagicMock()
        handle.signal = AsyncMock()
        handle.id = id
        return handle

    # get_workflow_handle: return a mock handle that has signal()
    def fake_get_handle(workflow_id):
        handle = MagicMock()
        async def do_signal(signal_fn, agent):
            # Actually claim the ticket in the DB so the poll sees it.
            try:
                claim_ticket(workflow_id, agent)
            except Exception:
                pass
        handle.signal = do_signal
        handle.id = workflow_id
        return handle

    mock_client = MagicMock()
    mock_client.start_workflow = fake_start_workflow
    mock_client.get_workflow_handle = fake_get_handle

    # Patch both the module-level event loop and the Temporal client.
    async def run_in_loop(coro):
        return await asyncio.ensure_future(coro)

    # Install a real asyncio event loop in the server module so _run_async works.
    loop = asyncio.new_event_loop()
    server_module._loop = loop
    server_module._temporal_client = mock_client

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    # ── Start HTTP server ────────────────────────────────────────────────────
    from src.server import TicketRequestHandler

    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), TicketRequestHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    server.server_close()
    thread.join()

    # Reset server module state for the next test.
    server_module._loop = None
    server_module._temporal_client = None
    loop.call_soon_threadsafe(loop.stop)


def test_client_create_and_get_ticket(test_server):
    client = TicketClient(base_url=test_server)

    # 1. Create a ticket
    ticket = client.create_ticket("Client test issue")
    assert isinstance(ticket, Ticket)
    assert ticket.subject == "Client test issue"
    assert ticket.status == "open"
    assert ticket.id is not None
    assert ticket.created_at is not None

    # 2. Get the ticket details
    fetched = client.get_ticket(ticket.id)
    assert isinstance(fetched, Ticket)
    assert fetched.id == ticket.id
    assert fetched.subject == "Client test issue"
    assert fetched.status == "open"


def test_client_claim_ticket(test_server):
    client = TicketClient(base_url=test_server)

    ticket = client.create_ticket("Ticket to claim")
    claimed = client.claim_ticket(ticket.id, "agent-bob")

    assert isinstance(claimed, Ticket)
    assert claimed.status == "claimed"
    assert claimed.claimed_by == "agent-bob"
    assert claimed.claimed_at is not None


def test_client_get_all_tickets(test_server):
    client = TicketClient(base_url=test_server)

    ticket1 = client.create_ticket("Issue A")
    ticket2 = client.create_ticket("Issue B")

    tickets = client.get_all_tickets()
    assert isinstance(tickets, list)
    assert len(tickets) >= 2
    # Verify we get Ticket models
    assert all(isinstance(t, Ticket) for t in tickets)

    subjects = [t.subject for t in tickets]
    assert "Issue A" in subjects
    assert "Issue B" in subjects


def test_client_not_found_error(test_server):
    client = TicketClient(base_url=test_server)

    # Getting a non-existent ticket should raise TicketNotFoundError
    with pytest.raises(TicketNotFoundError, match="ticket_not_found"):
        client.get_ticket("non-existent-id")

    # Claiming a non-existent ticket should raise TicketNotFoundError
    with pytest.raises(TicketNotFoundError, match="ticket_not_found"):
        client.claim_ticket("non-existent-id", "agent-bob")


def test_client_invalid_input_error(test_server):
    client = TicketClient(base_url=test_server)

    # Subject is required, empty subject should raise TicketValidationError locally
    with pytest.raises(TicketValidationError):
        client.create_ticket("")

    ticket = client.create_ticket("Valid issue")

    # Agent is required for claiming, empty agent should raise TicketValidationError locally
    with pytest.raises(TicketValidationError):
        client.claim_ticket(ticket.id, "")


def test_client_connection_error():
    # Use an invalid/unused port to trigger a connection error
    client = TicketClient(base_url="http://127.0.0.1:9999")

    with pytest.raises(TicketServiceUnavailableError):
        client.get_all_tickets()


def test_client_double_claim_returns_409(test_server):
    """A second claim on an already-claimed ticket must receive HTTP 409,
    not a silent 200 that makes the second agent think it owns the ticket."""
    client = TicketClient(base_url=test_server)

    ticket = client.create_ticket("Double-claim conflict test")

    # First claim succeeds
    claimed = client.claim_ticket(ticket.id, "agent-first")
    assert claimed.status == "claimed"
    assert claimed.claimed_by == "agent-first"

    # Second claim must be rejected with a conflict error (HTTP 409)
    with pytest.raises(TicketClientError) as exc_info:
        client.claim_ticket(ticket.id, "agent-second")

    assert exc_info.value.http_status == 409
