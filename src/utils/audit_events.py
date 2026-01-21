from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.models.audit import AuditEvent

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def make_event(
    *,
    phase: str,
    turn: int,
    kind: str,
    payload: Optional[Dict[str, Any]] = None,
    actor: Optional[str] = None,
) -> AuditEvent:
    return AuditEvent(
        ts=now_iso(),
        phase=phase,
        turn=turn,
        kind=kind,
        actor=actor,
        payload=payload or {},
    )
