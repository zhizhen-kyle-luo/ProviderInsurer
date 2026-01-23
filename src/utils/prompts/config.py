from __future__ import annotations

from typing import Any, Dict, Literal, Set


RequestType = Literal["diagnostic_test", "treatment", "level_of_care"]
PayorLineStatus = Literal["approved", "modified", "denied", "pending_info"]

ProviderBundleAction = Literal["CONTINUE", "APPEAL", "ABANDON"]
ProviderContinueIntent = Literal["PROVIDE_REQUESTED_DOCS", "ACCEPT_MODIFY", "RESUBMIT_AMENDED"]
AbandonMode = Literal["NO_TREAT", "TREAT_ANYWAY"]


VALID_REQUEST_TYPES: Set[str] = {"diagnostic_test", "treatment", "level_of_care"}
VALID_PAYOR_LINE_STATUSES: Set[str] = {"approved", "modified", "denied", "pending_info"}

VALID_PROVIDER_BUNDLE_ACTIONS: Set[str] = {"CONTINUE", "APPEAL", "ABANDON"}
VALID_PROVIDER_CONTINUE_INTENTS: Set[str] = {"PROVIDE_REQUESTED_DOCS", "ACCEPT_MODIFY", "RESUBMIT_AMENDED"}
VALID_ABANDON_MODES: Set[str] = {"NO_TREAT", "TREAT_ANYWAY"}


# simulation caps: code should raise if violated (no silent defaults)
MAX_ITERATIONS: int = 3
MAX_REQUEST_INFO_PER_LEVEL: int = 5 #was set to 2 for realism, now 5 to observe behavior

# optional experiment knob; you said you'd comment it out if not used
NOISE_PROBABILITY: float = 0.0


# review levels (0..2) and whether pending_info is allowed
WORKFLOW_LEVELS: Dict[int, Dict[str, Any]] = {
    0: {"name": "initial_review", "reviewer_type": "UM Triage", "can_pend": True},
    1: {"name": "reconsideration", "reviewer_type": "Medical Director", "can_pend": True},
    2: {"name": "independent_review", "reviewer_type": "IRE", "can_pend": False},
}

LEVEL_NAME_MAP: Dict[int, str] = {k: str(v["name"]) for k, v in WORKFLOW_LEVELS.items()}


# short guides used inside prompts (not long essays)
PAYOR_ACTIONS_GUIDE: str = (
    "Line statuses: approved | modified | denied | pending_info.\n"
    "- pending_info: missing info; list requested_documents\n"
    "- modified: approve with changes; set modification_type\n"
    "- denied: adverse; explain decision_reason\n"
)

PROVIDER_ACTIONS_GUIDE: str = (
    "Bundle actions: CONTINUE | APPEAL | ABANDON.\n"
    "- CONTINUE: proceed (e.g., provide docs, accept modify, resubmit amended)\n"
    "- APPEAL: escalate adverse lines to next level (max 2)\n"
    "- ABANDON: stop Phase 2 (NO_TREAT or TREAT_ANYWAY)\n"
)


# oversight config: budgets only; code enforces, prompts don't waste tokens saying so
OVERSIGHT_BUDGETS: Dict[str, Dict[str, Dict[str, int]]] = {
    "provider": {
        "low": {"review_expand_lines": 1, "max_patch_ops": 3, "max_paths_touched": 3},
        "medium": {"review_expand_lines": 2, "max_patch_ops": 8, "max_paths_touched": 6},
        "high": {"review_expand_lines": 999, "max_patch_ops": 50, "max_paths_touched": 30},
    },
    "payor": {
        "low": {"review_expand_lines": 1, "max_patch_ops": 3, "max_paths_touched": 3},
        "medium": {"review_expand_lines": 2, "max_patch_ops": 8, "max_paths_touched": 6},
        "high": {"review_expand_lines": 999, "max_patch_ops": 50, "max_paths_touched": 30},
    },
}

DEFAULT_PROVIDER_PARAMS: Dict[str, Any] = {"oversight_intensity": "medium"}
DEFAULT_PAYOR_PARAMS: Dict[str, Any] = {"oversight_intensity": "medium"}


OVERSIGHT_GUIDANCE: Dict[str, Dict[str, str]] = {
    "low": {"instruction": "minimal review; approve unless obvious error"},
    "medium": {"instruction": "standard review; check key fields for consistency"},
    "high": {"instruction": "thorough review; verify all clinical claims against evidence"},
}

OVERSIGHT_CONSTRAINTS: Dict[str, str] = {
    "provider": "focus on clinical accuracy and completeness",
    "payor": "focus on policy compliance and medical necessity criteria",
}
