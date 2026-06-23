# Architecture — Carfullfy SLA Escalation Engine

## Purpose

This document describes the system design for the Carfullfy SLA Escalation Engine: a ticketing service that guarantees an agent claims newly created tickets within a defined SLA window (1 hour in production, configurable to ~60s for local demos).

The focus is on correctness (no silent SLA losses), resilience across process restarts, and clear, auditable state transitions.

## High-level components

- Ticket API (HTTP): `POST /tickets`, `POST /tickets/{id}/claim`, `GET /tickets/{id}`
- Ticket store: persistent backing for tickets (relational DB, e.g. Postgres, or lightweight SQLite for single-node demos)
- SLA monitor/scheduler: durable job store + scheduler responsible for raising escalations when deadlines pass
- Escalation worker: idempotent worker that performs `notify_manager()` and marks ticket `escalated`
- Observability: structured logs and timestamps for all state transitions

## Data model (essential fields)

- Ticket: `id`, `subject`, `created_at`, `status` (open|claimed|escalated), `claimed_by`, `claimed_at`, `escalated_at`, `sla_deadline`
- SLA job record (optional if using external queue): `ticket_id`, `deadline`, `status` (pending|fired|cancelled)`

## Local (naïve) implementation — current failure mode

- On creation, an in-memory thread is spawned per ticket to wait for the SLA deadline.
- If the process restarts/crashes, all in-memory threads disappear and pending tickets remain `open` permanently.
- Result: SLA breaches are silently lost; no escalation is recorded.

## Robust design principles (requirements)

1. Durable scheduling: SLA deadlines must be persisted outside process memory so they survive restarts.
2. Idempotent escalation: multiple workers or retries must not cause duplicate escalations.
3. Atomic transitions: state changes (open→claimed, open→escalated) must be serialized to avoid races and double escalation.
4. Observable and auditable: every transition recorded with a timestamp and reason.

## Recommended solutions (options)

Option A — Persisted scheduler + worker (recommended):

- Store tickets and their `sla_deadline` in the database.
- A scheduler (simple cron or a small process) periodically queries for tickets where `status = open` and `sla_deadline <= now()` and enqueues idempotent escalation jobs.
- Workers consume jobs, run a transactional check-and-set: START TRANSACTION; SELECT FOR UPDATE the ticket row; if `status == open` set `status = escalated`, set `escalated_at`, commit; then call `notify_manager()` outside the transaction (or after commit).

Benefits: simple, no external queue required, survives restarts, supports horizontal scaling.

Option B — Use a durable queue with delayed messages (Redis Streams, RQ, Celery, RabbitMQ):

- On ticket creation, push a delayed job to the queue that becomes visible at the deadline.
- On claim, cancel the delayed job (or mark it cancelled in DB); worker checks job is still valid before escalation.

Benefits: precise deadline delivery, scalable; cost: extra infra and cancellation logic.

Option C — Hybrid: persist deadlines in DB and use the queue for quick delivery; scheduler reconciles periodically to handle missed messages.

## Concurrency control and idempotency

- Use row-level locking (SELECT ... FOR UPDATE) when performing the final status transition to guarantee atomicity.
- Generate an idempotency key for escalation worker runs (e.g., `escalate:ticket:{id}`) and persist worker attempts to avoid duplicate notifications.
- Write `escalated_at` only once; subsequent workers read and skip if already set.

## Failure handling and restart behavior

- On service start, the scheduler should scan for any `open` tickets with `sla_deadline <= now()` and enqueue escalations (recovery run).
- Ensure the escalation worker is idempotent so recovery runs cannot double-escalate.

## Observability and testing

- Record structured logs for events: `ticket_created`, `ticket_claimed`, `ticket_escalated`, and include timestamps and actor metadata.
- Unit tests: simulate concurrent claim + escalation attempts to assert exactly-one outcome.
- Integration: demo the failure mode by creating tickets, killing the process before deadlines, restarting, and showing that the scheduler recovers and escalates pending tickets.

## Deployment considerations

- Single-node demo: SQLite + scheduler cron job is acceptable for demonstration. Ensure scheduler runs frequently enough (e.g., every 5s for local demos).
- Production: use Postgres + background worker pool (Celery/RQ) or managed delayed-job service. Add health checks and metrics for pending SLA jobs.

## Summary

Move SLA scheduling from ephemeral in-memory threads to a durable, transactional mechanism. Use DB-backed deadlines or a durable delayed queue, combine with transactional updates and idempotent workers to guarantee that every SLA breach is detected and escalated exactly once, even after crashes or restarts.

