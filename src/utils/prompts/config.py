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

# empty by design - internal only, not sent to insurer
INTERNAL_REASONING = ""

PROVIDER_ACTIONS_GUIDE = """
PROVIDER ACTION SPACE (choose one each turn):

1. CONTINUE - strengthen record at current review level without escalating
   When to use: after REQUEST_INFO (pend) OR after APPROVE of diagnostic test
   Strategic meaning: answer payer's question OR use new test result to request treatment
   Examples:
   - After REQUEST_INFO: provide missing vitals, lab values, imaging reports, guideline citations
   - After diagnostic APPROVE: use test result (e.g., "negative TB") to now request treatment (e.g., Infliximab)
   - Order additional/alternative tests (ABG instead of chest X-ray, MRI instead of CT)
   - Add objective measurements (sequential vital signs, quantified severity scores)
   - Submit peer-reviewed literature supporting medical necessity

2. APPEAL - escalate to next review authority (changes who reviews)
   When to use: after DENY or DOWNGRADE
   Strategic meaning: challenge adverse determination by triggering formal reconsideration
   Examples:
   - Level 0→1: request plan medical director reconsideration after triage denial
   - Level 1→2: automatic forward to Independent Review Entity (IRE) per 42 CFR §422.592
   - After DOWNGRADE: appeal observation→inpatient or home infusion→hospital infusion

3. ABANDON - exit dispute, accept alternative outcome
   When to use: cost exceeds expected recovery, patient urgency, or low reversal probability
   Strategic meaning: stop fighting, accept lower reimbursement or patient self-pay
   Examples:
   - Accept observation status instead of continuing inpatient fight
   - Accept home infusion instead of hospital infusion (after DOWNGRADE)
   - Patient proceeds with treatment and pays out-of-pocket
   - Defer elective procedure to avoid financial risk
"""

PAYOR_ACTIONS_GUIDE = """
PAYOR ACTION SPACE (choose one each turn):

1. APPROVE - authorize coverage/service as requested (X12 278: A1)
   When to use: medical necessity criteria met, documentation complete
   Examples: approve inpatient status, approve medication, approve diagnostic test
   Note: can include restrictions like approved for certain quantity limits

2. DOWNGRADE - approve alternative/lower level of service (X12 278: A6 Modified)
   When to use: medical necessity not met for requested level, but lower level is appropriate
   Examples:
   - Approve observation instead of requested inpatient (classic grey zone)
   - Approve home infusion instead of hospital infusion
   - Approve outpatient procedure instead of inpatient admission
   Note: this is NOT a denial - provider gets authorization, just not what they wanted

3. DENY - adverse determination without authorization (X12 278: A3 Not Certified)
   When to use: medical necessity not met, step therapy incomplete, documentation insufficient
   Examples: deny for not meeting policy criteria, deny for incomplete step therapy, deny as experimental/investigational
   CMS 2026 rule: must provide specific denial reason

4. REQUEST_INFO - pend decision pending additional documentation (X12 278: A2 partial approval, A4 Pended)
   When to use: cannot adjudicate with current documentation, need specific clinical data
   Examples: request vital signs from admission, request lab values (troponin, BNP, lactate), request imaging reports, request medication administration record (MAR)
   Note: NOT available at Level 2 (independent review must decide on submitted record per 42 CFR §422.592)
"""

# Strategic logic table: what provider actions are valid after each payor decision
PROVIDER_RESPONSE_MATRIX = """
STRATEGIC ACTION MATRIX (what provider can do after each payor decision):

Payor Decision      | Request Type           | Valid Provider Actions | Strategic Logic
--------------------|------------------------|------------------------|------------------
APPROVE             | TREATMENT              | (None) - SUCCESS       | Terminal win. Treatment authorized. Simulation ends.
APPROVE             | DIAGNOSTIC             | CONTINUE               | Information gain. Got test result. Use it to request treatment.
APPROVE             | LEVEL_OF_CARE          | (None) - SUCCESS       | Terminal win. Got inpatient/site you wanted. Simulation ends.
DOWNGRADE           | LEVEL_OF_CARE          | APPEAL, ABANDON        | Grey zone choice. APPEAL=fight for higher reimbursement. ABANDON=accept lower status.
REQUEST_INFO (pend) | ANY                    | CONTINUE, ABANDON      | Open door. CONTINUE=answer question. ABANDON=give up. (Cannot APPEAL a pend)
DENY                | ANY                    | APPEAL, ABANDON        | Closed door. APPEAL=escalate to next authority. ABANDON=accept loss.
"""

PROVIDER_REQUEST_TYPES = """
REQUEST TYPES (provider must specify in each request):

1. TREATMENT - medication, procedure, or therapy request
   Examples: Infliximab infusion, surgical procedure, radiation therapy

2. DIAGNOSTIC - test or imaging to gather clinical information
   Examples: MRI, CT scan, lab panel, biopsy

3. LEVEL_OF_CARE - inpatient vs observation, hospital vs home infusion, ICU vs. Floor, or Hospital vs. SNF
   Examples: inpatient admission vs observation status, hospital infusion vs home infusion
"""

VALID_PROVIDER_ACTIONS = {
    "continue",
    "appeal",
    "abandon"
}

# canonical payor action values (lowercase)
VALID_PAYOR_ACTIONS = {
    "approved",
    "downgrade",
    "denied",
    "pending_info"
}

# canonical request type values (lowercase)
VALID_REQUEST_TYPES = {
    "treatment",
    "diagnostic_test",
    "level_of_care"
}

# canonical treatment decision values (post-PA-denial decision)
VALID_TREATMENT_DECISIONS = {
    "treat_anyway",  # provide care despite denial
    "no_treat"       # do not provide care
}

WORKFLOW_LEVELS = {
    0: {
        "name": "initial_determination",
        "role_label": "UM Triage Reviewer (Nurse/Algorithm) - Organization Determination (42 CFR §422.566)",
        "can_pend": True,
        "terminal": False,
        "independent": False,
        "copilot_active": True,
        "review_style": "checklist-driven, request info for missing required fields",
        "description": "Initial UM review. Prioritize REQUEST_INFO when required fields are missing. Be checklist-driven. Deny if clear policy mismatch."
    },
    1: {
        "name": "internal_reconsideration",
        "role_label": "Medical Director (Plan Reconsideration) - Plan Reconsideration (42 CFR §422.582)",
        "can_pend": True,
        "terminal": False,
        "independent": False,
        "copilot_active": True,
        "review_style": "clinical interpretation, fresh eyes, less pend-prone",
        "description": "Internal reconsideration by higher authority. Allow more clinical interpretation. Less likely to REQUEST_INFO if enough evidence exists. Fresh reviewer semantics."
    },
    2: {
        "name": "independent_review",
        "role_label": "Independent Review Entity (IRE) - IRE Review (42 CFR §422.592)",
        "can_pend": False,
        "terminal": True,
        "independent": True,
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
}

DEFAULT_PAYOR_PARAMS = {
    'oversight_intensity': 'low' 
}

OVERSIGHT_GUIDANCE = {
    'low': {
        'instruction': 'skim draft quickly, only fix obvious errors. if draft is reasonable, approve as-is.',
        'typical_behavior': 'most drafts approved with no changes or minor fixes only'
    },
    'medium': {
        'instruction': 'careful review, check key facts against evidence. fix clear errors, add missing critical items.',
        'typical_behavior': 'some drafts approved as-is, others get moderate edits'
    },
    'high': {
        'instruction': 'thorough line-by-line review, verify all claims against evidence. ensure complete accuracy.',
        'typical_behavior': 'most drafts get significant edits, verify all facts'
    }
}


PROVIDER_PARAM_DEFINITIONS = {
    'oversight_intensity': {
        'low': 'minimal human review of AI drafts, accept with minor tweaks only',
        'medium': 'standard review cycle, can fix contradictions and add missing evidence',
        'high': 'thorough multi-pass review, extensive editing allowed, verify all claims against evidence'
    }
}

PAYOR_PARAM_DEFINITIONS = {
    'oversight_intensity': {
        'low': 'minimal human review of AI decisions, automated processing with rare overrides',
        'medium': 'standard review cycle, medical director spot-checks AI decisions',
        'high': 'thorough multi-pass review, extensive human verification of all AI recommendations'
    }
}
