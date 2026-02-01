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
- line_number: int, sequential identifier (1, 2, 3...)
- request_type: diagnostic_test | treatment | level_of_care
- procedure_code: CPT (5 digits), HCPCS (letter+4), J-code (J+4), or NDC (11 digits)
- code_type: CPT | HCPCS | J-code | NDC (qualifier for procedure_code)
- service_name: human-readable name (e.g., "Infliximab", "MRI Abdomen")
- service_description: detailed description of service
- requested_quantity: int, number of units (infusions, days, visits)
- quantity_unit: days | visits | units | infusions
- charge_amount: float, billed amount in USD
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
        "charge_amount": <number>,
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
  ],
  "reviewer_type": "<UM Triage|Medical Director|IRE>",
  "level": <0|1|2>
}"""

# =============================================================================
# PHASE 2/3: Provider Action Schema
# =============================================================================

PROVIDER_ACTION_SCHEMA = """
SCHEMA (Provider Action):
- action: CONTINUE | APPEAL | RESUBMIT | ABANDON
  - CONTINUE: proceed without escalating review level
  - APPEAL: escalate denied/modified lines to next review level (disputes coverage decision)
  - RESUBMIT: withdraw current PA entirely, submit new/corrected request on next turn (resets to level 0)
  - ABANDON: stop pursuit entirely
- lines: array of per-line actions (required for CONTINUE and APPEAL)
  - line_number: int, which line this action applies to
  - intent: ONLY one of these two values:
      * PROVIDE_DOCS - for pending_info lines, you will provide requested documentation
      * ACCEPT_MODIFY - for modified lines, you accept the insurer's modification
  - to_level: int, target appeal level (required for APPEAL action only, omit for CONTINUE)
- abandon_mode: NO_TREAT (patient doesn't get service) | TREAT_ANYWAY (provider absorbs cost) | WRITE_OFF (Phase 3 only)
- resubmit_reason: text, explanation of why resubmitting (required for RESUBMIT action)
- reasoning: text, brief explanation of decision

CONTINUE rules:
- For each pending_info line: include {line_number, intent: "PROVIDE_DOCS"}
- For each modified line you accept: include {line_number, intent: "ACCEPT_MODIFY"}
- Approved lines need no entry (already terminal)
- Denied lines cannot use CONTINUE (use APPEAL or RESUBMIT instead)

RESUBMIT vs APPEAL:
- RESUBMIT: Provider-side errors (wrong codes, missing diagnoses) or want different services.
  NOT a formal appeal - withdraws current PA and starts fresh at level 0.
- APPEAL: Disagree with payor's coverage decision, want higher-level review.
  Same request, disputing the denial/modification.
"""

PROVIDER_ACTION_JSON = """{
  "action": "<CONTINUE|APPEAL|RESUBMIT|ABANDON>",
  "lines": [
    {"line_number": <int>, "intent": "<PROVIDE_DOCS|ACCEPT_MODIFY>", "to_level": <int or omit>}
  ],
  "abandon_mode": "<NO_TREAT|TREAT_ANYWAY|WRITE_OFF or omit>",
  "resubmit_reason": "<explanation if RESUBMIT>",
  "reasoning": "<brief explanation>"
}"""

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
- allowed_amount: float, contractual allowed amount in USD
- paid_amount: float, actual payment amount in USD
- adjustment_group_code: CO (Contractual) | PR (Patient Responsibility) | OA (Other Adjustment)
- adjustment_amount: float, amount adjusted
- requested_documents: list of strings (if pending_info)
"""

PHASE3_PAYOR_RESPONSE_JSON = """{
  "line_adjudications": [
    {
      "line_number": <number>,
      "adjudication_status": "<approved|modified|denied|pending_info>",
      "decision_reason": "<text>",
      "allowed_amount": <number>,
      "paid_amount": <number>,
      "adjustment_group_code": "<CO|PR|OA>",
      "adjustment_amount": <number>,
      "requested_documents": ["<doc1>", "<doc2>"]
    }
  ],
  "reviewer_type": "<MAC|QIC|ALJ>",
  "level": <0|1|2>
}"""
