"""
Prompts package - organized into modular files for clarity

This __init__.py re-exports all functions for backward compatibility
with existing code that imports from src.utils.prompts
"""

# Config and constants
from .config import (
    MAX_ITERATIONS,
    INTERNAL_REASONING,
    WORKFLOW_LEVELS,
    LEVEL_NAME_MAP,
    OVERSIGHT_GUIDANCE,
    PROVIDER_PARAM_DEFINITIONS,
    PAYOR_PARAM_DEFINITIONS,
    DEFAULT_PROVIDER_PARAMS,
    DEFAULT_PAYOR_PARAMS,
    PROVIDER_ACTIONS_GUIDE,
    PAYOR_ACTIONS_GUIDE,
    PROVIDER_RESPONSE_MATRIX,
    PROVIDER_REQUEST_TYPES,
    PROVIDER_ACTIONS,
    PAYOR_ACTIONS,
    REQUEST_TYPES,
)

# System prompts (provider and payor base context)
from .system_prompts import (
    create_provider_prompt,
    create_payor_prompt,
)

# Phase 2 prompts (pre-adjudication UR)
from .phase2_prompts import (
    create_unified_provider_request_prompt,
    create_treatment_decision_after_pa_denial_prompt,
    create_unified_payor_review_prompt,
)

# Phase 3 prompts (retrospective review / claims adjudication)
from .phase3_prompts import (
    create_phase3_claim_submission_decision_prompt,
    create_unified_phase3_provider_request_prompt,
    create_unified_phase3_payor_review_prompt,
)

# Public API
__all__ = [
    # Config
    "MAX_ITERATIONS",
    "INTERNAL_REASONING",
    "WORKFLOW_LEVELS",
    "LEVEL_NAME_MAP",
    "OVERSIGHT_GUIDANCE",
    "PROVIDER_PARAM_DEFINITIONS",
    "PAYOR_PARAM_DEFINITIONS",
    "DEFAULT_PROVIDER_PARAMS",
    "DEFAULT_PAYOR_PARAMS",
    # Action space
    "PROVIDER_ACTIONS_GUIDE",
    "PAYOR_ACTIONS_GUIDE",
    "PROVIDER_RESPONSE_MATRIX",
    "PROVIDER_REQUEST_TYPES",
    "PROVIDER_ACTIONS",
    "PAYOR_ACTIONS",
    "REQUEST_TYPES",
    # System prompts
    "create_provider_prompt",
    "create_payor_prompt",
    # Phase 2 prompts
    "create_unified_provider_request_prompt",
    "create_treatment_decision_after_pa_denial_prompt",
    "create_unified_payor_review_prompt",
    # Phase 3 prompts
    "create_phase3_claim_submission_decision_prompt",
    "create_unified_phase3_provider_request_prompt",
    "create_unified_phase3_payor_review_prompt",
]
