"""
Main run state object for a single simulation run.

- Holds provider-visible patient data (mutable only for "revealed already-documented" info, if used).
- Holds env-only hidden truth from case file (never passed to agents).
- Holds service_lines (Phase2/3/4 unified line model).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, List, Literal, TYPE_CHECKING
from pydantic import BaseModel, Field

from .patient import PatientVisibleData
from .financial import ServiceLineRequest
from .metrics import FrictionMetrics

if TYPE_CHECKING:
    from .audit import AuditLog
else:
    AuditLog = "AuditLog"

#internal
Phase = Literal[
    "phase_1_presentation",
    "phase_2_utilization_review",
    "phase_3_claims",
    "phase_4_financial",
]


class EncounterState(BaseModel):
    # identity (from case file)
    case_id: str
    case_type: str = ""  # metadata only; do not branch on it

    encounter_id: str = Field(default_factory=lambda: f"ENC-{date.today().strftime('%Y%m%d')}")

    # routing
    phase: Phase = "phase_1_presentation"
    turn: int = 0

    # provider-visible data (directly from case file schema)
    patient_visible_data: PatientVisibleData

    # env-only hidden truth (directly from case file schema)
    environment_hidden_data: Dict[str, Any] = Field(default_factory=dict)

    # unified service line objects (Phase 2 requests + Phase 3/4 fields optional inside line model)
    service_lines: List[ServiceLineRequest] = Field(default_factory=list)

    # metrics + audit
    friction_metrics: FrictionMetrics = Field(default_factory=FrictionMetrics)
    audit_log: Optional["AuditLog"] = None

    # cross-phase workflow flags/metadata (internal)
    current_level: int = 0
    denial_occurred: bool = False
    independent_review_reached: bool = False
    provider_treated_despite_denial: bool = False
    care_abandoned: bool = False
    claim_pended: bool = False
    claim_rejected: bool = False
    phase_2_evidence: Optional[Dict[str, Any]] = None
    provider_policy_view: Optional[Dict[str, Any]] = None

    # evaluation / truth-check bookkeeping (optional)
    final_authorized_level: Optional[str] = None
    ground_truth_outcome: Optional[str] = None
    simulation_matches_reality: Optional[bool] = None

    #submission, response, updates
    document_store : Dict[str, Any] = Field(default_factory=dict)
    phase2_submissions : List[Dict[str, Any]] = Field(default_factory=list)
    phase2_responses : List[Dict[str, Any]] = Field(default_factory=list)
    phase3_submissions : List[Dict[str, Any]] = Field(default_factory=list)
    phase3_responses : List[Dict[str, Any]] = Field(default_factory=list)

    # behavioral params (optional knobs)
    provider_params: Optional[Dict[str, Any]] = None
    payor_params: Optional[Dict[str, Any]] = None
