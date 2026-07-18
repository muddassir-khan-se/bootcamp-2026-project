"""
Carfullfy SLA Escalation Engine - Temporal Activities.
Wraps core DB operations as Temporal activities so they can be
called from the SlaWorkflow in a durable, retryable manner.
Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from temporalio import activity

try:
    from .db import db_connection
    from .models import Ticket
    from .ticket_service import (
        TicketConflictError,
        _row_to_ticket,
        claim_ticket,
        escalate_ticket,
        get_ticket,
        init_ticket_table,
        notify_manager,
    )
except ImportError:
    from db import db_connection
    from models import Ticket
    from ticket_service import (
        TicketConflictError,
        _row_to_ticket,
        claim_ticket,
        escalate_ticket,
        get_ticket,
        init_ticket_table,
        notify_manager,
    )

SLA_SECONDS = 60


# ---------------------------------------------------------------------------
# Input / Output dataclasses (must be JSON-serialisable for Temporal)
# ---------------------------------------------------------------------------

@dataclass
class SaveTicketInput:
    ticket_id: str   # Pre-generated UUID — same as Temporal workflow ID
    subject: str


@dataclass
class SaveTicketOutput:
    ticket_id: str
    subject: str
    created_at: str
    status: str
    sla_deadline: str


@dataclass
class ClaimTicketInput:
    ticket_id: str
    agent: str


@dataclass
class EscalateTicketInput:
    ticket_id: str


@dataclass
class NotifyManagerInput:
    ticket_id: str
    breach_time: str


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@activity.defn
async def save_ticket_activity(inp: SaveTicketInput) -> SaveTicketOutput:
    """
    Insert a ticket row in SQLite using a pre-assigned ticket_id.
    The ticket_id is the same as the Temporal workflow ID so the HTTP layer
    can always look up and signal the workflow by the ticket's UUID.
    """
    init_ticket_table()
    created_at = datetime.now(timezone.utc)
    sla_deadline = created_at + timedelta(seconds=SLA_SECONDS)

    with db_connection() as conn:
        conn.execute(
            "INSERT INTO tickets (id, subject, created_at, status, sla_deadline) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                inp.ticket_id,
                inp.subject,
                created_at.isoformat(),
                "open",
                sla_deadline.isoformat(),
            ),
        )
        conn.commit()

    ticket = get_ticket(inp.ticket_id)
    return SaveTicketOutput(
        ticket_id=ticket.id,
        subject=ticket.subject,
        created_at=ticket.created_at.isoformat(),
        status=ticket.status,
        sla_deadline=ticket.sla_deadline.isoformat() if ticket.sla_deadline else "",
    )


@activity.defn
async def escalate_ticket_activity(inp: EscalateTicketInput) -> str:
    """Atomically escalate a ticket that is still open. Returns final status."""
    ticket = escalate_ticket(inp.ticket_id)
    return ticket.status


@activity.defn
async def notify_manager_activity(inp: NotifyManagerInput) -> None:
    """Write an SLA-breach notification entry to notify.log."""
    notify_manager(inp.ticket_id, inp.breach_time)


@activity.defn
async def claim_ticket_activity(inp: ClaimTicketInput) -> str:
    """Claim a ticket on behalf of an agent. Returns final status."""
    try:
        ticket = claim_ticket(inp.ticket_id, inp.agent)
        return ticket.status
    except TicketConflictError as exc:
        # Already escalated — not an error for the signal handler
        return str(exc)
