"""financial settlement and DRG assignment models (Phase 4)"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ServiceLineItem(BaseModel):
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
