"""administrative friction metrics tracking"""
from __future__ import annotations

from pydantic import BaseModel


class FrictionMetrics(BaseModel):
    # phase 2: authorization
    phase2_turns: int = 0
    max_appeal_level_reached: int = 0

    # phase 2: final authorization outcomes
    total_lines_requested: int = 0
    lines_approved_phase2: int = 0
    lines_denied_phase2: int = 0
    lines_modified_phase2: int = 0

    # phase 3: claim adjudication
    phase3_turns: int = 0
    lines_delivered: int = 0
    lines_paid_phase3: int = 0
    lines_denied_phase3: int = 0

    # financial
    total_billed_amount: float = 0.0
    total_paid_amount: float = 0.0

    # rates
    authorization_denial_rate: float = 0.0
    claim_denial_rate: float = 0.0
    payment_ratio: float = 0.0

    # oversight effort proxies
    provider_review_tokens: int = 0
    provider_edit_ops: int = 0
    insurer_review_tokens: int = 0
    insurer_edit_ops: int = 0
