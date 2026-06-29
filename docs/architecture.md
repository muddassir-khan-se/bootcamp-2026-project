# Architecture — Carfullfy SLA Escalation Engine

> **System Design & Core Architecture**

---

## 1. Problem Statement & Invariant

- **Defect in naive design:** Per-ticket `threading.Thread` timers vanish on process crash, leaving overdue tickets `open` indefinitely.
- **Core Invariant:** SLA enforcement must survive process restarts with **zero missed escalations** and **no double-escalations**.

---

## 2. Ticket Lifecycle & State Machine

```
   create_ticket()             SLA Breach (5s scheduler)
      │                            │
      ▼                            ▼
  ┌────────┐                  ┌───────────┐
  │  open  │─────────────────▶│ escalated │ (Terminal)
  └────────┘                  └───────────┘
      │
      │ claim_ticket()
      ▼
  ┌────────┐
  │claimed │ (Terminal)
  └────────┘
```

---

## 3. Sequence Diagrams

### Normal Claim Flow
```
Client          Server / Service         SQLite DB
  │                    │                     │
  ├─ POST /tickets ───▶├─ INSERT ticket ────▶│ (sla_deadline = now + 60s)
  │◀─ 201 Created ─────┤                     │
  │                    │                     │
  ├─ POST /claim ─────▶├─ UPDATE claimed ───▶│ (WHERE status = 'open')
  │◀─ 200 OK ──────────┤                     │
```

### Crash Recovery Flow
```
Client / Sched     Server / Service      SQLite DB
  │                    │                     │
  │     ── Server Crash / Downtime ──        │ (DB retains sla_deadline)
  │                    │                     │
  ├─ Server Restart ──▶├─ Startup Recovery ──▶│ (SELECT overdue open tickets)
  │                    ├─ UPDATE escalated ─▶│ (WHERE status = 'open')
  │                    ├─ Log notify.log ────▶│
```

---

## 4. Component Summary

| Component | Responsibility | Key Mechanics |
| :--- | :--- | :--- |
| **`src/db.py`** | Persistence | SQLite WAL mode, foreign keys, module-level `threading.Lock` |
| **`src/models.py`** | Data Model | `Ticket` dataclass, UTC datetime handling, `to_dict()` JSON helper |
| **`src/ticket_service.py`**| Business Logic | Atomic state transitions, SLA calculation, notification logging |
| **`src/sla_scheduler.py`**  | Daemon Scheduler| 5s polling thread, immediate startup crash recovery scan |
| **`src/server.py`**         | HTTP Server | REST routing, CORS headers, static file dashboard server |
| **`src/static/`**         | Frontend UI | Single-page application, real-time polling, dark mode, toast alerts |

---

## 5. Concurrency & State Invariant Guarantee

To prevent race conditions between concurrent agent claims and automated escalations, state updates execute via conditional SQL check-and-set:

```sql
-- Executed by both claim and escalation routines
UPDATE tickets
   SET status = :new_status, claimed_by = :agent, claimed_at = :time
 WHERE id = :ticket_id AND status = 'open';
```

- **Execution Safety:** SQLite serializes writes. If `rowcount == 0`, the state was already modified by a competing thread, resulting in a safe, silent no-op.

---

## 6. Architecture Trade-offs Summary

| Pattern | Implementation Status | Evaluation |
| :--- | :--- | :--- |
| **DB-Backed Scheduler (Option A)** | **Implemented** | Simple, persistent, self-recovering on restart, zero external dependencies. |
| **Delayed Job Queue (Option B)** | Alternative | Requires Redis/RabbitMQ. Ideal for massive production throughput. |
| **Hybrid Reconciliation (Option C)**| Alternative | Combines queues with periodic DB cleanup for maximum fault tolerance. |
