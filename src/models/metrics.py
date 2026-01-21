"""administrative friction metrics tracking"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel


class FrictionMetrics(BaseModel):
    # phase 2: authorization
    phase2_turns: int = 0
    provider_bundle_actions: int = 0
    insurer_line_decisions_total: int = 0
    insurer_approve: int = 0
    insurer_deny: int = 0
    insurer_pend: int = 0
    insurer_modify: int = 0
    pend_rounds_total: int = 0
    amended_resubmissions: int = 0
    appeal_level1_lines: int = 0
    appeal_level2_lines: int = 0
    max_appeal_level_reached: int = 0

    # phase 2: final authorization outcomes
    total_lines_requested: int = 0
    lines_approved_phase2: int = 0
    lines_denied_phase2: int = 0
    lines_modified_phase2: int = 0
    lines_pending_final_phase2: int = 0

    # phase 3: claim adjudication
    phase3_turns: int = 0
    lines_delivered: int = 0
    lines_claimed: int = 0
    lines_paid_phase3: int = 0
    lines_denied_phase3: int = 0
    lines_modified_phase3: int = 0

    # financial
    total_requested_amount: float = 0.0
    total_authorized_amount: float = 0.0
    total_billed_amount: float = 0.0
    total_allowed_amount: float = 0.0
    total_paid_amount: float = 0.0
    total_adjustment_amount: float = 0.0

    # rates
    authorization_denial_rate: float = 0.0
    claim_denial_rate: float = 0.0
    payment_ratio: float = 0.0

    # oversight effort
    provider_review_tokens: int = 0
    provider_edit_ops: int = 0
    insurer_review_tokens: int = 0
    insurer_edit_ops: int = 0

    # termination
    phase2_terminated_by: Optional[Literal["ALL_LINES_TERMINAL", "ABANDON_NO_TREAT", "ABANDON_TREAT_ANYWAY", "MAX_TURNS"]] = None
    phase3_terminated_by: Optional[Literal["ALL_LINES_TERMINAL", "ABANDON_WRITE_OFF", "MAX_TURNS"]] = None
    provider_abandoned: bool = False
