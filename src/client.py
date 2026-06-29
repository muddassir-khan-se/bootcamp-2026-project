from __future__ import annotations

"""
TicketClient — Business-Level HTTP Client for the SLA Ticketing Service
========================================================================

Usage example::

    from src.client import TicketClient, TicketNotFoundError, TicketClientError

    client = TicketClient(base_url="http://127.0.0.1:8000")

    # Create a new ticket
    ticket = client.create_ticket("Database service is unreachable")
    print(ticket.id, ticket.status)  # uuid  open

    # Claim the ticket
    claimed = client.claim_ticket(ticket.id, agent="agent-alpha")
    print(claimed.status)  # claimed

    # Inspect a ticket
    t = client.get_ticket(ticket.id)

    # List all tickets
    tickets = client.get_all_tickets()
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, List, Optional

try:
    from .models import Ticket
except ImportError:
    from models import Ticket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TicketClientError(Exception):
    """Base exception raised for all ticketing client failures.

    Attributes:
        message: Human-readable error description.
        http_status: The HTTP status code returned by the server, if any.
    """

    def __init__(self, message: str, http_status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, http_status={self.http_status!r})"


class TicketNotFoundError(TicketClientError):
    """Raised when the requested ticket does not exist (HTTP 404)."""


class TicketValidationError(TicketClientError):
    """Raised when the request payload is rejected by the server (HTTP 400)."""


class TicketServiceUnavailableError(TicketClientError):
    """Raised when the ticketing service cannot be reached or returns 5xx."""


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------


def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-format datetime string or return None."""
    return datetime.fromisoformat(value) if value else None


def _deserialize_ticket(data: dict[str, Any]) -> Ticket:
    """Deserialize a raw API response dictionary into a ``Ticket`` domain object.

    Args:
        data: Dictionary returned from the tickets REST API.

    Returns:
        A fully-populated ``Ticket`` dataclass instance.

    Raises:
        TicketClientError: If required fields are missing from the payload.
    """
    try:
        return Ticket(
            id=data["id"],
            subject=data["subject"],
            created_at=datetime.fromisoformat(data["created_at"]),
            status=data["status"],
            claimed_by=data.get("claimed_by"),
            claimed_at=_parse_optional_datetime(data.get("claimed_at")),
            escalated_at=_parse_optional_datetime(data.get("escalated_at")),
            sla_deadline=_parse_optional_datetime(data.get("sla_deadline")),
        )
    except (KeyError, ValueError) as exc:
        raise TicketClientError(
            f"Unexpected response format from server: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TicketClient:
    """Business-level HTTP client for the SLA Ticketing Service.

    This client provides a clean, domain-oriented interface over the raw REST
    API.  All responses are deserialized into ``Ticket`` domain objects.
    Network and protocol errors are translated into typed exceptions so
    callers never need to handle raw ``urllib`` exceptions.

    Args:
        base_url: Root URL of the ticketing service.
                  Defaults to ``http://127.0.0.1:8000``.
        timeout:  Socket timeout in seconds for each request.
                  Defaults to ``10``.

    Example::

        client = TicketClient("http://tickets.internal:8000", timeout=5)
        ticket = client.create_ticket("Login service is down")
        client.claim_ticket(ticket.id, agent="ops-team-1")
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: int = 10,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal transport
    # ------------------------------------------------------------------

    def _build_url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Send an HTTP request and return the parsed JSON response body.

        Args:
            method:  HTTP verb (``"GET"``, ``"POST"``, etc.).
            path:    API path relative to ``base_url``.
            payload: Optional request body that will be JSON-encoded.

        Returns:
            Parsed JSON value (``dict`` or ``list``).

        Raises:
            TicketNotFoundError: Server returned HTTP 404.
            TicketValidationError: Server returned HTTP 400.
            TicketServiceUnavailableError: Server returned 5xx or is unreachable.
            TicketClientError: Any other error.
        """
        url = self._build_url(path)
        body: Optional[bytes] = (
            json.dumps(payload).encode("utf-8") if payload is not None else None
        )
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        logger.debug("→ %s %s payload=%r", method, url, payload)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                logger.debug("← %s %s", resp.status, url)
                return json.loads(raw)

        except urllib.error.HTTPError as exc:
            http_status = exc.code
            error_message: Optional[str] = None
            try:
                body_str = exc.read().decode("utf-8")
                error_payload = json.loads(body_str)
                error_message = error_payload.get("error")
            except Exception:
                error_message = None
            finally:
                exc.close()

            logger.warning("← HTTP %s %s  error=%r", http_status, url, error_message)

            if http_status == 404 or error_message == "ticket_not_found":
                raise TicketNotFoundError(
                    error_message or "Ticket not found",
                    http_status=http_status,
                ) from exc
            if http_status == 400:
                raise TicketValidationError(
                    error_message or f"Bad request: {http_status}",
                    http_status=http_status,
                ) from exc
            if http_status >= 500:
                raise TicketServiceUnavailableError(
                    error_message or f"Service error: {http_status}",
                    http_status=http_status,
                ) from exc
            raise TicketClientError(
                error_message or f"HTTP {http_status}: {exc.reason}",
                http_status=http_status,
            ) from exc

        except urllib.error.URLError as exc:
            reason = str(exc.reason)
            logger.error("Connection failed: %s  url=%s", reason, url)
            raise TicketServiceUnavailableError(
                f"Connection failed: {reason}"
            ) from exc

        except Exception as exc:
            raise TicketClientError(f"Unexpected error: {exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_ticket(self, subject: str) -> Ticket:
        """Create a new support ticket with the given subject.

        The SLA countdown starts immediately at ticket creation.
        An agent must claim the ticket within the configured SLA window
        (default: 60 seconds) to prevent automatic escalation.

        Args:
            subject: A brief description of the support issue.
                     Must be a non-empty string.

        Returns:
            The newly created ``Ticket`` with ``status="open"``.

        Raises:
            TicketValidationError: If ``subject`` is empty or missing.
            TicketServiceUnavailableError: If the service is unreachable.
            TicketClientError: For any other failure.

        Example::

            ticket = client.create_ticket("Payment gateway timeout")
        """
        if not subject or not subject.strip():
            raise TicketValidationError("subject must be a non-empty string")
        response = self._request("POST", "/tickets", {"subject": subject.strip()})
        return _deserialize_ticket(response)

    def claim_ticket(self, ticket_id: str, agent: str) -> Ticket:
        """Claim an open support ticket under the specified agent identity.

        Claiming a ticket stops the SLA escalation timer and records
        the agent's identity along with the claim timestamp.

        Args:
            ticket_id: UUID of the ticket to claim.
            agent:     Agent identifier (e.g. ``"ops-team-1"``).
                       Must be a non-empty string.

        Returns:
            The updated ``Ticket`` with ``status="claimed"``.

        Raises:
            TicketNotFoundError: If the ticket does not exist.
            TicketValidationError: If ``agent`` is empty or missing.
            TicketServiceUnavailableError: If the service is unreachable.
            TicketClientError: For any other failure.

        Example::

            claimed = client.claim_ticket(ticket.id, agent="ops-team-1")
        """
        if not agent or not agent.strip():
            raise TicketValidationError("agent must be a non-empty string")
        response = self._request(
            "POST", f"/tickets/{ticket_id}/claim", {"agent": agent.strip()}
        )
        return _deserialize_ticket(response)

    def get_ticket(self, ticket_id: str) -> Ticket:
        """Retrieve the current state of a specific ticket by its ID.

        Args:
            ticket_id: UUID of the ticket to inspect.

        Returns:
            The ``Ticket`` with its current status, timestamps, and metadata.

        Raises:
            TicketNotFoundError: If the ticket does not exist.
            TicketServiceUnavailableError: If the service is unreachable.
            TicketClientError: For any other failure.

        Example::

            ticket = client.get_ticket("3f2e1d4c-...")
            print(ticket.status)  # "open" | "claimed" | "escalated"
        """
        response = self._request("GET", f"/tickets/{ticket_id}")
        return _deserialize_ticket(response)

    def get_all_tickets(self) -> List[Ticket]:
        """Retrieve all support tickets ordered by creation date (newest first).

        Returns:
            A list of ``Ticket`` objects.  Returns an empty list if no
            tickets exist yet.

        Raises:
            TicketServiceUnavailableError: If the service is unreachable.
            TicketClientError: For any other failure.

        Example::

            tickets = client.get_all_tickets()
            open_tickets = [t for t in tickets if t.status == "open"]
        """
        response = self._request("GET", "/tickets")
        if not isinstance(response, list):
            raise TicketClientError(
                f"Unexpected response format: expected list, got {type(response).__name__}"
            )
        return [_deserialize_ticket(item) for item in response]
