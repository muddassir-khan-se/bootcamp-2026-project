# Carfullfy — Durable SLA Ticketing Engine

> **Bootcamp 2026 Project** · Author: Muddassir Khan

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-pytest-brightgreen?style=flat-square)](#running-tests)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-orange?style=flat-square)](#)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Key Features](#key-features)
3. [Repository Structure](#repository-structure)
4. [Prerequisites & Installation](#prerequisites--installation)
5. [Running the Service](#running-the-service)
6. [Running Tests](#running-tests)
7. [REST API Reference](#rest-api-reference)
8. [Frontend Dashboard](#frontend-dashboard)
9. [Core Components Breakdown](#core-components-breakdown)
10. [SLA Escalation Policy](#sla-escalation-policy)
11. [Development Workflow](#development-workflow)
12. [Documentation Index](#documentation-index)

---

## Project Overview

**Carfullfy** is a robust Python-based Customer Support SLA Ticketing Engine paired with an interactive real-time web dashboard.

The primary objective of the engine is to manage customer support tickets and enforce strict Service Level Agreements (SLAs). The system guarantees that every newly created ticket is either claimed by a support agent within a **60-second window** or automatically escalated to management.

### The Durability Guarantee

In typical lightweight implementations, SLA countdown timers are tracked in temporary process memory (such as background thread timers). If the application server restarts, crashes, or loses power, those in-memory timers vanish, leaving pending tickets permanently stranded in an un-escalated state.

**Carfullfy solves this problem through persistent durability:**
- **Persistent Storage:** All SLA deadlines (`sla_deadline`) are calculated and committed directly to SQLite (`tickets.db`) at the exact moment a ticket is created.
- **Automated Recovery:** A background daemon scheduler continuously monitors active tickets and performs an immediate recovery scan on server startup. Any ticket whose SLA expired during server downtime is detected and escalated on the very first execution pass.
- **Atomic Operations:** Database check-and-set transactions eliminate race conditions between simultaneous agent claims and background escalations.

---

## Key Features

| Feature | Description |
| :--- | :--- |
| 🎟 **Complete Ticket Lifecycle** | Full support for ticket creation, agent claiming, status tracking, and automated manager escalation via REST API. |
| ⏱ **Durable SLA Enforcement** | SLA expiration timestamps are stored persistently in SQLite, guaranteeing crash survival across process restarts. |
| 🔁 **Automatic Background Escalation** | A dedicated background daemon thread polls the database every 5 seconds to process overdue tickets. |
| 🔒 **Atomic Concurrency Control** | SQL conditional updates (`UPDATE ... WHERE status = 'open'`) ensure a ticket is never simultaneously claimed and escalated. |
| 🖥 **Interactive Live Dashboard** | Real-time browser single-page application featuring visual SLA countdown bars, dynamic status counters, and dark mode. |
| 🔔 **In-Browser Toast Notifications** | Clean, accessible pop-up alerts providing instant feedback on user actions and system events. |
| 📋 **Live Audit Activity Feed** | A real-time chronological event log displaying ticket creations, claims, and escalation events in the UI sidebar. |
| 🎯 **Multi-Level Priority Support** | Support for assigning Low, Medium, High, and Critical priorities during ticket submission. |
| 🌙 **Persistent Theme Preference** | Integrated Dark/Light mode switcher with settings preserved in browser `localStorage`. |
| ✅ **Automated Test Suite** | Comprehensive unit and integration coverage validating API behavior, DB models, and scheduler logic. |

---

## Repository Structure

```
bootcamp-2026-project/
│
├── src/                            # Application Source Code
│   ├── __init__.py                 # Python package initialization
│   ├── db.py                       # Central SQLite connection layer (WAL mode & thread safety)
│   ├── models.py                   # Data models (Ticket dataclass & JSON serializers)
│   ├── ticket_service.py           # Core business logic (creation, claiming, escalation)
│   ├── sla_scheduler.py            # Background daemon thread & crash recovery manager
│   ├── server.py                   # HTTP web server (REST API endpoints & static asset router)
│   ├── client.py                   # Programmatic Python HTTP client SDK
│   └── static/                     # Frontend Web Dashboard Assets
│       ├── index.html              # Dashboard HTML shell with SEO meta tags & layout panels
│       ├── style.css               # CSS design system (light/dark tokens, responsive grid)
│       └── app.js                  # Client-side JavaScript (polling, SLA timers, toast UI)
│
├── tests/                          # Automated Testing Suite
│   ├── test_api.py                 # REST API endpoint verification
│   ├── test_client.py              # Python HTTP client integration tests
│   └── test_sla_scheduler.py       # Background scheduler & escalation logic tests
│
├── docs/                           # Comprehensive System Documentation
│   ├── architecture.md             # In-depth system architecture, data models & flow diagrams
│   ├── ai-review-summary.md        # Technical review findings, severities & implemented resolutions
│   └── failure-demo.md             # Step-by-step verification guide for crash recovery
│
├── .github/workflows/
│   └── ci.yml                      # GitHub Actions automated test workflow
│
├── README.md                       # Master project document
├── requirements.txt                # Python dependencies
├── tickets.db                      # Primary SQLite database file (created automatically)
└── notify.log                      # Audit log for manager escalation notifications
```

---

## Prerequisites & Installation

### Requirements
- **Python 3.10** or higher
- `pip` package manager

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/muddassir-khan-se/bootcamp-2026-project.git
   cd bootcamp-2026-project
   ```

2. **Install dependencies:**
   ```bash
   py -m pip install -r requirements.txt
   ```

---

## Running the Service

Start the ticket engine server, background scheduler, and web dashboard with a single command:

```bash
py src/server.py
```

By default, the HTTP server listens on **`http://127.0.0.1:8000`**.

### Custom Database Configuration
You can customize the SQLite database storage path using the `TICKETS_DB_PATH` environment variable:

```powershell
# Windows PowerShell
$env:TICKETS_DB_PATH = "C:\custom\path\tickets.db"
py src/server.py
```

---

## Running Tests

Execute the automated test suite using `pytest`:

```bash
py -m pytest -q
```

The test suite validates:
- Ticket instance initialization and default property settings.
- Lifecycle state transitions (`open → claimed` and `open → escalated`).
- Calculation of SLA deadlines (exactly 60 seconds from creation timestamp).
- Scheduler execution cycles and automated recovery of overdue tickets.
- Concurrency protection ensuring isolated outcomes during simultaneous claim and escalation attempts.

---

## REST API Reference

All API request bodies and responses communicate using standard JSON. Timestamps are formatted as ISO 8601 UTC strings.

### 1. Create a Ticket
Creates a new support ticket in the `open` state and starts the 60-second SLA countdown.

- **HTTP Method:** `POST`
- **Endpoint:** `/tickets`
- **Headers:** `Content-Type: application/json`

**Request Body:**
```json
{
  "subject": "Database connection pool exhausted",
  "priority": "high"
}
```

**Response (`201 Created`):**
```json
{
  "id": "e4b3c1a2-9f8e-4b7c-8a1d-2e3f4a5b6c7d",
  "subject": "Database connection pool exhausted",
  "created_at": "2026-06-29T12:00:00.000000",
  "status": "open",
  "claimed_by": null,
  "claimed_at": null,
  "escalated_at": null,
  "sla_deadline": "2026-06-29T12:01:00.000000"
}
```

---

### 2. List All Tickets
Retrieves a complete history of support tickets stored in the database.

- **HTTP Method:** `GET`
- **Endpoint:** `/tickets`

**Response (`200 OK`):**
```json
[
  {
    "id": "e4b3c1a2-9f8e-4b7c-8a1d-2e3f4a5b6c7d",
    "subject": "Database connection pool exhausted",
    "created_at": "2026-06-29T12:00:00.000000",
    "status": "open",
    "claimed_by": null,
    "claimed_at": null,
    "escalated_at": null,
    "sla_deadline": "2026-06-29T12:01:00.000000"
  }
]
```

---

### 3. Inspect Specific Ticket
Retrieves detailed attributes for a specific ticket identifier.

- **HTTP Method:** `GET`
- **Endpoint:** `/tickets/{ticket_id}`

**Response (`200 OK`):** Returns single ticket JSON object.  
**Response (`404 Not Found`):** `{"error": "ticket_not_found"}`

---

### 4. Claim a Ticket
Assigns an open ticket to a support agent and stops the SLA escalation timer.

- **HTTP Method:** `POST`
- **Endpoint:** `/tickets/{ticket_id}/claim`
- **Headers:** `Content-Type: application/json`

**Request Body:**
```json
{
  "agent": "Agent Sarah"
}
```

**Response (`200 OK`):**
```json
{
  "id": "e4b3c1a2-9f8e-4b7c-8a1d-2e3f4a5b6c7d",
  "subject": "Database connection pool exhausted",
  "created_at": "2026-06-29T12:00:00.000000",
  "status": "claimed",
  "claimed_by": "Agent Sarah",
  "claimed_at": "2026-06-29T12:00:25.123456",
  "escalated_at": null,
  "sla_deadline": "2026-06-29T12:01:00.000000"
}
```

---

## Frontend Dashboard

Access the live single-page dashboard at **`http://127.0.0.1:8000`** while the server is running.

### Dashboard Capabilities Guide

| Panel / Feature | User Action | Functionality & Visual Behavior |
| :--- | :--- | :--- |
| **New Ticket Form** | Input subject & select priority | Submits ticket, initializes 60s countdown, triggers success toast. |
| **Live Ticket Monitor** | Real-time list view | Displays active tickets with dynamic urgency color bars (Green → Orange → Red). |
| **Status Filter Tabs** | Click All / Open / Claimed / Escalated | Filters ticket monitor view dynamically without page reloads. |
| **Subject Search Bar** | Type keywords or UUID snippets | Performs instant client-side text filtering across active tickets. |
| **Claim Action Modal** | Click "Claim Ticket" on any open card | Prompts for Agent ID, updates status, and logs event to Activity Feed. |
| **Card Detail Expansion** | Click anywhere on a ticket card | Expands card to reveal full UUID, timestamps, and assigned agent data. |
| **Activity Feed** | View left-sidebar feed | Shows chronological audit history of creations, claims, and SLA breaches. |
| **Dark Theme Toggle** | Click 🌙 / ☀️ icon in header | Toggles visual design system between high-contrast light and dark modes. |
| **Keyboard Shortcut** | Press key `N` | Instantly shifts cursor focus to the ticket creation subject field. |

---

## Core Components Breakdown

### 1. Database Management (`src/db.py`)
Centralized connection manager utilizing Python's `contextmanager`. Configures SQLite with **Write-Ahead Logging (WAL)** mode and foreign key support. Implements a global thread lock (`DB_LOCK`) to serialize concurrent thread queries safely.

### 2. Data Models (`src/models.py`)
Defines the `Ticket` dataclass containing typed attributes for ticket identifiers, subjects, status states, agent assignments, and ISO timestamp helper methods (`to_dict()`).

### 3. Service Layer (`src/ticket_service.py`)
Encapsulates all core domain logic. Contains SQL query executions for creating tickets, querying due tickets, updating statuses atomically (`WHERE status = 'open'`), and writing escalation audit notices to `notify.log`.

### 4. SLA Background Scheduler (`src/sla_scheduler.py`)
Extends `threading.Thread` as a daemon process. Executes periodic checks every 5 seconds to escalate overdue tickets. Crucially, it triggers an immediate recovery check upon initialization to process tickets that expired during server downtime.

### 5. HTTP Web Server (`src/server.py`)
Built on Python's native `http.server.HTTPServer` and `BaseHTTPRequestHandler`. Translates incoming HTTP requests into service function calls and serves frontend static assets (`index.html`, `style.css`, `app.js`) with proper MIME types and CORS headers.

---

## SLA Escalation Policy

| Parameter | Operational Specification |
| :--- | :--- |
| **SLA Duration** | **60 seconds** allowed from creation timestamp to agent claim. |
| **Polling Frequency** | Scheduler checks for overdue tickets every **5 seconds**. |
| **Escalation Trigger** | Any ticket with `status = 'open'` where `sla_deadline <= current_timestamp`. |
| **Atomic Protection** | SQL conditional update ensures simultaneous claims and escalations resolve cleanly. |
| **Audit Log Target** | Escalations write an entry formatted as `[notify_manager] Ticket {id} breached SLA at {timestamp}` into `notify.log`. |

---

## Development Workflow

Follow this standardized procedure for introducing code enhancements or fixes:

```bash
# 1. Create a dedicated feature branch
git checkout -b feature/your-feature-name

# 2. Implement changes across src/ and update matching unit tests in tests/

# 3. Verify changes using pytest
py -m pytest -q

# 4. Launch local server to test UI and API integration
py src/server.py

# 5. Stage, commit, and push changes
git add .
git commit -m "feat: detailed description of changes"
git push origin feature/your-feature-name

# 6. Submit a Pull Request targeting main branch on GitHub
```

---

## Documentation Index

For comprehensive technical specifications and step-by-step guides, refer to the dedicated documentation files in the `docs/` directory:

- 📐 **[`docs/architecture.md`](docs/architecture.md):** Full architectural design specifications, state machine transitions, component responsibilities, and concurrency safeguards.
- 🧪 **[`docs/failure-demo.md`](docs/failure-demo.md):** Step-by-step walkthrough demonstrating server termination, downtime simulation, and automatic startup SLA recovery.
- 📑 **[`docs/ai-review-summary.md`](docs/ai-review-summary.md):** Comprehensive audit report detailing identified architectural findings, severity levels, and technical resolution strategies.

---

> **Project Status:** Active Development &nbsp;|&nbsp; **Author:** Muddassir Khan &nbsp;|&nbsp; **Bootcamp:** 2026
