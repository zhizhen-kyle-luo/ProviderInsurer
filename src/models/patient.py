"""
Provider-visible patient data schema (matches case JSON patient_visible_data).

Principles:
- Required fields always present (empty "" / {} / [] if not documented).
- No case-type branching.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field


class PatientVisibleData(BaseModel):
    patient_id: str
    age: int
    sex: Literal["M", "F"]

    admission_source: str = ""
    chief_complaint: str = ""
    medical_history: List[str] = Field(default_factory=list)
    medications: List[str] = Field(default_factory=list)
    vital_signs: Dict[str, Any] = Field(default_factory=dict)

    presenting_symptoms: str = ""
    physical_exam: str = ""
    clinical_notes: str = ""
    lab_results: Dict[str, Any] = Field(default_factory=dict)
