# Architecture — Carfullfy SLA Escalation Engine

## Purpose

This document describes the system design for the Carfullfy Customer Support SLA Escalation Engine. The system must guarantee that every newly created ticket is claimed within a 1-hour SLA and that any unclaimed ticket is escalated, even if the application process restarts or crashes.

## Problem statement

The local reference implementation uses an in-memory background thread per ticket to track the SLA countdown. When the runtime restarts or crashes, those per-ticket threads disappear and tickets that are still open are left without escalation. This causes SLA breaches to be silently lost.

## Local implementation details

### Ticket API

The ticket API should provide the following endpoints:

- `POST /tickets` — create a ticket with fields: `id`, `subject`, `created_at`, `status = open`.
- `POST /tickets/{id}/claim` — claim a ticket, setting `status = claimed`, recording `claimed_by`, and `claimed_at`.
- `GET /tickets/{id}` — inspect the ticket state.

Tickets in the naive local system are held in a shared in-memory dictionary, guarded by a lock.

### SLA monitor thread

For each ticket created, the naive local implementation spawns one `threading.Thread`:

- The thread waits up to 1 hour (locally configurable to ~60s).
- It either polls the ticket status periodically or waits on a `threading.Event` that the claim endpoint sets.
- If the ticket becomes `claimed` before the deadline, the thread exits.
- If the deadline passes and the ticket is still `open`, the thread performs the escalation action:
  - call `notify_manager()` (console/log/file entry),
  - set `status = escalated`,
  - record `escalated_at`.

### Local failure mode

- Many open tickets can exist at once, each with its own independent SLA thread.
- If the process restarts or crashes while tickets are pending, the threads are gone.
- The ticket rows can be reloaded if persisted, but the SLA timers are lost.
- Unclaimed tickets remain `open` forever, and SLA breaches are not detected or escalated.

## Requirements

- Support many open tickets concurrently, each monitored independently.
- Enforce the state transitions: `open → claimed` or `open → escalated`.
- Timestamp and log all state transitions.
- Prevent double escalation: if a claim arrives at the same moment a timeout fires, only one outcome should happen.

## Durable architecture design

### Core components

- **Ticket service**
  - Handles ticket lifecycle through API calls.
  - Stores tickets persistently in a durable backend.
- **SLA scheduler**
  - Maintains deadline state outside process memory.
  - Periodically finds open tickets whose SLA deadline has passed.
- **Escalation worker**
  - Processes expiring tickets.
  - Uses transactional state checks to ensure only one outcome occurs.
- **Persistence layer**
  - Stores ticket state and SLA deadline.
  - Could be a relational database such as SQLite for demos or Postgres in production.

### Data model

- `Ticket`
  - `id`
  - `subject`
  - `created_at`
  - `status` (`open`, `claimed`, `escalated`)
  - `claimed_by`
  - `claimed_at`
  - `escalated_at`
  - `sla_deadline`

- `SLA job` (optional)
  - `ticket_id`
  - `deadline`
  - `status` (`pending`, `cancelled`, `processed`)

## Durable SLA options

### Option A — DB-backed scheduler (recommended)

- Persist ticket data and `sla_deadline` in the database.
- On ticket creation, store the deadline in the ticket row.
- A scheduler periodically queries for `open` tickets with `sla_deadline <= now()`.
- Each matching ticket is processed by an escalation worker.
- The worker performs a transactional update:
  - `SELECT ... FOR UPDATE` the ticket row.
  - If `status == open`, set `status = escalated`, set `escalated_at`, commit.
  - If `status != open`, skip.
- Notify managers after the transaction completes.

**Why this works**
- SLA deadlines survive process restarts.
- Recovery on restart is natural because the scheduler re-scans the database.
- Idempotency is easy with a transactional check.

### Option B — durable delayed job queue

- On ticket creation, enqueue a delayed job for the SLA deadline.
- If the ticket is claimed before the deadline, cancel or mark the job as invalid.
- When the delayed job becomes visible, the worker checks ticket state and escalates if still `open`.

**Why this works**
- Delay semantics are handled by the queue.
- The queue is durable across restarts.
- Requires support for cancelling or invalidating delayed jobs.

### Option C — hybrid reconciliation

- Store deadlines in the database and also use delayed jobs for precise delivery.
- On startup, run a reconciliation pass to catch missed deadlines.
- Optionally, use a periodic cleaner as a backup.

## Concurrency and no double escalation

- Use atomic transitions and locking.
- The escalation worker must verify ticket state inside a single transaction.
- Example pattern:
  - BEGIN TRANSACTION
  - SELECT ticket FOR UPDATE
  - if `status == open`: update to `escalated`
  - COMMIT
- If `claim` occurs concurrently, the first committed transaction wins.
- If both threads race, the second should observe the updated state and do nothing.

## Recovering from crashes

- On process restart, the scheduler should run immediately and scan for overdue tickets.
- Tickets still marked `open` with a deadline in the past should be escalated.
- This ensures SLA violations are not lost when the service restarts.

## Observability and auditing

- Log every transition with:
  - ticket id
  - previous status
  - new status
  - actor / reason
  - timestamp
- Example events:
  - `ticket_created`
  - `ticket_claimed`
  - `ticket_escalated`
- For local demo, `notify_manager()` can write to console or local file.

## Testing strategy

- Unit test the ticket lifecycle and transition rules.
- Concurrency tests should assert exactly one result when claim and escalation race.
- Failure demo should cover:
  - create ticket
  - restart process before escalation
  - verify scheduler recovers and escalates pending ticket

## Recommended local implementation

For the Bootcamp demo, the simplest robust approach is:

1. Persist tickets in SQLite.
2. Create `sla_deadline` on ticket creation.
3. Use a scheduler loop every few seconds to query expired open tickets.
4. Escalate in a transaction if still open.
5. On startup, run a recovery scan.

This avoids the unreliable in-memory thread model while still supporting the required SLA behavior.

## Summary

The key defect in the local implementation is using ephemeral in-memory threads for SLA timers. The durable design stores deadlines in persistent storage and uses a scheduler/worker model so SLA breaches are detected and escalated even after process restarts, while ensuring only one final status transition occurs.
