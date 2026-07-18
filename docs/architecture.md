# System Architecture — Carfullfy SLA Escalation Engine

> **Document Type:** Comprehensive Architectural Specification  
> **Target Audience:** Core Developers, Technical Reviewers, System Architects  
> **Author:** Muddassir Khan | Bootcamp 2026

---

## Table of Contents

1. [Architectural Purpose & Core Mandate](#1-architectural-purpose--core-mandate)
2. [Problem Statement & Failure Analysis](#2-problem-statement--failure-analysis)
3. [Ticket Lifecycle & State Transitions](#3-ticket-lifecycle--state-transitions)
   - [Finite State Machine](#finite-state-machine)
   - [Lifecycle Sequence Diagrams](#lifecycle-sequence-diagrams)
4. [System Component Specifications](#4-system-component-specifications)
5. [Durable Scheduling Architecture Options](#5-durable-scheduling-architecture-options)
6. [Concurrency Control & Atomic Guards](#6-concurrency-control--atomic-guards)
7. [Crash Recovery & Fault Tolerance Mechanics](#7-crash-recovery--fault-tolerance-mechanics)
8. [Observability, Telemetry & Auditing](#8-observability-telemetry--auditing)
9. [Verification & Testing Strategy](#9-verification--testing-strategy)
10. [Architectural Decision Record (ADR) Summary](#10-architectural-decision-record-adr-summary)

---

## 1. Architectural Purpose & Core Mandate

The **Carfullfy SLA Escalation Engine** is designed to provide robust, fail-safe Customer Support Ticket SLA management. The core mandate of the system is to guarantee that every support query submitted by a customer is claimed by an agent within a strict **60-second Service Level Agreement (SLA)** window.

If an open ticket is not claimed within this period, the system must reliably trigger an automated manager escalation. Crucially, the system is architected to fulfill this mandate with **100% durability guarantee**—ensuring that process crashes, unexpected server shutdowns, or maintenance restarts never cause an expired ticket to be silently forgotten or left in an un-escalated state.

---

## 2. Problem Statement & Failure Analysis

### The Naive Reference Implementation Defect
In naive or prototype ticketing architectures, SLA countdown timers are frequently implemented as in-memory background threads or ephemeral event timers (e.g., spawning a `threading.Timer` or `asyncio` task per ticket).

**The Ephemeral Failure Mode:**
1. A customer submits a ticket at `12:00:00`, creating an in-memory timer set to expire at `12:01:00`.
2. At `12:00:30`, the application process crashes or is restarted for a deployment.
3. Upon process restart, all active operating system threads and event loops are destroyed.
4. While the ticket record might exist in a database, the associated countdown thread is permanently gone.
5. The ticket remains stuck in the `open` state indefinitely, completely bypassing SLA monitoring and manager escalation.

### The Durable Solution Requirements
To eliminate this defect, the Carfullfy architecture enforces three fundamental principles:
- **State Externalization:** All SLA expiration targets (`sla_deadline`) are calculated immediately upon creation and committed to persistent storage (`tickets.db`).
- **Stateless Background Monitoring:** SLA verification relies on periodic database queries rather than running in-memory timers.
- **Immediate Startup Recovery:** Upon initialization, the background engine executes an immediate sweep of persistent storage to catch up on any deadlines that expired during downtime.

---

## 3. Ticket Lifecycle & State Transitions

### Finite State Machine

A ticket strictly transitions through three mutually exclusive states. Once a ticket exits the `open` state and reaches a terminal state (`claimed` or `escalated`), no further state modifications are permitted by the system.

```
                  create_ticket()
                         │
                         ▼
                  ┌─────────────┐
                  │    open     │
                  └─────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         │ claim_signal (Temporal)       │ SLA Breach (SlaWorkflow timeout)
         ▼                               ▼
  ┌─────────────┐                 ┌─────────────┐
  │   claimed   │                 │  escalated  │
  └─────────────┘                 └─────────────┘
    (Terminal)                      (Terminal)
```

#### State Transition Matrix

| Initial State | Target State | Triggering Actor | Execution Mechanism | Business Condition |
| :--- | :--- | :--- | :--- | :--- |
| **N/A** | `open` | Customer / User | `POST /tickets` (starts `SlaWorkflow`) | Ticket submitted; `sla_deadline` set to `created_at + 60s`. |
| `open` | `claimed` | Support Agent | `POST /tickets/{id}/claim` (sends `claim_signal` to `SlaWorkflow`) | Agent submits claim within the 60-second SLA deadline window. |
| `open` | `escalated` | Temporal Workflow | `SlaWorkflow.run()` (`workflow.wait_condition`) | SLA deadline expires and ticket remains unclaimed. |

---

### Lifecycle Sequence Diagrams

#### Normal Claim Flow (SLA Satisfied)
This diagram illustrates a standard scenario where a support agent claims an open ticket well before the 60-second deadline expires.

```
Client / Dashboard         HTTP Server (server.py)        Temporal Server (port 7233)            SQLite Database (tickets.db)
        │                            │                                   │                                    │
        ├─── POST /tickets ─────────▶│                                   │                                    │
        │    {"subject": "Issue"}    ├─── start_workflow() ─────────────▶│                                    │
        │                            │                                   ├─── save_ticket_activity ──────────▶│
        │                            │                                   │    (id, status='open', deadline)  │
        │◀── 201 Created (JSON) ─────┤◀── ticket row ready ──────────────┤◀── Transaction Committed ─────────┤
        │                            │                                   │                                    │
        │  (Agent reviews dashboard  │                                   │                                    │
        │   and clicks Claim)        │                                   │                                    │
        │                            │                                   │                                    │
        ├─── POST /tickets/{id}/claim▶│                                   │                                    │
        │    {"agent": "Agent A"}    ├─── handle.signal(claim_signal) ──▶│                                    │
        │                            │                                   ├─── claim_ticket_activity ─────────▶│
        │                            │                                   │    status='claimed', claimed_by... │
        │                            │                                   │    WHERE id=? AND status='open'    │
        │                            │◀── poll DB until claimed ─────────┤◀── 1 Row Updated ──────────────────┤
        │◀── 200 OK (JSON) ──────────┤                                   │                                    │
```

---

#### SLA Breach & Automated Recovery Flow (Durable Recovery via Temporal)
This diagram details how the system guarantees SLA escalations survive server crashes by leveraging Temporal's event sourcing and replay recovery mechanism.

```
Client / Dashboard         HTTP Server / Worker          Temporal Server (localhost:7233)       SQLite Database (tickets.db)
        │                            │                                   │                                    │
        ├─── POST /tickets ─────────▶├─── start_workflow() ─────────────▶│                                    │
        │                            │                                   ├─── schedules save_ticket_activity ▶│
        │◀── 201 Created ────────────┤◀── workflow started ──────────────┤                                    │
        │                            │                                   │                                    │
        │   ⚡⚡ SERVER/WORKER CRASHES AT 12:00:30 ⚡⚡                 │                                    │
        │   (In-memory state lost. Temporal Server tracks workflow progress, timers, and pending activities)  │
        │                            │                                   │                                    │
        │   🕒 SLA deadline (12:01:00) passes. Temporal Server tracks timer expiration.                       │
        │                            │                                   │                                    │
        │   🔄 SERVER/WORKER RESTARTS AT 12:02:00                       │                                    │
        │                            ├─── worker.run() reconnects ───────▶│                                    │
        │                            │                                   ├─── delivers expired timer task     │
        │                            │◀── replays SlaWorkflow ───────────┤                                    │
        │                            ├─── executes escalation path ──────▶│                                    │
        │                            │    ├─ escalate_ticket_activity ───▶├─── UPDATE status='escalated' ────▶│
        │                            │    ├─ notify_manager_activity ─────▶│─── Appends entry to notify.log ──▶│
        │                            │    └───────────────────────────────┘                                   │
        ├─── GET /tickets ──────────▶├─── get_all_tickets() ─────────────────────────────────────────────────▶│
        │◀── 200 OK (escalated) ─────┤                                                                        │
```

---

## 4. System Component Specifications

The system follows a modular, layered architecture designed to separate database persistence, domain logic, HTTP routing, and client representation.

### 1. Database Persistence Layer (`src/db.py`)
- **Responsibility:** Manages SQLite connection pooling, transactional context managers, thread safety, and physical file initialization.
- **Key Specifications:**
  - **WAL Journaling:** Configures `PRAGMA journal_mode = WAL` (Write-Ahead Logging) to allow high-concurrency concurrent read operations alongside write transactions.
  - **Thread Synchronization:** Encapsulates connection acquisition within a global module thread lock (`DB_LOCK`) to prevent multi-threaded SQLite lock contention.
  - **Configurability:** Dynamically resolves storage location via the `TICKETS_DB_PATH` environment variable, falling back to a root-level `./tickets.db` file.

### 2. Domain Models (`src/models.py`)
- **Responsibility:** Provides strongly-typed data structures representing domain entities.
- **Key Specifications:**
  - **Dataclass `Ticket`:** Encapsulates attributes including `id` (UUID v4 string), `subject`, `created_at` (UTC datetime), `status` (`open`, `claimed`, `escalated`), `claimed_by`, `claimed_at`, `escalated_at`, and `sla_deadline`.
  - **Serialization:** Provides `to_dict()` helper functions converting native Python `datetime` objects into standardized ISO 8601 UTC strings for HTTP JSON payloads.

### 3. Service Business Logic (`src/ticket_service.py`)
- **Responsibility:** Executes core domain database operations and enforces business invariants.
- **Key Specifications:**
  - `create_ticket(subject)`: Generates UUID, captures `utcnow()`, sets `sla_deadline = created_at + 60s`, executes SQL insertion.
  - `claim_ticket(id, agent)`: Executes atomic check-and-set update setting status to `claimed`.
  - `escalate_ticket(id)`: Atomic conditional update setting status to `escalated` if still open.
  - `notify_manager(id, breach_time)`: Appends breach log to `notify.log`.

### 4. Temporal Activities (`src/temporal_activities.py`)
- **Responsibility:** Exposes core database operations as retryable, durable Activities callable from the workflow.
- **Key Specifications:**
  - `@activity.defn` decorated async functions: `save_ticket_activity`, `claim_ticket_activity`, `escalate_ticket_activity`, `notify_manager_activity`.
  - **Retry Policy:** Up to 3 attempts with 2-second initial back-off interval.

### 5. SLA Workflow (`src/temporal_workflow.py`)
- **Responsibility:** Manages the full ticket lifecycle as a durable, crash-resilient state machine.
- **Key Specifications:**
  - `SlaWorkflow` (`@workflow.defn`): One instance per ticket, identified by ticket UUID as Workflow ID.
  - **Durable timer**: `workflow.wait_condition(timeout=60s)` replaces all polling threads.
  - **Signal**: `claim_signal(agent)` received from HTTP handler causes the timer branch to exit cleanly.

### 6. Temporal Worker (`src/worker.py`)
- **Responsibility:** Bridges the Temporal server to local workflow/activity code.
- **Key Specifications:**
  - Registers `SlaWorkflow` and all four activities on the `"sla-ticket-queue"` task queue.
  - Must be running alongside a Temporal dev server for workflows to execute.

### 7. HTTP Web Server & Router (`src/server.py`)
- **Responsibility:** Exposes RESTful HTTP API endpoints and routes static web dashboard assets.
- **Key Specifications:**
  - **Native HTTP Server:** Extends `BaseHTTPRequestHandler` to handle `GET`, `POST`, and `OPTIONS` requests cleanly without external framework overhead.
  - **Temporal Bridge:** Runs an asyncio event loop in a background thread; `_run_async()` submits coroutines to it from the synchronous handler.
  - **POST /tickets:** Generates UUID → starts `SlaWorkflow` via Temporal Client → polls SQLite for the row.
  - **POST /tickets/{id}/claim:** Sends `claim_signal` to the workflow handle → polls SQLite until `status = 'claimed'`.
  - **CORS Support:** Emits `Access-Control-Allow-Origin: *` headers on all responses.

### 8. Frontend Single-Page Application (`src/static/`)
- **Responsibility:** Provides real-time user interface for monitoring tickets, creating issues, claiming workloads, and viewing activity logs.
- **Key Specifications:**
  - **Real-Time Polling:** Automatically polls `/tickets` every 3 seconds to update ticket counts and status grids.
  - **Visual SLA Countdown:** Client-side 1-second interval timer calculating remaining seconds and rendering dynamic CSS progress bars (Green for >30s, Orange for >10s, Red for <10s).
  - **Interactive Features:** Status filter tabs, keyword search, dark mode toggle, keyboard shortcut (`N`), and animated toast notification pop-ups.

---

## 5. Durable Scheduling Architecture Options

During the architectural design phase, three primary scheduling models were evaluated for handling SLA expirations:

| Evaluation Criteria | Option A: DB-Backed Scheduler | Option B: Durable Delayed Queue | Option C: Temporal Workflow (Selected) |
| :--- | :--- | :--- | :--- |
| **Mechanics** | SLA deadlines stored in DB rows; a periodic background thread queries overdue rows. | SLA jobs enqueued into a delayed queue (e.g., Redis/Celery); queue fires worker at deadline. | SLA logic encapsulated in durable workflows using event-sourced state machines. |
| **Crash Recovery** | **Automatic & Instant:** Startup DB scan catches all tickets expired during downtime. | **Queue Dependent:** Requires persistent queue disk snapshots to survive restarts. | **Event-Sourced:** Temporal server replays event logs to resume timers instantly upon worker restart. |
| **Dependencies** | **Zero External Dependencies:** Relies entirely on built-in SQLite database engine. | **High Dependencies:** Requires dedicated message broker infrastructure (Redis, RabbitMQ). | **Managed Infrastructure:** Requires Temporal Server (which manages queue state/timers internally). |
| **Operational Overhead**| **Minimal:** Single Python daemon process co-located with HTTP server. | **Moderate to High:** Requires managing worker pools, broker health, and queue monitoring. | **Scalable:** Temporal manages workflow durability; worker simply executes code. |
| **Architectural Choice**| Evaluated | Evaluated | **SELECTED FOR IMPLEMENTATION** |

---

## 6. Concurrency Control & Atomic Guards

In a multi-threaded web server environment, a critical race condition could occur if a support agent attempts to claim a ticket at the exact same millisecond that the Temporal SLA Workflow attempts to escalate it.

### The Race Condition Risk
Without concurrency guards, both operations might read `status == 'open'` simultaneously, leading to state corruption where a ticket is marked as both `claimed` and `escalated`, or triggering duplicate manager notifications.

### The Atomic Check-and-Set Guard
To guarantee that a ticket resolves into exactly **one** terminal state, both claim and escalation operations execute using atomic, conditional SQL updates:

```sql
-- Executed during Agent Claim (temporal_activities.py)
UPDATE tickets
   SET status = 'claimed',
       claimed_by = :agent,
       claimed_at = :timestamp
 WHERE id = :ticket_id
   AND status = 'open';
```

```sql
-- Executed during Automated Escalation (temporal_activities.py)
UPDATE tickets
   SET status = 'escalated',
       escalated_at = :timestamp
 WHERE id = :ticket_id
   AND status = 'open';
```

### Execution Behavior Under Contention
1. **Database Locking:** SQLite serializes write transactions. When competing threads issue updates simultaneously, SQLite processes them sequentially.
2. **First Transaction Wins:** The first transaction successfully updates the row from `open` to its target state (`claimed` or `escalated`) and commits.
3. **Second Transaction Fails Safely:** When the second transaction executes, the conditional clause `WHERE status = 'open'` evaluates to `FALSE` because the status has already changed.
4. **Zero Impact:** SQLite returns `rowcount == 0`. The application code detects `rowcount == 0` and safely aborts without modifying data or sending duplicate notifications.

---

## 7. Crash Recovery & Fault Tolerance Mechanics

The system's fault tolerance model guarantees zero lost escalations across unexpected process restarts.

### Startup Recovery Sequence
Whenever the worker and server restart, Temporal's event sourcing mechanism automatically recovers all in-flight workflows:

```
[1. Worker Startup Initiated]
              │
              ▼
[2. Connect to Temporal Server] ──▶ Resolves connection on localhost:7233
              │
              ▼
[3. Register SlaWorkflow + Activities] ──▶ Registers workflow definitions
              │
              ▼
[4. Subscribe to Task Queue] ──────▶ Listens on "sla-ticket-queue"
              │
              ▼
[5. Temporal Replay Scan] ─────────▶ Server replays workflow event history
              │
              ▼
[6. Resume Durable Timer] ─────────▶ workflow.wait_condition resumes remaining SLA time
              │
              ▼
[7. Process Expired Deadlines] ────▶ Automatically fires overdue escalation activities
              │
              ▼
[8. DB Updated Atomically] ────────▶ escalate_ticket_activity + notify_manager_activity run
```

---

## 8. Observability, Telemetry & Auditing

The architecture enforces comprehensive audit logging and telemetry across all system layers to support post-mortem analysis and operational reporting.

### 1. Persistent Transition Audit Logging (`notify.log`)
Whenever an SLA breach occurs and a ticket is escalated, the system writes an append-only audit record to `notify.log`:
```text
[notify_manager] Ticket e4b3c1a2-9f8e-4b7c-8a1d-2e3f4a5b6c7d breached SLA at 2026-06-29T12:01:00.000000
```

### 2. Live Web Dashboard Telemetry
The frontend dashboard provides real-time visibility into system metrics and state transitions:
- **Dynamic Counter Cards:** Renders real-time aggregate counts for Total, Open, Claimed, and Escalated tickets with visual pop animations on value changes.
- **Client-Side Audit Activity Feed:** Displays a scrollable timeline log capturing ticket creation, agent assignment, and escalation events with exact time markers.
- **Visual Urgency Progress Bars:** Renders animated progress bars displaying exact remaining SLA countdown seconds.

---

## 9. Verification & Testing Strategy

The repository includes an automated testing suite implemented via `pytest` to validate core architectural guarantees:

| Test Module | Coverage Area | Architectural Properties Verified |
| :--- | :--- | :--- |
| **`tests/test_api.py`** | Direct Service Layer | Validates `ticket_service.py` functions: create, claim, get, conflict detection. |
| **`tests/test_client.py`** | HTTP SDK Integration | Verifies programmatic Python HTTP client methods with Temporal Client mocked out. |
| **`tests/test_temporal_activities.py`** | Temporal Activities | Tests all four activities: `save_ticket`, `claim_ticket`, `escalate_ticket`, `notify_manager`. |

---

## 10. Architectural Decision Record (ADR) Summary

| Decision Identifier | Architectural Subject | Chosen Decision | Rational & Justification |
| :--- | :--- | :--- | :--- |
| **ADR-001** | Persistence Layer | SQLite with WAL Mode | Eliminates external database infrastructure management while supporting concurrent reads and reliable disk persistence for demos. |
| **ADR-002** | SLA Storage Strategy | Pre-calculated Expiration | Storing `sla_deadline` directly in ticket rows allows simple, high-performance SQL indexing and stateless background querying. |
| **ADR-003** | Concurrency Protection | SQL Conditional Check-and-Set | Using `WHERE status = 'open'` within SQL statements guarantees race-condition protection without requiring complex distributed locks. |
| **ADR-004** | Durable Timers | Temporal Workflow Engine | Replacing custom scheduler loops with Temporal's event-sourced `workflow.sleep` provides absolute crash survival guarantees. |
| **ADR-005** | Frontend Delivery | Vanilla JS/CSS (No Build Step) | Serving static files directly via HTTP server eliminates Node.js build dependencies while delivering high-performance UI components. |
