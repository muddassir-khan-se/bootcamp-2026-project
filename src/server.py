from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .sla_scheduler import SlaScheduler
from .ticket_service import claim_ticket, create_ticket, get_ticket, init_ticket_table

HOST = "127.0.0.1"
PORT = 8000


def parse_json(body: bytes) -> dict[str, Any]:
    return json.loads(body.decode("utf-8")) if body else {}


class TicketRequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def _json_response(self, payload: Any, code: int = 200) -> None:
        self._set_headers(code)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

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
