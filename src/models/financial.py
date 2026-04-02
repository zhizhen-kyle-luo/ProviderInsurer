"""unified service line model for both Phase 2 (278 authorization) and Phase 3 (837/835 claims)"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ServiceLineRequest(BaseModel):
    """
    unified service line for both 278 authorization and 837 claims

    maps to:
    - X12 278 Loop 2000F (authorization request/response)
    - X12 837 Loop 2400 (claim service line)
    - X12 835 SVC segment (remittance advice)

    represents lifecycle: PA request → PA decision → claim submission → adjudication

    per-line independence:
    - each line has its own request_type (diagnostic_test, treatment, level_of_care)
    - each line is adjudicated independently (different statuses per line allowed)
    - terminal status evaluated per-line: one line terminal doesn't affect others
    - workflow continues until ALL lines reach terminal status
    """
    # X12 278/837 SV1 segment (shared fields)
    line_number: int  # 837 LX-01 explicit counter, 278 implicit sequence
    procedure_code: str  # SV1-01: CPT/HCPCS/J-code
    code_type: str  # qualifier: "CPT", "HCPCS", "J-code", "NDC"
    requested_quantity: int  # SV1-03 or HSD-01
    quantity_unit: Optional[str] = None  # HSD: "days", "visits", "units", "infusions"

    # X12 278 SV1-02 / 837 SV1-02 (charge amount)
    # charge_amount: Optional[float] = None  # optional in 278, required in 837

    # X12 278/837 HI segment (diagnosis)
    diagnosis_codes: Optional[List[str]] = None  # ICD-10 codes for this line

    # Phase 2 specific: clinical justification (X12 278 PWK/MSG segments)
    clinical_rationale: Optional[str] = None  # phase 2 PA + phase 3 appeals

    # Phase 2 specific: service type and details (X12 278 UM segment context)
    request_type: Optional[str] = None  # "treatment", "diagnostic_test", "level_of_care"
    service_name: Optional[str] = None  # drug name, procedure name, etc.
    service_description: Optional[str] = None  # human-friendly display label (used in prompts/claims)

    # coding options (X12 278/837 SV1 qualifiers - type-specific)
    ndc_code: Optional[str] = None  # national drug code
    j_code: Optional[str] = None  # j-code for infused meds
    cpt_code: Optional[str] = None  # current procedural terminology

    # service details (X12 278 context, optional)
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    visit_count: Optional[int] = None

    # Phase 2 decision fields (X12 278 HCR response)
    authorization_status: Optional[str] = None  # "approved" | "modified" | "denied" | "pending_info"
    approved_quantity: Optional[int] = None  # HCR partial/modified approval
    authorization_number: Optional[str] = None  # REF*9F in 837 claim (links 278→837)
    modification_type: Optional[str] = None  # "quantity_reduction" | "code_downgrade"

    # shared decision fields (both phases - X12 278 HCR03/MSG, 835 LQ remark)
    decision_reason: Optional[str] = None  # why approved/denied/modified/pending_info
    requested_documents: List[str] = Field(default_factory=list)  # if pending_info: what docs needed

    # Phase 3 decision fields (X12 835 SVC/CLP response)
    adjudication_status: Optional[str] = None  # "approved" | "modified" | "denied" | "pending_info"
    # allowed_amount: Optional[float] = None  # 835 SVC-02: contractual rate
    # paid_amount: Optional[float] = None  # 835 SVC-03: actual payment

    # X12 835 CAS segment (adjustment tracking - phase 3 only)
    adjustment_group_code: Optional[str] = None  # "CO" | "PR" | "OA" (who pays)
    # adjustment_amount: Optional[float] = None  # $ amount adjusted

    # workflow tracking (internal, not X12)
    current_review_level: int = 0  # initial=0, reconsideration=1, IRE=2
    reviewer_type: Optional[str] = None  # "UM Triage", "Medical Director", "IRE"
    treat_anyway: bool = False  # after abandon: whether provider treated despite non-approval
    accepted_modification: bool = False  # whether provider accepted modified terms
    abandoned: bool = False  # provider abandoned pursuit of this line (accepts denial/doesn't fight)
    request_revision : int = 0
    delivered : bool = False  # for Phase 3 claims: whether service was delivered
    pend_round : int = 0  # how many times this line has been pended
    pend_total : int = 0  # total times this line has been pended across all rounds
    awaiting_response_at_level: Optional[int] = None  # set when appeal filed, cleared when insurer responds