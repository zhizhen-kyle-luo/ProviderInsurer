"""
phase 2: iterative utilization review workflow

handles all case types through unified workflow:
- level 0: initial_determination (automated/checklist review)
- level 1: internal_appeal (medical director review)
- level 2: independent_review (final clinical review, no pend)

Uses unified_review.py for core 3-level logic.
"""

from typing import Dict, Any, TYPE_CHECKING

from src.models.schemas import EncounterState
from src.utils.prompts import (
    create_unified_provider_request_prompt,
    create_unified_payor_review_prompt
)
from src.simulation.phases.unified_review import run_unified_multi_level_review

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def run_phase_2_utilization_review(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any]
) -> EncounterState:
    """
    unified phase 2: iterative utilization review workflow for all case types

    PHASE 2 = PRE-ADJUDICATION UTILIZATION REVIEW:
    - Timing: BEFORE or DURING care delivery
    - Record status: EVOLVING - provider can order tests, add documentation
    - Payor can: PEND (request more info), and provider can respond in real-time
    - Decision: whether to AUTHORIZE care to proceed (prospective PA / concurrent review)

    continues until: approved OR max iterations OR agent abandon

    stage semantics (0-indexed):
      - level 0: initial_determination (automated/checklist review)
      - level 1: internal_appeal (medical director review)
      - level 2: independent_review (final clinical review, no pend)
    """

    # Call unified review with Phase 2 prompts
    state = run_unified_multi_level_review(
        sim=sim,
        state=state,
        case=case,
        phase="phase_2_utilization_review",
        provider_prompt_fn=create_unified_provider_request_prompt,
        payor_prompt_fn=create_unified_payor_review_prompt,
        provider_prompt_kwargs={},  # Phase 2 provider prompt doesn't need extra kwargs
        payor_prompt_kwargs={},  # Phase 2 payor prompt doesn't need extra kwargs
        max_iterations=sim.max_iterations
    )

    return state
