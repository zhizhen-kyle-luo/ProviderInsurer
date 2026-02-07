from __future__ import annotations
from typing import Any, Dict, Optional
from src.models.state import EncounterState
from src.sim.phase1 import run_phase1
from src.sim.phase2 import run_phase2
from src.sim.phase3 import run_phase3
from src.sim.phase4 import run_phase4
from src.utils.audit_logger import AuditLogger
from src.utils.environment import Environment


def run_full_simulation(
    *,
    case: Dict[str, Any],
    provider_llm,
    payor_llm,
    provider_params: Optional[Dict[str, Any]] = None,
    payor_params: Optional[Dict[str, Any]] = None,
    audit_logger: Optional[AuditLogger] = None,
    environment: Optional[Environment] = None,
) -> EncounterState:
    """
    run all 4 phases in sequence:
    - phase 1: patient presentation (validation/initialization)
    - phase 2: utilization review (authorization)
    - phase 3: claim adjudication
    - phase 4: financial settlement (metrics calculation)
    """

    state = run_phase1(case=case)

    if audit_logger:
        state.audit_log = audit_logger

    state = run_phase2(
        state=state,
        provider_llm=provider_llm,
        payor_llm=payor_llm,
        provider_params=provider_params,
        payor_params=payor_params,
        audit_logger=audit_logger,
        environment=environment,
    )

    # Check if any lines should be delivered to Phase 3
    # Lines are deliverable if: approved, modified+accepted, or treat_anyway
    def _should_deliver(line):
        if getattr(line, "treat_anyway", False):
            return True
        status = getattr(line, "authorization_status", None)
        if status == "approved":
            return True
        if status == "modified" and getattr(line, "accepted_modification", False):
            return True
        return False

    deliverable_lines = [l for l in state.service_lines if _should_deliver(l)]
    if not deliverable_lines:
        state.care_abandoned = True

    if state.care_abandoned:
        state = run_phase4(state=state, audit_logger=audit_logger)
        return state

    state = run_phase3(
        state=state,
        provider_llm=provider_llm,
        payor_llm=payor_llm,
        provider_params=provider_params,
        payor_params=payor_params,
        audit_logger=audit_logger,
    )

    state = run_phase4(state=state, audit_logger=audit_logger)

    return state
