"""diagnostic tests, lab results, and imaging models"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class DiagnosticTest(BaseModel):
    test_name: str
    cpt_code: Optional[str] = None
    icd10_codes: List[str] = Field(default_factory=list)
    clinical_rationale: str


class LabResult(BaseModel):
    test_name: str
    result_summary: str


class ImagingResult(BaseModel):
    exam_name: str
    impression: str


class TestOrdered(BaseModel):
    test_name: str
    cpt_code: Optional[str] = None
    rationale: Optional[str] = None
