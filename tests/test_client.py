from __future__ import annotations

import socket
import threading
from http.server import HTTPServer
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
    db_file = tmp_path / "tickets.db"
    monkeypatch.setenv("TICKETS_DB_PATH", str(db_file))

    from src.server import TicketRequestHandler
    from src.ticket_service import init_ticket_table

    init_ticket_table()

    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), TicketRequestHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    server.server_close()
    thread.join()


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
