"""
Schema definitions for LLM prompts.
Single source of truth for field descriptions used in Phase 2/3 prompts.
Aligned with X12 278/837/835 transaction sets and ServiceLineRequest model.
"""

# =============================================================================
# PHASE 2: Provider Submission Schema (X12 278 Request)
# =============================================================================

PHASE2_PROVIDER_REQUEST_SCHEMA = """
SCHEMA (X12 278 Request):

REQUEST TYPES:
- diagnostic_test: Lab tests, imaging, pathology to establish/confirm diagnosis
- treatment: Therapeutic interventions (medications, procedures, surgeries)
- level_of_care: Intensity of care setting (inpatient, observation, SNF, home health)

DIAGNOSIS CODES (ICD-10):
Per X12 278, diagnosis codes are situational - include when known. For diagnostic_test requests
where final diagnosis is uncertain, use working diagnoses or symptom codes (ICD-10 R-codes).
For treatment and level_of_care, include the diagnosis justifying medical necessity.

FIELD DEFINITIONS:
- line_number: int, sequential identifier (1, 2, 3...)
- request_type: diagnostic_test | treatment | level_of_care
- procedure_code: CPT (5 digits), HCPCS (letter+4), J-code (J+4), or NDC (11 digits)
- code_type: CPT | HCPCS | J-code | NDC (qualifier for procedure_code)
- service_name: human-readable name (e.g., "Infliximab", "MRI Abdomen")
- service_description: detailed description of service
- requested_quantity: int, number of units (infusions, days, visits)
- quantity_unit: days | visits | units | infusions
- clinical_evidence: text justification with demographics, symptoms, labs, guideline citations
"""

PHASE2_PROVIDER_REQUEST_JSON = """{
  "insurer_request": {
    "diagnosis_codes": [{"icd10":"<code>","description":"<text>"}],
    "requested_services": [
      {
        "line_number": 1,
        "request_type": "<diagnostic_test|treatment|level_of_care>",
        "procedure_code": "<code>",
        "code_type": "<CPT|HCPCS|J-code|NDC>",
        "service_name": "<name>",
        "service_description": "<description>",
        "requested_quantity": <number>,
        "quantity_unit": "<days|visits|units|infusions>",
        "clinical_evidence": "<text>"
      }
    ],
    "clinical_notes": "<H&P narrative>"
  }
}"""

# =============================================================================
# PHASE 2: Payor Response Schema (X12 278 HCR Response)
# =============================================================================

PHASE2_PAYOR_RESPONSE_SCHEMA = """
SCHEMA (X12 278 HCR Response):
- line_number: int, must match line from insurer_request
- authorization_status: approved (X12 A1) | modified (A6) | denied (A3) | pending_info (A4)
- decision_reason: text explanation of approval rationale, denial reason, or info needed
- approved_quantity: int, quantity approved (may differ from requested if modified)
- authorization_number: string, auth ID if approved/modified (links to future 837 claim)
- modification_type: quantity_reduction | site_change | code_downgrade (required if modified)
- requested_documents: list of strings, docs needed (required if pending_info)
"""

PHASE2_PAYOR_RESPONSE_JSON = """{
  "line_adjudications": [
    {
      "line_number": <number>,
      "authorization_status": "<approved|modified|denied|pending_info>",
      "decision_reason": "<text>",
      "approved_quantity": <number>,
      "authorization_number": "<id>",
      "modification_type": "<quantity_reduction|site_change|code_downgrade>",
      "requested_documents": ["<doc1>", "<doc2>"]
    }
  ]
}"""

# =============================================================================
# PHASE 2/3: Provider Action Schema
# =============================================================================

PROVIDER_ACTION_SCHEMA = """
SCHEMA (Provider Action):
Provider decides action AFTER seeing payor's response. This is the strategic choice point.
Each non-approved line requires a decision. Approved lines are already terminal (no action needed).

TWO ACTION MODES:

1. RESUBMIT (bundle-level) - Withdraw entire PA, start fresh at level 0
   Use when YOUR submission had errors that caused denials:
   - Wrong procedure codes, missing diagnoses, insufficient documentation
   - Want to request DIFFERENT services than originally submitted
   Required: resubmit_reason
   NOT a formal appeal - payor treats it as a new request
   Strategic: Avoids burning appeal levels on fixable errors

2. LINE_ACTIONS (per-line) - Specify action for each non-approved line
   Each line gets its own action based on its status:

   For MODIFIED lines (payor approved with changes):
   - ACCEPT_MODIFY: Accept the modification, line becomes terminal, service will be delivered
   - APPEAL: Dispute the modification, escalate to next level (requires to_level)
   - ABANDON: Give up on this line (requires mode: NO_TREAT or TREAT_ANYWAY)

   For PENDING_INFO lines (payor needs more documentation):
   - PROVIDE_DOCS: Will provide requested documents in next submission's clinical_evidence
   - ABANDON: Give up on this line (requires mode: NO_TREAT or TREAT_ANYWAY)

   For DENIED lines (payor rejected):
   - APPEAL: Dispute the denial, escalate to next level (requires to_level, max 2)
   - ABANDON: Accept the denial (requires mode: NO_TREAT or TREAT_ANYWAY)

ABANDON modes (Phase 2):
- NO_TREAT: Patient does not receive service
- TREAT_ANYWAY: Deliver service anyway, provider absorbs cost

APPEAL levels:
- to_level must be current_level + 1
- Level 1 = Medical Director peer-to-peer review
- Level 2 = IRE (Independent Review Entity) - final, binding decision
- ~83% of appeals succeed, but takes 15-45 days

RESUBMIT only when denial was due to YOUR CORRECTABLE ERROR:
    - Wrong codes, typos, missing documentation YOU ACTUALLY HAVE
    - Resets to level 0, treated as new request
    - Futile if you cannot provide what was missing

APPEAL when:
    - Patient does not meet policy criteria that CANNOT change (e.g., step-therapy not tried)
    - Payor misapplied policy or ignored clinical evidence
    - Prior resubmission failed for the same reason
    - Escalates to higher review level

If facts cannot change, RESUBMIT will fail again. Use APPEAL to argue exception or ABANDON.
"""

PROVIDER_ACTION_JSON = """{
  "action": "RESUBMIT",
  "resubmit_reason": "<explanation of what you're correcting>",
  "reasoning": "<brief explanation>"
}

OR

{
  "action": "LINE_ACTIONS",
  "line_actions": [
    {"line_number": <int>, "action": "ACCEPT_MODIFY"},
    {"line_number": <int>, "action": "PROVIDE_DOCS"},
    {"line_number": <int>, "action": "APPEAL", "to_level": <1 or 2>},
    {"line_number": <int>, "action": "ABANDON", "mode": "<NO_TREAT|TREAT_ANYWAY>"}
  ],
  "reasoning": "<brief explanation>"
}

RULES:
- Approved lines: omit from line_actions (already terminal)
- Modified lines: ACCEPT_MODIFY | APPEAL (with to_level) | ABANDON (with mode)
- Pending_info lines: PROVIDE_DOCS | ABANDON (with mode)
- Denied lines: APPEAL (with to_level) | ABANDON (with mode)
- Every non-approved line MUST have an action in line_actions"""

# =============================================================================
# PHASE 3: Provider Claim Submission Schema (X12 837)
# =============================================================================

PHASE3_PROVIDER_CLAIM_SCHEMA = """
SCHEMA (X12 837 Claim):
- line_number: int, must match delivered service line
- procedure_code: same code used in authorization
- authorization_number: string, auth number from Phase 2 approval (REF*9F)
- clinical_documentation: text, documentation supporting medical necessity
"""

PHASE3_PROVIDER_CLAIM_JSON = """{
  "claim_submission": {
    "billed_lines": [
      {
        "line_number": <number>,
        "procedure_code": "<code>",
        "authorization_number": "<auth_num>",
        "clinical_documentation": "<text>"
      }
    ],
    "provider_notes": "<narrative>"
  }
}"""

# =============================================================================
# PHASE 3: Payor Adjudication Schema (X12 835 Remittance)
# =============================================================================

PHASE3_PAYOR_RESPONSE_SCHEMA = """
SCHEMA (X12 835 Remittance):
- line_number: int, must match line from claim_submission
- adjudication_status: approved | modified | denied | pending_info
- decision_reason: text explanation of payment decision
- adjustment_group_code: CO (Contractual) | PR (Patient Responsibility) | OA (Other Adjustment)
- requested_documents: list of strings (if pending_info)
"""

PHASE3_PAYOR_RESPONSE_JSON = """{
  "line_adjudications": [
    {
      "line_number": <number>,
      "adjudication_status": "<approved|modified|denied|pending_info>",
      "decision_reason": "<text>",
      "adjustment_group_code": "<CO|PR|OA>",
      "requested_documents": ["<doc1>", "<doc2>"]
    }
  ]
}"""
