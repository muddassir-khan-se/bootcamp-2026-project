# Durable SLA Ticketing Service

**Bootcamp 2026 Project** by Muddassir Khan

## Project Overview

This repository implements a Python-based Customer Support SLA ticketing service. It provides ticket creation, claiming, inspection, and automatic escalation for tickets whose SLA deadline is missed.

The design focuses on durability: SLA escalation decisions are persisted through SQLite so the system can recover from process restarts without losing escalation state.

## Key Features

- **Ticket lifecycle management**: Create, claim, inspect, and escalate tickets
- **Durable SLA enforcement**: SLA deadlines are stored in SQLite and re-evaluated after restart
- **Automatic escalation**: Tickets that exceed SLA deadline are escalated automatically
- **Simple HTTP server**: REST-style API endpoints for ticket operations
- **Test coverage**: `pytest` verifies core behavior and scheduler logic

## Current Repository Structure

```
.
├── src/
│   ├── __init__.py
│   ├── db.py
│   ├── models.py
│   ├── ticket_service.py
│   ├── sla_scheduler.py
│   └── server.py
├── tests/
│   ├── test_api.py
│   └── test_sla_scheduler.py
├── docs/
│   ├── architecture.md
│   ├── ai-review-summary.md
│   └── failure-demo.md
├── .github/workflows/
│   └── ci.yml
├── README.md
├── requirements.txt
├── tickets.db
└── notify.log
```

## Prerequisites

- Python 3.10+
- `pip`

## Installation

```bash
cd bootcamp-2026-project
py -m pip install -r requirements.txt
```

## Running Tests

```bash
py -m pytest -q
```

## Running the Service

Start the ticket service:

```bash
py src/server.py
```

By default, the service listens on `127.0.0.1:8000` and uses `./tickets.db` as the SQLite database.

### Override default database path

```powershell
$env:TICKETS_DB_PATH = "C:\path\to\tickets.db"
py src/server.py
```

## API Endpoints

### Create ticket

```http
POST /tickets
Content-Type: application/json

{ "subject": "Example issue" }
```

### Claim ticket

```http
POST /tickets/{ticket_id}/claim
Content-Type: application/json

{ "agent": "agent-1" }
```

### Get ticket details

```http
GET /tickets/{ticket_id}
```

## Core Components

### `src/db.py`
- Central SQLite connection manager
- Supports `TICKETS_DB_PATH` environment override
- Enables WAL mode for durability

### `src/models.py`
- Ticket dataclass representation
- Serialization helpers for JSON responses

### `src/ticket_service.py`
- Ticket creation and claim logic
- SLA deadline storage and lookup
- Escalation logic for overdue tickets

### `src/sla_scheduler.py`
- Periodic background scheduler
- Runs escalation checks every interval
- Keeps escalation behavior durable and repeatable

### `src/server.py`
- Simple HTTP server for ticket API
- Supports create, claim, and get operations
- Bootstraps ticket table on startup

## Testing Strategy

The `tests/` directory validates:
- Ticket creation and retrieval
- Claiming tickets and status transitions
- SLA escalation logic for overdue tickets
- Scheduler execution and automatic escalation

## Dependency File

`requirements.txt` contains Python test dependencies and runtime support for the project.

## Development Workflow

1. Create a feature branch:
   ```bash
git checkout -b feature/your-description
```
2. Add or update code in `src/`
3. Add tests in `tests/`
4. Run:
   ```bash
py -m pytest -q
```
5. Commit and push your changes
6. Open a pull request

## Notes

- The service is intentionally lightweight and single-process.
- SQLite is used for persistence and recovery.
- `notify.log` records escalation notification events.

---

**Project Status**: Active Development  
**Author**: Muddassir Khan
