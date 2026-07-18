"""
Carfullfy SLA Escalation Engine - Temporal Worker.
Connects to the Temporal server and registers the SlaWorkflow and all
activities so they can be executed from the task queue.

Run this in a separate terminal AFTER starting the Temporal dev server:

    Terminal 1:  temporal server start-dev
    Terminal 2:  py src/worker.py
    Terminal 3:  py src/server.py

Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

try:
    from .temporal_activities import (
        claim_ticket_activity,
        escalate_ticket_activity,
        notify_manager_activity,
        save_ticket_activity,
    )
    from .temporal_workflow import SlaWorkflow, TASK_QUEUE
except ImportError:
    from temporal_activities import (
        claim_ticket_activity,
        escalate_ticket_activity,
        notify_manager_activity,
        save_ticket_activity,
    )
    from temporal_workflow import SlaWorkflow, TASK_QUEUE

TEMPORAL_HOST = "localhost:7233"


async def main() -> None:
    print(f"Connecting to Temporal server at {TEMPORAL_HOST} ...")
    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[SlaWorkflow],
        activities=[
            save_ticket_activity,
            escalate_ticket_activity,
            notify_manager_activity,
            claim_ticket_activity,
        ],
    )

    print(f"Worker started on task queue '{TASK_QUEUE}'. Press Ctrl+C to stop.")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
