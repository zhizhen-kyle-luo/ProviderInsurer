from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

#internal
AuditPhase = Literal[
    "phase_1_presentation",
    "phase_2_utilization_review",
    "phase_3_claims",
    "phase_4_financial",
]


class AuditEvent(BaseModel):
    ts: str
    phase: AuditPhase
    turn: int
    kind: str
    actor: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class AuditLog(BaseModel):
    case_id: str
    run_id: str
    simulation_start: str
    simulation_end: Optional[str] = None

    events: List[AuditEvent] = Field(default_factory=list)
    agent_configs: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)

    # policy information
    provider_policy: Optional[Dict[str, Any]] = None
    payor_policy: Optional[Dict[str, Any]] = None

    # environment configuration
    environment_config: Optional[Dict[str, Any]] = None

    # experiment metadata
    context_mode: Optional[str] = None
