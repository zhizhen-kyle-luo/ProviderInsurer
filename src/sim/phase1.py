"""
Only load the actualy case in run script, this is just phase 1 logic for any cases
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional

from src.models.patient import PatientVisibleData
from src.models.state import EncounterState

# Internal helpers
_REQUIRED_PATIENT_KEYS = [
    "patient_id",
    "age",
    "sex",
    "admission_source",
    "chief_complaint",
    "medical_history",
    "medications",
    "vital_signs",
    "presenting_symptoms",
    "physical_exam",
    "clinical_notes",
    "lab_results",
]
def _assert_required_keys(obj: Dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted([k for k in required if k not in obj])
    if missing:
        raise ValueError(f"{label} missing required keys: {missing}")

def run_phase1(
    *,
    case: Dict[str, Any],
    encounter_id: Optional[str] = None,
) -> EncounterState:
    """
    Phase 1: Validate case schema and initialize EncounterState.

    - Raises if any required keys are missing.
    - Does not fabricate defaults.
    - Prepares an audit bucket for later dynamic patient_visible updates.
    """
    if "case_id" not in case:
        raise ValueError("case missing required key: case_id")
    if "case_type" not in case:
        raise ValueError("case missing required key: case_type")
    if "patient_visible_data" not in case:
        raise ValueError("case missing required key: patient_visible_data")
    if "environment_hidden_data" not in case:
        raise ValueError("case missing required key: environment_hidden_data")

    raw_pvd = case["patient_visible_data"]
    if not isinstance(raw_pvd, dict):
        raise ValueError("case.patient_visible_data must be a dict")

    _assert_required_keys(raw_pvd, _REQUIRED_PATIENT_KEYS, "case.patient_visible_data")

    # Pydantic will enforce type constraints (e.g., sex in {"M","F"}).
    pvd_model = PatientVisibleData(**raw_pvd)

    state = EncounterState(
        case_id=case["case_id"],
        case_type=case["case_type"],
        patient_visible_data=pvd_model,
        environment_hidden_data=deepcopy(case["environment_hidden_data"]),
        #everything else defaults
    )

    if encounter_id is not None:
        state.encounter_id = encounter_id

    return state