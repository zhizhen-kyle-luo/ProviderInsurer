"""administrative friction metrics tracking"""
from __future__ import annotations

from pydantic import BaseModel


class FrictionMetrics(BaseModel):
    # phase 2: authorization workflow
    phase2_turns: int = 0
    phase2_appeals: int = 0
    phase2_pends: int = 0
    max_appeal_level_reached: int = 0

    # phase 2: line outcomes
    total_lines_requested: int = 0
    lines_approved_phase2: int = 0
    lines_denied_phase2: int = 0
    lines_modified_phase2: int = 0
    lines_modified_accepted: int = 0

    # phase 3: claims workflow
    phase3_turns: int = 0
    phase3_appeals: int = 0
    phase3_pends: int = 0

    # phase 3: line outcomes
    lines_delivered: int = 0
    lines_paid_phase3: int = 0
    lines_denied_phase3: int = 0

