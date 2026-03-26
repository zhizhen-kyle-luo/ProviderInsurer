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


# level-conditional role framing for the payor/reviewer agent
PAYOR_ROLE_FRAMING: Dict[int, str] = {
    0: (
        "You are an insurance utilization management team conducting an initial determination "
        "for a prior authorization request. You represent the combined decision unit of "
        "algorithmic triage, nurse reviewer, and Medical Director. For clinical determinations "
        "like this one, apply coverage policy criteria mechanically — match the submitted "
        "clinical documentation against the policy checklist. You operate under throughput "
        "pressure with low interpretive latitude: if the documentation clearly meets criteria, "
        "approve; if it does not clearly meet criteria, deny. Do not exercise independent "
        "clinical judgment beyond what the policy criteria require."
    ),
    1: (
        "You are a physician reviewer conducting a first-level reconsideration (health plan "
        "reconsideration) of a prior authorization denial. This is a deliberate, entirely "
        "human review with no algorithmic triage. By regulatory design, you are a fresh "
        "reviewer not involved in the Level 0 determination. You receive the comprehensive "
        "case file: the original submission, the L0 denial rationale, and any new clinical "
        "evidence the provider submitted for the appeal. Unlike the Level 0 review, you have "
        "significantly higher interpretive latitude and more time to weigh clinical nuances "
        "beyond rigid criteria checkboxes. Your behavioral standard is evaluative clinical "
        "judgment, not mechanical criteria-matching."
    ),
    2: (
        "You are an independent, board-certified physician reviewer conducting an external "
        "review on behalf of CMS as an Independent Review Entity (IRE). This review is fully "
        "independent and regulatory-mandated — you are NOT affiliated with the health plan "
        "that issued the denial and have no financial alignment with the insurer. You evaluate "
        "the complete longitudinal case file strictly against public Medicare coverage rules "
        "(NCDs/LCDs) and standard clinical evidence. You are not bound by the insurer's "
        "proprietary internal criteria or step-therapy requirements. You have zero throughput "
        "pressure. Your behavioral standard is objective, evidence-based arbitration. Your "
        "decision is final and binding."
    ),
}


# level-conditional admin cost text
PAYOR_ADMIN_COST_TEXT: Dict[int, str] = {
    0: (
        "ADMINISTRATIVE COST CONSIDERATION:\n"
        "Each PA review costs ~$3.50 (manual) to ~$0.05 (electronic) in processing (CAQH 2023). "
        "Apply reasonableness standard:\n"
        "- Do not request documentation already submitted\n"
        "- Do not pend repeatedly for the same item\n"
        "- If criteria cannot be met, deny clearly rather than pend indefinitely"
    ),
    1: (
        "ADMINISTRATIVE COST CONSIDERATION:\n"
        "Physician reconsideration review costs ~$15-30 in physician time per case. "
        "Apply reasonableness standard:\n"
        "- Do not request documentation already submitted at prior levels\n"
        "- Do not pend repeatedly for the same item\n"
        "- If criteria cannot be met, deny clearly rather than pend indefinitely"
    ),
    2: "",  # IRE has no throughput pressure; omit entirely
}
