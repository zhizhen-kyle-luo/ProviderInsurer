"""main encounter state object combining all phase data"""
from __future__ import annotations
from typing import Dict, Any, Optional, Union, Literal, List, TYPE_CHECKING
from datetime import date
from pydantic import BaseModel, Field

from .case_types import CaseType
from .patient import AdmissionNotification, ClinicalPresentation
from .financial import ServiceLineRequest
from .metrics import FrictionMetrics

if TYPE_CHECKING:
    from .audit import AuditLog
else:
    AuditLog = "AuditLog"  # forward ref placeholder


class EncounterState(BaseModel):
    case_id: str
    encounter_id: str = Field(default_factory=lambda: f"ENC-{date.today().strftime('%Y%m%d')}")

    # case type discriminator
    case_type: str = CaseType.INPATIENT_ADMISSION

    admission: AdmissionNotification
    clinical_presentation: ClinicalPresentation

    # unified service lines for both Phase 2 (278 authorization) and Phase 3 (837/835 claims)
    service_lines: List[ServiceLineRequest] = Field(default_factory=list)

    denial_occurred: bool = False
    appeal_filed: bool = False
    appeal_successful: bool = False
    provider_treated_despite_denial: bool = False

    # phase 3 pend tracking
    claim_pended: bool = False
    claim_rejected: bool = False
    claim_abandoned_via_pend: bool = False
    pend_iterations: int = 0

    # phase 3 billing - Provider's actual chosen amount (for DRG upcoding analysis)
    phase_3_billed_amount: Optional[float] = None
    phase_3_diagnosis_code: Optional[str] = None

    # X12 837 CLM / 835 CLP claim-level totals (sum of all service_lines)
    claim_total_charge: Optional[float] = None  # X12 837 CLM-02: total billed
    claim_total_allowed: Optional[float] = None  # X12 835 CLP-03: payer allowed amount
    claim_total_paid: Optional[float] = None  # X12 835 CLP-04: actual payment

    # friction model - policy asymmetry and friction tracking
    friction_metrics: Optional[FrictionMetrics] = None
    provider_policy_view: Dict[str, Any] = Field(default_factory=dict)  # fuzzy clinical view (GOLD)
    payor_policy_view: Dict[str, Any] = Field(default_factory=dict)  # strict coverage view (InterQual)

    ground_truth_outcome: Optional[Union[Literal["inpatient", "observation"], Literal["approved", "denied"]]] = None
    simulation_matches_reality: Optional[bool] = None

    # level-specific tracking for Medicare Advantage workflow (0-indexed: L0=triage, L1=reconsideration, L2=IRE)
    current_level: int = 0
    independent_review_reached: bool = False  # true when escalated to Level 2 (IRE)
    request_info_cycles_by_level: Dict[int, int] = Field(default_factory=dict)

    # audit log for LLM interactions
    audit_log: Optional["AuditLog"] = None

    # truth checking results (deception detection)
    # using Any to avoid circular import with src.evaluation.truth_checker
    truth_check_phase2: Optional[Any] = None  # FactCheckResult type
    truth_check_phase3: Optional[Any] = None  # FactCheckResult type

    # provider behavioral parameters
    provider_params: Optional[Dict[str, Any]] = None
