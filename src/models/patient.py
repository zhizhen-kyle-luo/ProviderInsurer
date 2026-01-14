"""patient demographics, insurance, and clinical presentation models"""
from __future__ import annotations
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel


class PatientDemographics(BaseModel):
    patient_id: str
    age: int
    sex: Literal["M", "F"]
    mrn: str


class AdmissionNotification(BaseModel):
    patient_demographics: PatientDemographics
    preliminary_diagnoses: List[str]


class ClinicalPresentation(BaseModel):
    chief_complaint: str
    history_of_present_illness: str
    physical_exam_findings: str
    medical_history: List[str]