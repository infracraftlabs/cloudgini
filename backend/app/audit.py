from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent


def record(db: Session, actor: str, role: str, event: str, target_type: str, target_id: str,
           outcome: str = "success", **details: Any) -> None:
    """Append one audit event. Callers commit; there is no update or delete path."""
    db.add(AuditEvent(actor=actor, role=role, event=event, target_type=target_type, target_id=str(target_id),
                      outcome=outcome, details=details))
