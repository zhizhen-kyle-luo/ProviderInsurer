"""financial models - claim line items for Phase 3 adjudication"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ClaimLineItem(BaseModel):
    """
    individual service line on a claim with adjudication tracking
    aligns with X12 837 claim line / X12 835 remittance advice
    """
    # provider submission (X12 837 SV1/SV2 segment)
    line_number: int  # sequence on claim
    procedure_code: str  # CPT/HCPCS/J-code
    code_type: str  # "CPT", "HCPCS", "J-code", "NDC"
    service_description: str
    quantity: int
    billed_amount: float  # amount per unit or total

    # diagnosis pointer (links to claim-level diagnosis codes)
    diagnosis_pointers: List[int] = Field(default_factory=list)  # references to diagnosis_codes array

    # adjudication status (X12 835 CAS segment)
    adjudication_status: Optional[str] = None  # "approved", "downgrade", "denied", "pending_info"
    allowed_amount: Optional[float] = None
    paid_amount: Optional[float] = None
    adjustment_reason: Optional[str] = None

    current_review_level: int = 0 
    reviewer_type: Optional[str] = None
    provider_action: Optional[str] = None
