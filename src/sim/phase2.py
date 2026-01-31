from __future__ import annotations
from typing import Any, Dict, Optional
from src.models.state import EncounterState
from src.sim.engine import run as run_engine
from src.sim.phase2_adapter import Phase2Adapter
from src.utils.audit_logger import AuditLogger
from src.utils.environment import Environment

def run_phase2(
    *,
    state: EncounterState,
    provider_llm,
    payor_llm,
    provider_params: Optional[Dict[str, Any]] = None,
    payor_params: Optional[Dict[str, Any]] = None,
    max_turns: int = 3,
    audit_logger: Optional[AuditLogger] = None,
    seed: Optional[int] = None,
    environment: Optional[Environment] = None,
) -> EncounterState:
    if provider_params is not None:
        state.provider_params = provider_params
    if payor_params is not None:
        state.payor_params = payor_params

    if environment is None:
        environment = Environment(
            synthesis_llm=provider_llm,
            allow_synthesis=True,
            audit_logger=audit_logger,
        )
    else:
        if getattr(environment, "audit_logger", None) is None:
            environment.audit_logger = audit_logger
        if getattr(environment, "allow_synthesis", False) and getattr(environment, "synthesis_llm", None) is None:
            environment.synthesis_llm = provider_llm

    adapter = Phase2Adapter(
        provider_llm=provider_llm,
        payor_llm=payor_llm,
        provider_params=provider_params,
        payor_params=payor_params,
        environment=environment,
        audit_logger=audit_logger,
    )

    return run_engine(
        state=state,
        adapter=adapter,
        max_turns=max_turns,
        audit_logger=audit_logger,
        seed=seed,
    )
