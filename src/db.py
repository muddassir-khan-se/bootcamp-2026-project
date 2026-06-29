"""
Carfullfy SLA Escalation Engine - Database Connection Layer.
Provides SQLite connection management with WAL mode, threading locks, and environment path overrides.
Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "tickets.db"
DB_LOCK = threading.Lock()

def get_db_path() -> Path:
    return Path(os.environ.get("TICKETS_DB_PATH", str(DEFAULT_DB_PATH)))

@contextmanager
def db_connection() -> Generator[sqlite3.Connection, None, None]:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with DB_LOCK:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()
