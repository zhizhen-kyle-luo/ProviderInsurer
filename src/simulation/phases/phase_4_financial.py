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
    # Final outcome is already recorded in state.authorization_request.authorization_status
    # Iteration counts tracked in audit_log
    # Appeal/pend metrics tracked in state flags (appeal_filed, claim_pended, etc.)
    # Nothing to calculate for now, just return state with all outcomes recorded
    return state
