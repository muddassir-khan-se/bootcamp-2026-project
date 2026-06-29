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
         │ claim_ticket()                │ SLA Breach (SlaScheduler)
         ▼                               ▼
  ┌─────────────┐                 ┌─────────────┐
  │   claimed   │                 │  escalated  │
  └─────────────┘                 └─────────────┘
    (Terminal)                      (Terminal)
```

#### State Transition Matrix

| Initial State | Target State | Triggering Actor | Execution Mechanism | Business Condition |
| :--- | :--- | :--- | :--- | :--- |
| **N/A** | `open` | Customer / User | `POST /tickets` | Ticket submitted; `sla_deadline` set to `created_at + 60s`. |
| `open` | `claimed` | Support Agent | `POST /tickets/{id}/claim` | Agent submits claim within the 60-second SLA deadline window. |
| `open` | `escalated` | Background Engine | `SlaScheduler.run()` | `sla_deadline <= current_timestamp` and ticket remains unclaimed. |

---

### Lifecycle Sequence Diagrams

#### Normal Claim Flow (SLA Satisfied)
This diagram illustrates a standard scenario where a support agent claims an open ticket well before the 60-second deadline expires.

```
Client / Dashboard         HTTP Server (server.py)       Service Layer (ticket_service.py)       SQLite Database (tickets.db)
        │                            │                                   │                                    │
        ├─── POST /tickets ─────────▶│                                   │                                    │
        │    {"subject": "Issue"}    ├─── create_ticket(subject) ───────▶│                                    │
        │                            │                                   ├─── INSERT INTO tickets ───────────▶│
        │                            │                                   │    (id, status='open', deadline)  │
        │                            │◀── Return Ticket Object ──────────┤◀── Transaction Committed ─────────┤
        │◀── 201 Created (JSON) ─────┤                                   │                                    │
        │                            │                                   │                                    │
        │  (Agent reviews dashboard  │                                   │                                    │
        │   and clicks Claim)        │                                   │                                    │
        │                            │                                   │                                    │
        ├─── POST /tickets/{id}/claim▶│                                   │                                    │
        │    {"agent": "Agent A"}    ├─── claim_ticket(id, agent) ──────▶│                                    │
        │                            │                                   ├─── UPDATE tickets SET ────────────▶│
        │                            │                                   │    status='claimed', claimed_by... │
        │                            │                                   │    WHERE id=? AND status='open'    │
        │                            │◀── Return Updated Ticket ─────────┤◀── 1 Row Updated ──────────────────┤
        │◀── 200 OK (JSON) ──────────┤                                   │                                    │
```

---

#### SLA Breach & Automated Recovery Flow (Process Restart Handling)
This diagram details how the system gracefully recovers when a server crash occurs while tickets are pending escalation.

```
Client / Dashboard         HTTP Server / Daemon          Service Layer (ticket_service.py)       SQLite Database (tickets.db)
        │                            │                                   │                                    │
        ├─── POST /tickets ─────────▶├─── create_ticket() ──────────────▶├─── INSERT INTO tickets ───────────▶│
        │◀── 201 Created ────────────┤                                   │    (deadline = 12:01:00)          │
        │                            │                                   │                                    │
        │   ⚡⚡ SERVER CRASHES / UNEXPECTED SHUTDOWN AT 12:00:30 ⚡⚡    │                                    │
        │   (In-memory process destroyed. Database retains ticket record)│                                    │
        │                            │                                   │                                    │
        │   🕒 Downtime occurs. SLA deadline (12:01:00) passes.          │                                    │
        │                            │                                   │                                    │
        │   🔄 SERVER RESTARTS AT 12:02:00                               │                                    │
        │                            ├─── init_ticket_table() ──────────▶├─── Verify Schema ─────────────────▶│
        │                            ├─── SlaScheduler.start() ──────────┐                                    │
        │                            │    ├── IMMEDIATE RECOVERY SCAN ───┴───▶ get_due_tickets() ────────────▶│
        │                            │    │                                   SELECT WHERE status='open'     │
        │                            │    │                                   AND sla_deadline <= NOW()      │
        │                            │    │◀── Returns Overdue Ticket List ──────────────────────────────────┤
        │                            │    │                                   │                                    │
        │                            │    ├── escalate_due_tickets() ────────▶ escalate_ticket(id) ───────────▶│
        │                            │    │                                   UPDATE SET status='escalated'  │
        │                            │    │                                   WHERE id=? AND status='open'   │
        │                            │    │                                   │                                    │
        │                            │    ├── notify_manager() ──────────────▶ Appends entry to notify.log     │
        │                            │    └──────────────────────────────────┘                               │
        │                            │                                                                       │
        ├─── GET /tickets ──────────▶├─── get_all_tickets() ─────────────▶ SELECT * FROM tickets ───────────▶│
        │◀── 200 OK (escalated) ─────┤                                                                       │
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
- **Responsibility:** Executes core domain operations and enforces business invariants.
- **Key Specifications:**
  - `create_ticket(subject)`: Generates a unique UUID, captures `utcnow()`, sets `sla_deadline = created_at + 60s`, and executes SQL insertion.
  - `claim_ticket(id, agent)`: Executes atomic check-and-set updates setting status to `claimed`.
  - `escalate_due_tickets()`: Queries all tickets matching `status = 'open'` and `sla_deadline <= now()`, triggering `escalate_ticket()` and writing audit alerts to `notify.log`.

### 4. SLA Background Daemon (`src/sla_scheduler.py`)
- **Responsibility:** Provides continuous background polling and startup recovery verification.
- **Key Specifications:**
  - **Daemon Thread:** Subclasses `threading.Thread(daemon=True)` to run in background without blocking clean server shutdown.
  - **Poller Mechanics:** Operates on a 5-second sleep interval configured with a `threading.Event` stop signal.
  - **Immediate Recovery Sweep:** Overrides initial run behavior to execute an immediate escalation check prior to entering the sleep loop, ensuring zero startup latency for overdue tickets.

### 5. HTTP Web Server & Router (`src/server.py`)
- **Responsibility:** Exposes RESTful HTTP API endpoints and routes static web dashboard assets.
- **Key Specifications:**
  - **Native HTTP Server:** Extends `BaseHTTPRequestHandler` to handle `GET`, `POST`, and `OPTIONS` requests cleanly without external framework overhead.
  - **Static Asset Serving:** Automatically resolves and serves static frontend files (`index.html`, `style.css`, `app.js`) with accurate MIME headers (`text/html`, `text/css`, `application/javascript`).
  - **CORS Support:** Emits `Access-Control-Allow-Origin: *` headers on all responses to support browser-based API integrations.

### 6. Frontend Single-Page Application (`src/static/`)
- **Responsibility:** Provides real-time user interface for monitoring tickets, creating issues, claiming workloads, and viewing activity logs.
- **Key Specifications:**
  - **Real-Time Polling:** Automatically polls `/tickets` every 3 seconds to update ticket counts and status grids.
  - **Visual SLA Countdown:** Client-side 1-second interval timer calculating remaining seconds and rendering dynamic CSS progress bars (Green for >30s, Orange for >10s, Red for <10s).
  - **Interactive Features:** Status filter tabs, keyword search, dark mode toggle, keyboard shortcut (`N`), and animated toast notification pop-ups.

---

## 5. Durable Scheduling Architecture Options

During the architectural design phase, three primary scheduling models were evaluated for handling SLA expirations:

| Evaluation Criteria | Option A: DB-Backed Scheduler (Selected) | Option B: Durable Delayed Queue | Option C: Hybrid Reconciliation |
| :--- | :--- | :--- | :--- |
| **Mechanics** | SLA deadlines stored in DB rows; a periodic background thread queries overdue rows. | SLA jobs enqueued into a delayed queue (e.g., Redis/Celery); queue fires worker at deadline. | Delayed queue handles primary execution; DB background thread runs periodic safety sweeps. |
| **Crash Recovery** | **Automatic & Instant:** Startup DB scan catches all tickets expired during downtime. | **Queue Dependent:** Requires persistent queue disk snapshots to survive restarts. | **Fully Redundant:** Queue recovers jobs; DB scan provides absolute safety net. |
| **Dependencies** | **Zero External Dependencies:** Relies entirely on built-in SQLite database engine. | **High Dependencies:** Requires dedicated message broker infrastructure (Redis, RabbitMQ). | **Highest Dependencies:** Requires both database storage and message queue infrastructure. |
| **Operational Overhead**| **Minimal:** Single Python daemon process co-located with HTTP server. | **Moderate to High:** Requires managing worker pools, broker health, and queue monitoring. | **Complex:** Requires orchestrating queue state synchronization with database state. |
| **Architectural Choice**| **SELECTED FOR IMPLEMENTATION** | Evaluated for enterprise scale | Evaluated for mission-critical scale |

---

## 6. Concurrency Control & Atomic Guards

In a multi-threaded web server environment, a critical race condition could occur if a support agent attempts to claim a ticket at the exact same millisecond that the SLA background scheduler attempts to escalate it.

### The Race Condition Risk
Without concurrency guards, both operations might read `status == 'open'` simultaneously, leading to a state corruption where a ticket is marked as both `claimed` and `escalated`, or triggering duplicate manager notifications.

### The Atomic Check-and-Set Guard
To guarantee that a ticket resolves into exactly **one** terminal state, both claim and escalation operations execute using atomic, conditional SQL updates:

```sql
-- Executed during Agent Claim (ticket_service.py)
UPDATE tickets
   SET status = 'claimed',
       claimed_by = :agent,
       claimed_at = :timestamp
 WHERE id = :ticket_id
   AND status = 'open';
```

```sql
-- Executed during Automated Escalation (ticket_service.py)
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
Whenever the server initializes (via `py src/server.py`), the application executes the following deterministic startup sequence:

```
[1. Server Startup Initiated]
              │
              ▼
[2. init_ticket_table()] ─────────▶ Executes CREATE TABLE IF NOT EXISTS on tickets.db
              │
              ▼
[3. Instantiate SlaScheduler] ────▶ Spawns background daemon thread
              │
              ▼
[4. Scheduler Thread Start] ──────▶ OVERRIDES default sleep loop to execute check_and_escalate() IMMEDIATELY
              │
              ▼
[5. Database Recovery Query] ─────▶ SELECT * FROM tickets WHERE status='open' AND sla_deadline <= NOW()
              │
              ▼
[6. Process Overdue Tickets] ─────▶ Loops through returned rows and executes atomic escalate_ticket()
              │
              ▼
[7. Audit Notification Log] ──────▶ Writes breach notices to notify.log for each recovered ticket
              │
              ▼
[8. Enter Polling Loop] ──────────▶ Transitions into regular 5-second background sleep cycle
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
| **`tests/test_api.py`** | REST API Layer | Validates HTTP endpoints (`GET`, `POST`), status codes (`201`, `200`, `404`), CORS headers, and JSON error structures. |
| **`tests/test_client.py`** | SDK Integration | Verifies programmatic Python HTTP client wrapper methods (`create_ticket`, `claim_ticket`, `get_ticket`). |
| **`tests/test_sla_scheduler.py`** | Core Engine | Tests SLA deadline calculation, overdue ticket detection, scheduler execution loops, and atomic state transition checks. |

---

## 10. Architectural Decision Record (ADR) Summary

| Decision Identifier | Architectural Subject | Chosen Decision | Rational & Justification |
| :--- | :--- | :--- | :--- |
| **ADR-001** | Persistence Layer | SQLite with WAL Mode | Eliminates external database infrastructure management while supporting concurrent reads and reliable disk persistence for demos. |
| **ADR-002** | SLA Storage Strategy | Pre-calculated Expiration | Storing `sla_deadline` directly in ticket rows allows simple, high-performance SQL indexing and stateless background querying. |
| **ADR-003** | Concurrency Protection | SQL Conditional Check-and-Set | Using `WHERE status = 'open'` within SQL statements guarantees race-condition protection without requiring complex distributed locks. |
| **ADR-004** | Startup Recovery | Immediate Daemon Sweep | Running an immediate check on scheduler initialization ensures zero recovery latency for tickets that expired during server downtime. |
| **ADR-005** | Frontend Delivery | Vanilla JS/CSS (No Build Step) | Serving static files directly via HTTP server eliminates Node.js build dependencies while delivering high-performance UI components. |
