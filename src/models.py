from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Ticket:
    id: str
    subject: str
    created_at: datetime
    status: str
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "subject": self.subject,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "sla_deadline": self.sla_deadline.isoformat() if self.sla_deadline else None,
        }
