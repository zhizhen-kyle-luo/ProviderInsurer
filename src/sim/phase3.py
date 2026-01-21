from __future__ import annotations
from typing import Any, Dict, Optional
from src.models.state import EncounterState
from src.sim.engine import run as run_engine
from src.sim.phase3_adapter import Phase3Adapter
from src.utils.audit_logger import AuditLogger


def run_phase3(
    *,
    state: EncounterState,
    provider_copilot_llm,
    payor_copilot_llm,
    provider_base_llm=None,
    payor_base_llm=None,
    provider_params: Optional[Dict[str, Any]] = None,
    payor_params: Optional[Dict[str, Any]] = None,
    max_turns: int = 3,
    audit_logger: Optional[AuditLogger] = None,
    seed: Optional[int] = None,
) -> EncounterState:
    if provider_params is not None:
        state.provider_params = provider_params
    if payor_params is not None:
        state.payor_params = payor_params

    lines = getattr(state, "service_lines", []) or []
    for line in lines:
        if line.authorization_status in {"approved"}:
            line.delivered = True
        elif line.authorization_status == "modified" and line.accepted_modification:
            line.delivered = True
        elif line.treat_anyway:
            line.delivered = True

    adapter = Phase3Adapter(
        provider_copilot_llm=provider_copilot_llm,
        payor_copilot_llm=payor_copilot_llm,
        provider_base_llm=provider_base_llm,
        payor_base_llm=payor_base_llm,
        provider_params=provider_params,
        payor_params=payor_params,
        audit_logger=audit_logger,
    )

    return run_engine(
        state=state,
        adapter=adapter,
        max_turns=max_turns,
        audit_logger=audit_logger,
        seed=seed,
    )
