"""main encounter state object combining all phase data"""
from __future__ import annotations

from datetime import date
from typing import Dict, Any, Optional, List, Literal, TYPE_CHECKING
from pydantic import BaseModel, Field

from .case_types import CaseType
from .patient import AdmissionNotification, ClinicalPresentation
from .financial import ServiceLineRequest
from .metrics import FrictionMetrics

if TYPE_CHECKING:
    from .audit import AuditLog
else:
    AuditLog = "AuditLog"  # forward ref placeholder


Phase = Literal[
    "phase_1_presentation",
    "phase_2_utilization_review",
    "phase_3_claims",
    "phase_4_financial",
]


class EncounterState(BaseModel):
    # identity
    case_id: str
    encounter_id: str = Field(default_factory=lambda: f"ENC-{date.today().strftime('%Y%m%d')}")

    # routing
    case_type: str = CaseType.SPECIALTY_MEDICATION
    phase: Phase = "phase_1_presentation"
    turn: int = 0  # generic turn counter (Phase 2 increments each round-trip)

    # phase 1 / shared clinical context
    admission: AdmissionNotification
    clinical_presentation: ClinicalPresentation

    # unified service line objects (Phase 2 requests + Phase 3/4 fields are optional inside the line model)
    service_lines: List[ServiceLineRequest] = Field(default_factory=list)

    # metrics + audit
    friction_metrics: FrictionMetrics = Field(default_factory=FrictionMetrics)
    audit_log: Optional["AuditLog"] = None

    # behavioral parameters (optional)
    provider_params: Optional[Dict[str, Any]] = None
    payor_params: Optional[Dict[str, Any]] = None

    # cross-phase carry-forward evidence (only what you truly need later)
    phase_2_evidence: Dict[str, Any] = Field(default_factory=dict)
