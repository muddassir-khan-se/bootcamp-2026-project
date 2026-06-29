"""
Carfullfy SLA Escalation Engine - HTTP Server & Static Asset Router.
Provides REST API endpoints for ticket lifecycle management and serves the frontend dashboard.
Author: Muddassir Khan | Bootcamp 2026
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

try:
    from .sla_scheduler import SlaScheduler
    from .ticket_service import claim_ticket, create_ticket, get_ticket, init_ticket_table, get_all_tickets
except ImportError:
    from sla_scheduler import SlaScheduler
    from ticket_service import claim_ticket, create_ticket, get_ticket, init_ticket_table, get_all_tickets

HOST = "127.0.0.1"
PORT = 8000


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

    def do_POST(self) -> None:
        if self.path == "/tickets":
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = parse_json(body)
            subject = data.get("subject")
            if not subject:
                return self._json_response({"error": "subject_required"}, 400)
            ticket = create_ticket(subject)
            return self._json_response(ticket.to_dict(), 201)

        if self.path.startswith("/tickets/") and self.path.endswith("/claim"):
            path_parts = self.path.split("/")
            if len(path_parts) < 3:
                return self._json_response({"error": "invalid_path"}, 404)
            ticket_id = path_parts[2]
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = parse_json(body)
            agent = data.get("agent")
            if not agent:
                return self._json_response({"error": "agent_required"}, 400)
            try:
                ticket = claim_ticket(ticket_id, agent)
            except ValueError:
                return self._json_response({"error": "ticket_not_found"}, 404)
            return self._json_response(ticket.to_dict(), 200)

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


def run_server() -> None:
    init_ticket_table()
    scheduler = SlaScheduler()
    scheduler.start()
    server = HTTPServer((HOST, PORT), TicketRequestHandler)
    print(f"Server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    run_server()
