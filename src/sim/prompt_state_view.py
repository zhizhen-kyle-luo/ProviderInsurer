from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.models.patient import PatientVisibleData


@dataclass
class Phase2PromptStateView:
    patient_visible_data: PatientVisibleData
    service_lines: Any
    provider_policy_view: Optional[Dict[str, Any]]
    payor_policy_view: Optional[Dict[str, Any]]


def build_phase2_prompt_state(state) -> Phase2PromptStateView:
    pv = getattr(state, "patient_visible_data", None)
    if pv is None:
        raise ValueError("state missing required field: patient_visible_data")

    if isinstance(pv, dict):
        pv_model = PatientVisibleData(**pv)
    else:
        pv_model = pv

    return Phase2PromptStateView(
        patient_visible_data=pv_model,
        service_lines=getattr(state, "service_lines", []),
        provider_policy_view=getattr(state, "provider_policy_view", None),
        payor_policy_view=getattr(state, "payor_policy_view", None),
    )
