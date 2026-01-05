"""
Prompt Configuration Constants and Workflow Definitions

Shared configuration for all prompts:
- WORKFLOW_LEVELS: 3-level review structure (initial → reconsideration → independent)
- Behavioral parameters for provider and payor agents
- Oversight budgets for human review effort
"""
MAX_ITERATIONS = 3
NOISE_PROBABILITY = 0
MAX_REQUEST_INFO_PER_LEVEL = 2

# Internal reasoning for provider documentation (empty by design - internal only, not sent to insurer)
INTERNAL_REASONING = ""
PROVIDER_ACTIONS = ["CONTINUE", "APPEAL", "ABANDON"]
PAYOR_ACTIONS = ["APPROVE", "DENY", "REQUEST_INFO"]

# Level definitions for 3-level Medicare Advantage-inspired workflow (0-indexed)
# Level 0: UM triage / checklist-driven initial determination
# Level 1: internal reconsideration by higher authority (medical director-like)
# Level 2: independent external review (IRE/IRO), terminal, no internal notes access

WORKFLOW_LEVELS = {
    0: {
        "name": "initial_determination",
        "role": "triage",
        "role_label": "UM Triage Reviewer (Nurse/Algorithm) - Organization Determination (42 CFR §422.566)",
        "can_pend": True,
        "terminal": False,
        "independent": False,
        "sees_internal_notes": True,
        "copilot_active": True,
        "review_style": "checklist-driven, request info for missing required fields",
        "description": "Initial UM review. Prioritize REQUEST_INFO when required fields are missing. Be checklist-driven. Deny if clear policy mismatch."
    },
    1: {
        "name": "internal_reconsideration",
        "role": "reconsideration",
        "role_label": "Medical Director (Plan Reconsideration) - Plan Reconsideration (42 CFR §422.582)",
        "can_pend": True,
        "terminal": False,
        "independent": False,
        "sees_internal_notes": True,
        "copilot_active": True,
        "review_style": "clinical interpretation, fresh eyes, less pend-prone",
        "description": "Internal reconsideration by higher authority. Allow more clinical interpretation. Less likely to REQUEST_INFO if enough evidence exists. Fresh reviewer semantics."
    },
    2: {
        "name": "independent_review",
        "role": "independent",
        "role_label": "Independent Review Entity (IRE) - IRE Review (42 CFR §422.592)",
        "can_pend": False,
        "terminal": True,
        "independent": True,
        "sees_internal_notes": False,
        "copilot_active": False,
        "review_style": "record-based binding decision, cite criteria explicitly",
        "description": "Independent external review. Decide based on submitted record only. Cite criteria. No REQUEST_INFO allowed. Produces binding final disposition."
    }
}

# Mapping from stage names to level numbers (0-indexed)
LEVEL_NAME_MAP = {
    "initial_determination": 0,
    "internal_appeal": 1,
    "internal_reconsideration": 1,
    "independent_review": 2
}

DEFAULT_PROVIDER_PARAMS = {
    'oversight_intensity': 'medium',
    'authorization_aggressiveness': 'medium',
}

DEFAULT_PAYOR_PARAMS = {
    'oversight_intensity': 'low' 
}

OVERSIGHT_BUDGETS = {
    'low': {
        'max_edit_passes': 1,
        'max_tokens_changed': 50,
        'max_evidence_checks': 1
    },
    'medium': {
        'max_edit_passes': 2,
        'max_tokens_changed': 300,
        'max_evidence_checks': 3
    },
    'high': {
        'max_edit_passes': 2,
        'max_tokens_changed': 600,
        'max_evidence_checks': 6
    }
}


PROVIDER_PARAM_DEFINITIONS = {
    'oversight_intensity': {
        'low': 'minimal human review of AI drafts, accept with minor tweaks only',
        'medium': 'standard review cycle, can fix contradictions and add missing evidence',
        'high': 'thorough multi-pass review, extensive editing allowed, verify all claims against evidence'
    },
    'authorization_aggressiveness': {
        'low': 'risk-averse, prioritize administrative efficiency; abandon early when approval/payment uncertain; avoid prolonged fights',
        'medium': 'balanced approach; pursue authorization when clinically warranted; appeal denials if evidence is strong',
        'high': 'willing to fight for patient access; persist through appeals despite uncertainty; prioritize clinical need over administrative burden'
    }
}

PAYOR_PARAM_DEFINITIONS = {
    'oversight_intensity': {
        'low': 'minimal human review of AI decisions, automated processing with rare overrides',
        'medium': 'standard review cycle, medical director spot-checks AI decisions',
        'high': 'thorough multi-pass review, extensive human verification of all AI recommendations'
    }
}