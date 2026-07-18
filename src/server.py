"""
Carfullfy SLA Escalation Engine - HTTP Server & Static Asset Router.
Provides REST API endpoints for ticket lifecycle management and serves the frontend dashboard.

Workflow logic is now driven by Temporal:
  POST /tickets          → generates UUID, starts SlaWorkflow, returns ticket from DB
  POST /tickets/*/claim  → sends claim_signal to the running workflow

Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional

from temporalio.client import Client, WorkflowHandle
from temporalio.service import RPCError

try:
    from .temporal_workflow import SlaWorkflow, TASK_QUEUE, TicketWorkflowInput
    from .ticket_service import (
        create_ticket,
        claim_ticket,
        get_all_tickets,
        get_ticket,
        init_ticket_table,
        TicketConflictError,
    )
except ImportError:
    from temporal_workflow import SlaWorkflow, TASK_QUEUE, TicketWorkflowInput
    from ticket_service import (
        create_ticket,
        claim_ticket,
        get_all_tickets,
        get_ticket,
        init_ticket_table,
        TicketConflictError,
    )

HOST = "127.0.0.1"
PORT = 8000
TEMPORAL_HOST = "localhost:7233"

# ---------------------------------------------------------------------------
# Async event loop running in a background daemon thread.
# Bridges the synchronous HTTP handler to the async Temporal SDK.
# ---------------------------------------------------------------------------

_loop: Optional[asyncio.AbstractEventLoop] = None
_temporal_client: Optional[Client] = None
_temporal_available: bool = False  # set to True when Temporal connects successfully


def _start_event_loop() -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


def _run_async(coro) -> Any:
    """Submit a coroutine to the background event loop and block until done."""
    assert _loop is not None, "Event loop not started"
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=30)


async def _connect_client() -> Client:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await Client.connect(TEMPORAL_HOST)
    return _temporal_client


def get_temporal_client() -> Client:
    return _run_async(_connect_client())


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

def parse_json(body: bytes) -> dict[str, Any]:
    return json.loads(body.decode("utf-8")) if body else {}


class TicketRequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json_response(self, payload: Any, code: int = 200) -> None:
        self._set_headers(code)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_OPTIONS(self) -> None:
        self._set_headers(200)

    def _read_body(self) -> bytes | None:
        """Read the request body using Content-Length. Returns None on malformed header."""
        raw = self.headers.get("Content-Length", "0")
        try:
            length = int(raw)
        except ValueError:
            self._json_response({"error": "invalid_content_length"}, 400)
            return None
        return self.rfile.read(length)

    def do_POST(self) -> None:
        # ── POST /tickets ──────────────────────────────────────────────────
        if self.path == "/tickets":
            body = self._read_body()
            if body is None:
                return
            data = parse_json(body)
            subject = data.get("subject")
            if not subject:
                return self._json_response({"error": "subject_required"}, 400)

            # Generate ticket UUID here so the workflow ID = ticket UUID.
            # This lets us signal the workflow later using the same ID.
            ticket_id = str(uuid.uuid4())

            if _temporal_available:
                try:
                    client = get_temporal_client()
                    _run_async(
                        client.start_workflow(
                            SlaWorkflow.run,
                            TicketWorkflowInput(ticket_id=ticket_id, subject=subject),
                            id=ticket_id,
                            task_queue=TASK_QUEUE,
                        )
                    )
                except Exception as exc:
                    return self._json_response({"error": f"temporal_error: {exc}"}, 503)

                # The first activity (save_ticket_activity) runs synchronously within
                # the workflow before the 60-second sleep. Poll briefly until the row
                # appears in SQLite (usually < 200 ms).
                import time as _time
                for _ in range(20):
                    try:
                        ticket = get_ticket(ticket_id)
                        return self._json_response(ticket.to_dict(), 201)
                    except ValueError:
                        _time.sleep(0.1)
                return self._json_response({"error": "ticket_not_ready"}, 503)
            else:
                # Temporal not available — create directly in SQLite (fallback mode).
                try:
                    ticket = create_ticket(subject)
                    return self._json_response(ticket.to_dict(), 201)
                except Exception as exc:
                    return self._json_response({"error": str(exc)}, 500)

        # ── POST /tickets/{id}/claim ───────────────────────────────────────
        if self.path.startswith("/tickets/") and self.path.endswith("/claim"):
            path_parts = self.path.split("/")
            if len(path_parts) < 3:
                return self._json_response({"error": "invalid_path"}, 404)
            ticket_id = path_parts[2]
            body = self._read_body()
            if body is None:
                return
            data = parse_json(body)
            agent = data.get("agent")
            if not agent:
                return self._json_response({"error": "agent_required"}, 400)

            # Check ticket exists and is still open before signalling.
            try:
                ticket = get_ticket(ticket_id)
            except ValueError:
                return self._json_response({"error": "ticket_not_found"}, 404)

            if ticket.status != "open":
                return self._json_response(
                    {"error": "ticket_not_open", "current_status": ticket.status}, 409
                )

            if _temporal_available:
                try:
                    client = get_temporal_client()
                    handle: WorkflowHandle = client.get_workflow_handle(ticket_id)
                    _run_async(handle.signal(SlaWorkflow.claim_signal, agent))
                except RPCError as exc:
                    return self._json_response({"error": f"workflow_not_found: {exc}"}, 409)
                except Exception as exc:
                    return self._json_response({"error": f"temporal_error: {exc}"}, 503)

                # Poll until the claim is persisted to SQLite by the workflow activity.
                import time as _time
                for _ in range(20):
                    try:
                        ticket = get_ticket(ticket_id)
                        if ticket.status == "claimed":
                            return self._json_response(ticket.to_dict(), 200)
                    except ValueError:
                        pass
                    _time.sleep(0.1)

                try:
                    ticket = get_ticket(ticket_id)
                    return self._json_response(ticket.to_dict(), 200)
                except ValueError:
                    return self._json_response({"error": "ticket_not_found"}, 404)
            else:
                # Temporal not available — claim directly in SQLite (fallback mode).
                try:
                    ticket = claim_ticket(ticket_id, agent)
                    return self._json_response(ticket.to_dict(), 200)
                except TicketConflictError as exc:
                    return self._json_response(
                        {"error": "ticket_not_open", "current_status": str(exc)}, 409
                    )
                except ValueError:
                    return self._json_response({"error": "ticket_not_found"}, 404)

        self._json_response({"error": "not_found"}, 404)

    def do_GET(self) -> None:
        if self.path == "/tickets" or self.path == "/tickets/":
            tickets = get_all_tickets()
            return self._json_response([t.to_dict() for t in tickets], 200)

        if self.path.startswith("/tickets/"):
            path_parts = self.path.split("/")
            if len(path_parts) < 3:
                return self._json_response({"error": "invalid_path"}, 404)
            ticket_id = path_parts[2]
            try:
                ticket = get_ticket(ticket_id)
            except ValueError:
                return self._json_response({"error": "ticket_not_found"}, 404)
            return self._json_response(ticket.to_dict(), 200)

        # Serve static dashboard files
        url_path = self.path
        if url_path == "/" or url_path == "":
            url_path = "/index.html"

        static_dir = Path(__file__).resolve().parent / "static"
        file_path = (static_dir / url_path.lstrip("/")).resolve()

        is_relative = False
        try:
            file_path.relative_to(static_dir)
            is_relative = True
        except ValueError:
            pass

        if is_relative and file_path.is_file():
            ext = file_path.suffix.lower()
            content_type = "text/plain"
            if ext == ".html":
                content_type = "text/html"
            elif ext == ".css":
                content_type = "text/css"
            elif ext == ".js":
                content_type = "application/javascript"
            elif ext == ".png":
                content_type = "image/png"
            elif ext == ".jpg" or ext == ".jpeg":
                content_type = "image/jpeg"
            elif ext == ".svg":
                content_type = "image/svg+xml"
            elif ext == ".ico":
                content_type = "image/x-icon"

            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self._set_headers(200, content_type)
                self.wfile.write(content)
                return
            except Exception as e:
                return self._json_response({"error": f"Failed to read file: {str(e)}"}, 500)

        self._json_response({"error": "not_found"}, 404)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Suppress default access log noise to keep console clean."""
        pass


def run_server() -> None:
    init_ticket_table()

    # Start the async event loop in a background daemon thread.
    loop_thread = threading.Thread(target=_start_event_loop, daemon=True)
    loop_thread.start()

    # Wait for the background loop to be fully initialized.
    import time as _time
    for _ in range(50):
        if _loop is not None:
            break
        _time.sleep(0.05)

    # Pre-connect to Temporal so the first request is fast.
    global _temporal_available
    try:
        get_temporal_client()
        _temporal_available = True
        print("Connected to Temporal server — full workflow mode active.")
    except Exception as exc:
        _temporal_available = False
        print(f"WARNING: Could not connect to Temporal ({exc})")
        print("  Running in FALLBACK MODE — tickets will be saved directly to SQLite.")
        print("  Start 'temporal server start-dev' + 'py src/worker.py' for full SLA workflow mode.")

    server = HTTPServer((HOST, PORT), TicketRequestHandler)
    print(f"HTTP server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
