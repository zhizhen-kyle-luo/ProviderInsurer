from __future__ import annotations

from typing import Any, Dict, Literal, Set


RequestType = Literal["diagnostic_test", "treatment", "level_of_care"]
PayorLineStatus = Literal["approved", "modified", "denied", "pending_info"]

# Provider action types (top-level)
ProviderActionType = Literal["RESUBMIT", "LINE_ACTIONS"]

# Per-line actions (within LINE_ACTIONS)
ProviderLineAction = Literal["ACCEPT_MODIFY", "PROVIDE_DOCS", "APPEAL", "ABANDON"]

# ABANDON modes by phase
AbandonModePhase2 = Literal["NO_TREAT", "TREAT_ANYWAY"]
AbandonModePhase3 = Literal["WRITE_OFF"]


VALID_REQUEST_TYPES: Set[str] = {"diagnostic_test", "treatment", "level_of_care"}
VALID_PAYOR_LINE_STATUSES: Set[str] = {"approved", "modified", "denied", "pending_info"}

VALID_PROVIDER_ACTION_TYPES: Set[str] = {"RESUBMIT", "LINE_ACTIONS"}
VALID_PROVIDER_LINE_ACTIONS: Set[str] = {"ACCEPT_MODIFY", "PROVIDE_DOCS", "APPEAL", "ABANDON"}
VALID_ABANDON_MODES_PHASE2: Set[str] = {"NO_TREAT", "TREAT_ANYWAY"}
VALID_ABANDON_MODES_PHASE3: Set[str] = {"WRITE_OFF"}


# simulation caps: code should raise if violated (no silent defaults)
MAX_TURNS_SAFETY_LIMIT: int = 15  # fallback to avoid infinite loops; agents don't know about this
MAX_REQUEST_INFO_PER_LEVEL: int = 5  # was set to 2 for realism, now 5 to observe behavior; avoid inf loop as well

# optional experiment knob; you said you'd comment it out if not used
NOISE_PROBABILITY: float = 0.0


# review levels (0..2) and whether pending_info is allowed
WORKFLOW_LEVELS: Dict[int, Dict[str, Any]] = {
    0: {"name": "initial_review", "reviewer_type": "UM Triage", "can_pend": True},
    1: {"name": "reconsideration", "reviewer_type": "Medical Director", "can_pend": True},
    2: {"name": "independent_review", "reviewer_type": "IRE", "can_pend": False},
}

LEVEL_NAME_MAP: Dict[int, str] = {k: str(v["name"]) for k, v in WORKFLOW_LEVELS.items()}


# strategy modes for game-theoretic experiment
VALID_STRATEGY_MODES: Set[str] = {"cooperate", "defect", "default"}

PROVIDER_STRATEGY_GUIDANCE: Dict[str, str] = {
    "cooperate": (
        "In ambiguous/gray-zone situations, choose the minimum clinically defensible "
        "set of requested services and the lowest reasonable intensity/level-of-care "
        "that still supports timely, appropriate treatment. Avoid adding extra line items "
        "or upgrading level-of-care unless clearly required by the case facts and policyor for better patient outcome ."
    ),
    "defect": (
        "In ambiguous/gray-zone situations, choose the maximum plausibly defensible "
        "set of requested services and the highest plausible intensity/level-of-care "
        "supported by the case facts/policy, to maximize approval/payment odds and reduce "
        "risk of denial. You may include additional supportive line items if they are "
        "remotely justifiable from provided facts; do not fabricate facts."
    ),
    "default": "",
}

PAYOR_STRATEGY_GUIDANCE: Dict[str, str] = {
    "cooperate": (
        "In ambiguous/gray-zone situations, apply policy in a good-faith, access-preserving way. "
        "If the request plausibly satisfies the policy, approve. If it is close but missing a small, "
        "specific piece of information, request narrowly targeted additional information (when permitted) "
        "and then reach a terminal decision. Prefer approve over deny when policy interpretation is "
        "genuinely ambiguous."
    ),
    "defect": (
        "In ambiguous/gray-zone situations, apply policy in a strict, cost-containment way. "
        "If the request is not clearly supported by explicit policy criteria and documentation, "
        "choose deny or modify/downgrade. When permitted, demand stricter documentation and interpret "
        "ambiguity against approval. Prefer modify/downgrade or deny over approve when evidence is borderline."
    ),
    "default": "",
}
