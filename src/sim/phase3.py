from __future__ import annotations
from typing import Any, Dict, Optional
from src.models.state import EncounterState
from src.sim.engine import run as run_engine
from src.sim.phase3_adapter import Phase3Adapter
from src.utils.audit_logger import AuditLogger


def run_phase3(
    *,
    state: EncounterState,
    provider_llm,
    payor_llm,
    provider_params: Optional[Dict[str, Any]] = None,
    payor_params: Optional[Dict[str, Any]] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> EncounterState:
    if provider_params is not None:
        state.provider_params = provider_params
    if payor_params is not None:
        state.payor_params = payor_params

    lines = getattr(state, "service_lines", []) or []
    for line in lines:
        should_deliver = (
            line.authorization_status == "approved"
            or (line.authorization_status == "modified" and line.accepted_modification)
            or line.treat_anyway
        )
        if should_deliver:
            line.delivered = True

    adapter = Phase3Adapter(
        provider_llm=provider_llm,
        payor_llm=payor_llm,
        provider_params=provider_params,
        payor_params=payor_params,
        audit_logger=audit_logger,
    )

    return run_engine(
        state=state,
        adapter=adapter,
        audit_logger=audit_logger,
    )
