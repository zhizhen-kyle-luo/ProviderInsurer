"""administrative friction metrics tracking"""
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel


class PolicyReference(BaseModel):
    """Reference to a policy used in the simulation."""
    policy_id: str
    issuer: str
    source: Optional[Dict[str, Any]] = None


class EnvironmentConfig(BaseModel):
    """Environment configuration for the simulation."""
    allow_synthesis: bool = True
    synthesis_model: Optional[str] = None


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
    lines_delivered: int = 0
    lines_paid_phase3: int = 0
    lines_denied_phase3: int = 0

    # policy references
    provider_policy: Optional[PolicyReference] = None
    payor_policy: Optional[PolicyReference] = None

    # environment
    environment_config: Optional[EnvironmentConfig] = None
