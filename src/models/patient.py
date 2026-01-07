"""patient demographics, insurance, and clinical presentation models"""
from __future__ import annotations
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel


class PatientDemographics(BaseModel):
    patient_id: str
    age: int
    sex: Literal["M", "F"]
    mrn: str


class InsuranceInfo(BaseModel):
    plan_type: Literal["MA", "Commercial", "Medicare_FFS", "Medicaid"]
    payer_name: str
    member_id: str
    group_number: Optional[str] = None
    authorization_required: bool = True


class AdmissionNotification(BaseModel):
    patient_demographics: PatientDemographics
    insurance: InsuranceInfo
    admission_source: str  # free text: "ER", "Direct", "Transfer", or ""
    chief_complaint: str
    preliminary_diagnoses: List[str]


class ClinicalPresentation(BaseModel):
    chief_complaint: str
    history_of_present_illness: str
    vital_signs: Dict[str, Any]
    physical_exam_findings: str
    medical_history: List[str]