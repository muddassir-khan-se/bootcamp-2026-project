# Failure Demo — Durable SLA Escalation Engine

> **Goal:** Prove that SLA escalation timers survive a server crash and are recovered automatically on restart.

---

## Prerequisites

- Python 3.10+ installed
- Dependencies installed: `py -m pip install -r requirements.txt`
- Server is **not** currently running

---

## Demo Steps

### Step 1 — Start the server

```powershell
py src/server.py
```

Expected output:
```
Server running at http://127.0.0.1:8000
```

---

### Step 2 — Create a ticket

Open a **second** terminal and run:

```powershell
$body = '{"subject": "Database connection timeout — DEMO"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/tickets `
  -Method POST -Body $body -ContentType "application/json"
```

Expected response (note the `sla_deadline` — 60 s after creation):

```json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "open",
  "sla_deadline": "2026-06-29T07:01:00",
  "created_at": "2026-06-29T07:00:00"
}
```

> The deadline is written to `tickets.db` immediately — no in-memory state is relied upon.

---

### Step 3 — Kill the server before the SLA expires

In the first terminal, press **Ctrl+C**.

> **In a naive system:** per-ticket threads are lost → ticket sits `open` forever.  
> **In this system:** the deadline is already in SQLite → nothing is lost.

---

### Step 4 — Wait for the SLA to expire

Wait **at least 60 seconds** without restarting the server. The deadline passes during this simulated downtime.

---

### Step 5 — Restart the server

```powershell
py src/server.py
```

On startup, `SlaScheduler` immediately runs this query before its first sleep:

```sql
SELECT * FROM tickets WHERE status = 'open' AND sla_deadline <= datetime('now')
```

The overdue ticket is found and escalated **within the first second** of startup.

---

### Step 6 — Verify escalation

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/tickets -Method GET
```

Expected:

```json
{
  "status": "escalated",
  "escalated_at": "2026-06-29T07:01:05"
}
```

Check `notify.log` in the project root:

```
[notify_manager] Ticket xxxxxxxx-... breached SLA at 2026-06-29T07:01:05
```

Open `http://127.0.0.1:8000` — the dashboard shows a red **Escalated** badge and the breach timestamp.

---

## What the Demo Proves

| Property | Result |
| :--- | :---: |
| SLA deadline stored durably | ✅ |
| Escalation survives process restart | ✅ |
| No double-escalation on concurrent claim | ✅ |
| Manager notified via `notify.log` | ✅ |
| Dashboard reflects final state | ✅ |

---

## Additional Scenarios

**Concurrent claim vs. escalation**

If an agent claims the ticket at the exact moment the scheduler fires, only one outcome is recorded. The losing operation finds `rowcount == 0` (ticket is no longer `open`) and exits silently.

**Multiple overdue tickets**

If 10 tickets all exceeded their SLA during downtime, the scheduler escalates all 10 in its first pass — one atomic SQL transaction per ticket.

---

## Reading `notify.log`

```
[notify_manager] Ticket abc12345-... breached SLA at 2026-06-29T07:01:05
[notify_manager] Ticket def67890-... breached SLA at 2026-06-29T08:05:33
```

Each line is written by `notify_manager()` in `ticket_service.py`. In production this would call an email API, PagerDuty, or a Slack webhook.
