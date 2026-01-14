from typing import Dict, Any
from src.models import EncounterState


def run_phase_4_financial(
    state: EncounterState,
    case: Dict[str, Any]
) -> EncounterState:
    """
    phase 4: record final outcome (barebone - no cost calculations)

    For AI arms race experiment, we care about:
    - Final outcome (approved/denied/abandoned)
    - Iteration counts
    - Friction metrics (appeals, pends)

    Cost modeling removed for now
    """
    # final outcomes already recorded in state.service_lines (authorization_status, adjudication_status)
    # iteration counts tracked in audit_log
    # appeal/pend metrics tracked in state flags (appeal_filed, claim_pended, etc.)
    return state
