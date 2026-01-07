"""unified authorization request model (X12 278 / FHIR PAS aligned)"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class AuthorizationRequest(BaseModel):
    """
    unified PA request and decision for all service types (medications, procedures, admissions)
    aligns with X12 278 EDI transaction standard where request and decision travel together
    """
    # REQUEST fields (provider submits these)
    request_type: str  # "medication", "procedure", "admission", "imaging", "dme"
    service_name: str  # drug name, procedure name, etc.
    clinical_rationale: str
    diagnosis_codes: List[str] = Field(default_factory=list)  # ICD-10 codes

    # coding (type-specific but all optional)
    ndc_code: Optional[str] = None  # national drug code (for medications)
    j_code: Optional[str] = None    # j-code (for infused medications)
    cpt_code: Optional[str] = None  # current procedural terminology (for procedures)

    # service details (all optional - include what's relevant)
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    visit_count: Optional[int] = None
    site_of_service: Optional[str] = None

    # service quantity (HSD-like - X12 278 Health Care Services Delivery)
    # enables partial approval scenarios: "requested 5 infusions, approved 3"
    requested_quantity: Optional[int] = None  # provider's requested amount
    quantity_unit: Optional[str] = None  # "infusions", "days", "visits", "units", "treatments"

    # step therapy / prior authorization history (optional)
    prior_therapies_failed: List[str] = Field(default_factory=list)
    step_therapy_completed: bool = False

    # DECISION fields (payer fills these in - mirrors X12 278 response)
    authorization_status: Optional[str] = None  # "approved", "denied", "pended", "partial"
    denial_reason: Optional[str] = None
    appeal_notes: Optional[str] = None

    # quantity decision (enables partial approvals)
    approved_quantity_amount: Optional[int] = None  # how many units approved (if different from requested)
    # note: quantity_unit is shared between request and decision

    missing_documentation: List[str] = Field(default_factory=list)  # only populated for pended status
    reviewer_type: Optional[str] = None  # "UM Triage Reviewer", "Medical Director", "IRE"
    review_level: Optional[int] = None  # 0, 1, or 2 (Medicare appeals level)
