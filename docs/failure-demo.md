# Failure & Recovery Demonstration Guide — Carfullfy SLA Engine

> **Document Type:** Technical Verification & Demonstration Guide  
> **Objective:** Step-by-step verification demonstrating that SLA escalation timers survive application crashes and recover automatically upon server restart.  
> **Author:** Muddassir Khan | Bootcamp 2026

---

## Table of Contents

1. [Demonstration Purpose](#1-demonstration-purpose)
2. [Prerequisites & Environment Setup](#2-prerequisites--environment-setup)
3. [Step-by-Step Demonstration Walkthrough](#3-step-by-step-demonstration-walkthrough)
   - [Step 1: Launch Application Server](#step-1-launch-application-server)
   - [Step 2: Submit a New Support Ticket](#step-2-submit-a-new-support-ticket)
   - [Step 3: Verify Open Ticket State](#step-3-verify-open-ticket-state)
   - [Step 4: Simulate Application Crash / Shutdown](#step-4-simulate-application-crash--shutdown)
   - [Step 5: Simulate Server Downtime](#step-5-simulate-server-downtime)
   - [Step 6: Restart Application Server](#step-6-restart-application-server)
   - [Step 7: Verify Automatic Escalation Recovery](#step-7-verify-automatic-escalation-recovery)
   - [Step 8: Verify Dashboard & Audit Logs](#step-8-verify-dashboard--audit-logs)
4. [Verification Summary Matrix](#4-verification-summary-matrix)
5. [Advanced Contention & Failure Scenarios](#5-advanced-contention--failure-scenarios)

---

## 1. Demonstration Purpose

The primary architectural guarantee of the **Carfullfy SLA Escalation Engine** is **100% durability**. In standard in-memory timer systems, restarting an application server destroys all active countdown timers, causing overdue tickets to sit in an un-escalated state indefinitely.

This guide provides an exact, reproducible walkthrough demonstrating how Carfullfy eliminates this vulnerability. By storing SLA deadlines persistently in SQLite and running an immediate recovery scan upon startup, the engine automatically detects and escalates tickets that breached their SLA during server downtime.

---

## 2. Prerequisites & Environment Setup

Before initiating the demonstration, ensure your local environment meets the following conditions:

- **Python Environment:** Python **3.10** or higher installed.
- **Dependencies Installed:** Execute `py -m pip install -r requirements.txt` in the project root.
- **Clean State:** Ensure no instances of `server.py` are currently running in the background.

---

## 3. Step-by-Step Demonstration Walkthrough

### Step 1: Launch Application Server

Open your primary terminal (Terminal 1) in the project root directory and start the ticketing service:

```powershell
py src/server.py
```

**Expected Output in Terminal 1:**
```text
Server running at http://127.0.0.1:8000
```
*Under the hood:* The HTTP server starts listening for REST requests, initializes the SQLite database schema in `tickets.db`, and launches the background daemon scheduler (`SlaScheduler`).

---

### Step 2: Submit a New Support Ticket

Open a secondary terminal window (Terminal 2) to act as the client. Execute a REST API call to create a new ticket:

```powershell
$body = '{"subject": "Production database connection timeout -- DEMO"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/tickets -Method POST -Body $body -ContentType "application/json"
```

**Expected Response Output (Terminal 2):**
```json
{
  "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "subject": "Production database connection timeout -- DEMO",
  "created_at": "2026-06-29T12:00:00.000000",
  "status": "open",
  "claimed_by": null,
  "claimed_at": null,
  "escalated_at": null,
  "sla_deadline": "2026-06-29T12:01:00.000000"
}
```

**Key Observation:** Examine the `sla_deadline` field. It is pre-calculated to exactly **60 seconds** after `created_at`. This timestamp is committed directly to the SQLite database disk file (`tickets.db`).

---

### Step 3: Verify Open Ticket State

Confirm that the newly created ticket is active and marked as `open` by querying the ticket listing endpoint:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/tickets -Method GET
```

**Expected Output:** The JSON response array contains your ticket with `"status": "open"`.

---

### Step 4: Simulate Application Crash / Shutdown

Return to **Terminal 1** (where the server is running). Press **`Ctrl + C`** to terminate the server process abruptly.

**Terminal 1 Output:**
```text
^C
Server stopped.
```

**Architectural Analysis:**
- In an **ephemeral in-memory system**, killing the process destroys the background timer thread watching this ticket. Upon restart, the ticket would remain `open` forever.
- In **Carfullfy's durable architecture**, no memory timers were created. The ticket record and its expiration target (`2026-06-29T12:01:00.000000`) remain safely persisted on disk in `tickets.db`.

---

### Step 5: Simulate Server Downtime

Do **not** restart the server immediately. Allow at least **60 seconds** to elapse from the ticket creation time recorded in Step 2. 

*During this period, the SLA deadline (`12:01:00`) passes while the application server is completely offline.*

---

### Step 6: Restart Application Server

In **Terminal 1**, restart the ticketing engine service:

```powershell
py src/server.py
```

**Expected Output in Terminal 1:**
```text
Server running at http://127.0.0.1:8000
```

**Under the Hood Recovery Sequence:**
1. Upon invocation, `server.py` initializes `SlaScheduler`.
2. As soon as `SlaScheduler.start()` is called, its internal daemon thread executes an **immediate recovery scan** prior to entering its standard 5-second sleep cycle.
3. The scheduler executes SQL: `SELECT * FROM tickets WHERE status = 'open' AND sla_deadline <= NOW()`.
4. It detects your overdue ticket, triggers an atomic status update (`open → escalated`), sets `escalated_at`, and writes an alert entry to `notify.log`.

---

### Step 7: Verify Automatic Escalation Recovery

Switch back to **Terminal 2** and query the ticket list to verify that recovery succeeded:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/tickets -Method GET
```

**Expected Output (Terminal 2):**
```json
[
  {
    "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "subject": "Production database connection timeout -- DEMO",
    "created_at": "2026-06-29T12:00:00.000000",
    "status": "escalated",
    "claimed_by": null,
    "claimed_at": null,
    "escalated_at": "2026-06-29T12:01:05.123456",
    "sla_deadline": "2026-06-29T12:01:00.000000"
  }
]
```

**Verification Success:** Notice that `status` has automatically transitioned to **`escalated`** and `escalated_at` reflects the exact recovery timestamp.

---

### Step 8: Verify Dashboard & Audit Logs

1. **Check Audit Log (`notify.log`):** Open `notify.log` in your editor or run `Get-Content notify.log` in PowerShell. You will observe the recorded manager notification:
   ```text
   [notify_manager] Ticket a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d breached SLA at 2026-06-29T12:01:05.123456
   ```

2. **Inspect Web Dashboard:** Open **`http://127.0.0.1:8000`** in your web browser.
   - The **Escalated Tickets** counter card reflects `1`.
   - The ticket card displays a red **Escalated** status badge.
   - Expanding the ticket card confirms the exact escalation timestamp.

---

## 4. Verification Summary Matrix

| Proven Architectural Property | Demonstration Evidence | Technical Validation |
| :--- | :--- | :--- |
| **Durable SLA Storage** | `sla_deadline` present in POST response and stored in `tickets.db`. | Confirms deadlines are persisted on disk rather than held in volatile memory. |
| **Zero Downtime Data Loss** | Server process terminated via `Ctrl+C` for over 60 seconds. | Proves state is completely decoupled from application process lifetime. |
| **Automatic Startup Recovery** | Ticket escalated within 1 second of server restart in Step 6. | Validates that `SlaScheduler` immediate startup sweep catches overdue tickets instantly. |
| **Audit Log Integrity** | Entry written to `notify.log` upon recovery pass completion. | Confirms external notification handlers fire reliably during crash recovery. |
| **UI Telemetry Synchronization** | Dashboard reflects escalated state and updated counter metrics. | Proves frontend state synchronizes seamlessly with backend recovery state. |

---

## 5. Advanced Contention & Failure Scenarios

### Scenario A: Simultaneous Claim & Escalation Race
*Condition:* An agent submits `POST /tickets/{id}/claim` at the exact same millisecond that the background scheduler detects `sla_deadline <= NOW()`.

*Behavior:* Both execution paths issue atomic SQL updates containing `WHERE status = 'open'`. SQLite's write lock forces sequential processing. Whichever transaction executes first updates the row. The second transaction finds `status != 'open'` (`rowcount == 0`) and exits safely as a silent no-op. Double-escalation is physically impossible.

### Scenario B: Mass Expiration Recovery During Extended Downtime
*Condition:* The server experiences extended downtime (e.g., 2 hours), during which 50 open tickets exceed their SLA deadlines.

*Behavior:* Upon server restart, the scheduler's initial recovery query (`SELECT WHERE status='open' AND sla_deadline <= NOW()`) returns all 50 overdue records. The loop iterates through the collection, escalating each ticket atomically and generating 50 audit log entries in `notify.log` before entering its regular polling cycle.
