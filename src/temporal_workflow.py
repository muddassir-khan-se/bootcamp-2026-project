"""
Carfullfy SLA Escalation Engine - Temporal Workflow.
Defines the SlaWorkflow that manages the full ticket lifecycle:
  1. Save ticket to DB (using ticket_id = Temporal workflow ID)
  2. Sleep 60 seconds (durable timer — survives crashes)
  3. If not claimed → escalate and notify manager
  4. If claimed signal received → persist claim to DB and exit cleanly

One workflow instance runs per ticket, identified by the ticket UUID.
Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import sys as _sys
    import os as _os
    # Ensure the src/ directory is on sys.path so that the absolute import
    # 'temporal_activities' resolves correctly inside the Temporal sandbox,
    # which does not support relative imports.
    _src_dir = _os.path.dirname(_os.path.abspath(__file__))
    if _src_dir not in _sys.path:
        _sys.path.insert(0, _src_dir)

    try:
        from temporal_activities import (
            ClaimTicketInput,
            EscalateTicketInput,
            NotifyManagerInput,
            SaveTicketInput,
            SaveTicketOutput,
            claim_ticket_activity,
            escalate_ticket_activity,
            notify_manager_activity,
            save_ticket_activity,
        )
    except ImportError:
        from .temporal_activities import (
            ClaimTicketInput,
            EscalateTicketInput,
            NotifyManagerInput,
            SaveTicketInput,
            SaveTicketOutput,
            claim_ticket_activity,
            escalate_ticket_activity,
            notify_manager_activity,
            save_ticket_activity,
        )

TASK_QUEUE = "sla-ticket-queue"
SLA_SECONDS = 60

# Retry policy — up to 3 attempts with 2-second initial back-off.
ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_attempts=3,
)


@dataclass
class TicketWorkflowInput:
    ticket_id: str
    subject: str


@workflow.defn
class SlaWorkflow:
    """
    One instance of this workflow runs for the entire lifetime of a ticket.
    The workflow ID equals the ticket UUID so it can be looked up and
    signalled (claimed) from the HTTP API using the same ID.
    """

    def __init__(self) -> None:
        self._claimed: bool = False
        self._claimed_by: Optional[str] = None

    @workflow.signal
    async def claim_signal(self, agent: str) -> None:
        """
        Signal sent by the HTTP handler when an agent claims the ticket.
        Marks the ticket as claimed so the SLA timer branch is skipped,
        then persists the claim to the database.
        """
        self._claimed = True
        self._claimed_by = agent

    @workflow.run
    async def run(self, inp: TicketWorkflowInput) -> str:
        """
        Main workflow body.

        Args:
            inp: TicketWorkflowInput containing ticket_id and subject.

        Returns:
            Final ticket status: "claimed" or "escalated".
        """
        # ── Step 1: Persist the ticket to SQLite ─────────────────────────────
        await workflow.execute_activity(
            save_ticket_activity,
            SaveTicketInput(ticket_id=inp.ticket_id, subject=inp.subject),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=ACTIVITY_RETRY,
        )

        # ── Step 2: Durable SLA wait ─────────────────────────────────────────
        # wait_condition with a timeout replaces the polling thread entirely.
        # If claim_signal fires before the timeout, we exit early (ticket claimed).
        # If the timeout expires, the ticket breached SLA → escalate.
        try:
            await workflow.wait_condition(
                lambda: self._claimed,
                timeout=timedelta(seconds=SLA_SECONDS),
            )
        except TimeoutError:
            pass  # SLA elapsed without a claim — proceed to escalation.

        # ── Step 3a: Claimed — persist to DB and finish ──────────────────────
        if self._claimed:
            await workflow.execute_activity(
                claim_ticket_activity,
                ClaimTicketInput(
                    ticket_id=inp.ticket_id,
                    agent=self._claimed_by or "unknown",
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=ACTIVITY_RETRY,
            )
            return "claimed"

        # ── Step 3b: SLA breached — escalate and notify ──────────────────────
        final_status: str = await workflow.execute_activity(
            escalate_ticket_activity,
            EscalateTicketInput(ticket_id=inp.ticket_id),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=ACTIVITY_RETRY,
        )

        if final_status == "escalated":
            breach_time = workflow.now().isoformat()
            await workflow.execute_activity(
                notify_manager_activity,
                NotifyManagerInput(
                    ticket_id=inp.ticket_id,
                    breach_time=breach_time,
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=ACTIVITY_RETRY,
            )

        return final_status
