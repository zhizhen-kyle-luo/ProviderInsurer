"""administrative friction metrics tracking"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel


class FrictionMetrics(BaseModel):
    #Phase 2 workflow volume
    phase2_turns: int = 0
    provider_bundle_actions: int = 0  # CONTINUE/APPEAL/ABANDON count

    #Phase 2 insurer line outcomes (count decisions returned)
    insurer_line_decisions_total: int = 0
    insurer_approve: int = 0
    insurer_deny: int = 0
    insurer_pend: int = 0
    insurer_modify: int = 0

    #Phase 2 escalation / cycles
    pend_rounds_total: int = 0
    amended_resubmissions: int = 0
    appeal_level1_lines: int = 0
    appeal_level2_lines: int = 0
    max_appeal_level_reached: int = 0  # 0/1/2

    # Oversight effort (orchestrator computed, not LLM self-report)
    provider_review_tokens: int = 0
    provider_edit_ops: int = 0
    insurer_review_tokens: int = 0
    insurer_edit_ops: int = 0

    # --- Termination (optional but useful)
    terminated_by: Optional[Literal["ALL_LINES_TERMINAL", "ABANDON_NO_TREAT", "ABANDON_TREAT_ANYWAY", "MAX_TURNS"]] = None
