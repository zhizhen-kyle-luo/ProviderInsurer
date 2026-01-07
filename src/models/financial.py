"""financial settlement and DRG assignment models (Phase 4)"""
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
    adjudication_status: Optional[str] = None  # "approved", "denied", "partial", "pending"
    allowed_amount: Optional[float] = None  # payor's allowed amount (contractual rate)
    paid_amount: Optional[float] = None  # actual payment
    adjustment_reason: Optional[str] = None  # denial/adjustment reason
    adjustment_code: Optional[str] = None  # CARC/RARC code (optional)

    # review level tracking (enables line-level appeals)
    current_review_level: int = 0  # 0 (initial), 1 (internal appeal), 2 (IRE)
    reviewer_type: Optional[str] = None  # who adjudicated this line

    # provider decision on this line
    provider_action: Optional[str] = None  # "accept", "appeal", "withdrawn"


class ServiceLineItem(BaseModel):
    """
    DEPRECATED: kept for backward compatibility
    use ClaimLineItem for Phase 3 claims adjudication
    """
    service_description: str
    cpt_or_drg_code: str
    billed_amount: float
    allowed_amount: float
    paid_amount: float


class DRGAssignment(BaseModel):
    drg_code: str
    drg_description: str
    relative_weight: float
    geometric_mean_los: float
    base_payment_rate: float
    total_drg_payment: float


class FinancialSettlement(BaseModel):
    line_items: List[ServiceLineItem] = Field(default_factory=list)
    drg_assignment: Optional[DRGAssignment] = None
    total_billed_charges: float
    total_allowed_amount: float
    payer_payment: float
    patient_responsibility: float
    outlier_payment: float = 0.0
    quality_adjustments: float = 0.0
    total_hospital_revenue: float
    estimated_hospital_cost: float
    hospital_margin: float
