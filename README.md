# Carfullfy — Durable SLA Ticketing Engine

> **Bootcamp 2026 Project** · Author: Muddassir Khan

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-pytest-brightgreen?style=flat-square)](#quick-start)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## Overview

**Carfullfy** is a durable Python Customer Support SLA Ticketing Engine with a real-time web dashboard. SLA timers are persisted in SQLite, ensuring automatic escalation recovery across crashes and process restarts.

---

## Quick Start

```bash
# Install
git clone https://github.com/muddassir-khan-se/bootcamp-2026-project.git
cd bootcamp-2026-project
py -m pip install -r requirements.txt

# Run Tests
py -m pytest -q

# Start Service (Server + SLA Scheduler + Web Dashboard)
py src/server.py
```
> Access live dashboard at `http://127.0.0.1:8000`. Override DB path via `$env:TICKETS_DB_PATH`.

---

## Key Features

| Feature | Description |
| :--- | :--- |
| 🎟 **Ticket Lifecycle** | REST API for creation, claiming, inspection, and auto-escalation |
| ⏱ **Durable Enforcement** | SQLite deadline storage surviving process restarts |
| 🔁 **Auto-Escalation** | Background scheduler scanning every 5s for overdue tickets |
| 🔒 **Atomic State Check** | `UPDATE WHERE status = 'open'` prevents double-escalation |
| 🖥 **Live Dashboard** | Real-time UI with filters, search, countdowns, and dark mode |
| 📋 **Audit Activity Feed** | In-browser live event trail (creation, claims, escalations) |
| 🎯 **Priority Levels** | Low / Medium / High / Critical priority options |

---

## REST API Reference

All endpoints accept/return JSON with ISO 8601 UTC timestamps.

| Method | Endpoint | Description | Sample Payload / Response |
| :---: | :--- | :--- | :--- |
| `POST` | `/tickets` | Create a new ticket | Req: `{"subject": "DB crash"}`<br>Res `201`: `{"id": "...", "status": "open", "sla_deadline": "..."}` |
| `GET` | `/tickets` | List all tickets | Res `200`: `[{"id": "...", "status": "open"}, ...]` |
| `GET` | `/tickets/{id}` | Get ticket by UUID | Res `200`: `{"id": "...", ...}` \| `404`: `{"error": "ticket_not_found"}` |
| `POST` | `/tickets/{id}/claim` | Claim open ticket | Req: `{"agent": "Agent A"}`<br>Res `200`: `{"status": "claimed", "claimed_by": "Agent A"}` |

---

## Project Architecture & Structure

```
bootcamp-2026-project/
├── src/
│   ├── db.py               # SQLite connection context manager (WAL mode, Thread Lock)
│   ├── models.py           # Ticket dataclass & serialization helpers
│   ├── ticket_service.py   # Business logic (create, claim, escalate)
│   ├── sla_scheduler.py    # Daemon thread (5s polling & startup crash recovery pass)
│   ├── server.py           # BaseHTTPRequestHandler API & static file router
│   └── static/             # Vanilla JS, CSS design system, HTML dashboard shell
├── tests/                  # Pytest unit & integration suite
└── docs/                   # System design, AI audit summary, failure demo guide
```

---

## Core SLA Parameters

| Parameter | Value | Details |
| :--- | :--- | :--- |
| **SLA Limit** | 60 Seconds | Deadline set on creation (`created_at + 60s`) |
| **Poll Interval** | 5 Seconds | Background scheduler scan frequency |
| **Notifications** | `notify.log` | Escalation log append target |

---

## Project Documentation

| Document | Purpose |
| :--- | :--- |
| 📐 [`docs/architecture.md`](docs/architecture.md) | System design, state machine, sequence diagrams, and concurrency guarantees |
| 🧪 [`docs/failure-demo.md`](docs/failure-demo.md) | Step-by-step verification of crash recovery and durability |
| 📑 [`docs/ai-review-summary.md`](docs/ai-review-summary.md) | Architectural review findings, severity ratings, and resolutions |
