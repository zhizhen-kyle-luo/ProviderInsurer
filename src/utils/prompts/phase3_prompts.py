"""
Phase 3 Prompts: Retrospective Review / Claims Adjudication (Post-Service)

These prompts handle claim review after care is completed.
Record status: FIXED (clinical events already happened, cannot order new tests)
Insurer can: PEND only for existing documentation clarification, not new clinical actions
"""

from .config import (
    MAX_ITERATIONS,
    WORKFLOW_LEVELS,
    LEVEL_NAME_MAP,
)


def create_phase3_claim_submission_decision_prompt(
    state,
    pa_status: str,
    denial_reason: str,
):
    """Prompt for provider decision to submit a claim after PA denial."""
    return f"""PHASE 3: CLAIM SUBMISSION DECISION

SITUATION: Your prior authorization (Phase 2) was DENIED, but the patient still received care under your decision.
You must decide: Submit a claim for payment, or skip claim submission?

PHASE 2 AUTHORIZATION STATUS:
- Status: {pa_status}
- Denial Reason: {denial_reason}
- Service: {state.authorization_request.service_name if state.authorization_request and state.authorization_request.service_name else 'N/A'}

CLINICAL CONTEXT:
- Patient Age: {state.admission.patient_demographics.age}
- Chief Complaint: {state.clinical_presentation.chief_complaint}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}

TWO DECISIONS:
1. submit_claim: Submit claim for payment despite PA denial. This will enter the claims adjudication process (appeals, documentation submission, etc.)
2. skip: Do not submit claim. Write off the cost. No further administrative effort.

TASK: Decide whether to submit a claim for payment.

RESPONSE FORMAT (JSON):
{{
    "decision": "submit_claim" or "skip",
    "rationale": "<explain your reasoning>"
}}

Consider your clinical and documentation constraints in your decision."""


def create_unified_phase3_provider_request_prompt(
    state, case, iteration, prior_iterations, stage=None,
    service_request=None, cost_ref=None, phase_2_evidence=None,
    case_type="specialty_medication", coding_options=None
):
    """
    Phase 3 unified provider prompt: retrospective review (post-service)

    KEY OPERATIONAL DIFFERENCE FROM PHASE 2:
    - Record is FIXED: clinical events already happened, cannot order new tests
    - Can only clarify/supplement EXISTING documentation
    - Decision sought: PAYMENT for services already rendered
    - Appeals focus on: documentation completeness, not clinical necessity

    stage semantics (same 3-level structure as Phase 2):
    - initial_determination: standard claim submission with documentation
    - internal_appeal: address claim denial with additional documentation
    - independent_review: final appeal packet with maximum documentation clarity
    """
    import json

    def format_currency(value: object) -> str:
        if isinstance(value, (int, float)):
            return f"${value:.2f}"
        if value is None:
            return "N/A"
        return str(value)

    # build line-level claim status summary (provider memory of what was approved/denied)
    claim_lines_summary = ""
    if state.claim_lines:
        level_names = {0: 'Initial', 1: 'Internal Appeal', 2: 'IRE'}
        claim_lines_summary = "\nCLAIM LINE STATUS (your submitted lines and payor decisions):\n"
        for line in state.claim_lines:
            claim_lines_summary += f"\nLine {line.line_number}: {line.procedure_code} - {line.service_description}\n"
            claim_lines_summary += f"  Billed: {format_currency(line.billed_amount)} (qty: {line.quantity})\n"

            if line.adjudication_status:
                claim_lines_summary += f"  Status: {line.adjudication_status.upper()}\n"
                if line.adjudication_status in ["approved", "partial"]:
                    claim_lines_summary += f"  Paid: {format_currency(line.paid_amount)}\n"
                elif line.adjudication_status == "denied":
                    claim_lines_summary += f"  Denial Reason: {line.adjustment_reason}\n"

            level_name = level_names.get(line.current_review_level, f'Level {line.current_review_level}')
            claim_lines_summary += f"  Review Level: L{line.current_review_level} ({level_name})\n"
            claim_lines_summary += f"  Your Action: {line.provider_action or 'PENDING DECISION'}\n"

        claim_lines_summary += "\n"

    # format prior iterations for context
    prior_context = ""
    if prior_iterations:
        prior_context = "PRIOR CLAIM ITERATIONS:\n"
        for i, iter_data in enumerate(prior_iterations, 1):
            prior_context += f"\nIteration {i}:\n"
            prior_context += f"  Your submission: {iter_data.get('provider_request_type', 'claim')}\n"
            prior_context += f"  Payor decision: {iter_data.get('payor_decision', 'unknown')}\n"
            if iter_data.get('payor_denial_reason'):
                prior_context += f"  Denial/pend reason: {iter_data['payor_denial_reason']}\n"

    # stage-specific provider instructions
    stage_instruction = ""
    if stage == "initial_determination":
        stage_instruction = "ROUND 1 - INITIAL CLAIM SUBMISSION: Submit your claim with complete documentation of services rendered.\n"
    elif stage == "internal_appeal":
        stage_instruction = "ROUND 2 - INTERNAL APPEAL: You are appealing a claim denial. Provide additional EXISTING documentation that addresses the specific denial reason. You CANNOT change clinical facts - only clarify/supplement documentation.\n"
    elif stage == "independent_review":
        stage_instruction = "ROUND 3 - FINAL INDEPENDENT REVIEW: This is your final appeal opportunity. Submit all available documentation that supports payment for services already rendered. Ensure maximum clarity and completeness.\n"

    # build clinical documentation from Phase 2
    clinical_doc_parts = []
    if phase_2_evidence and phase_2_evidence.get('test_results'):
        clinical_doc_parts.append("DIAGNOSTIC WORKUP (Phase 2):")
        for test_name, test_data in phase_2_evidence['test_results'].items():
            if isinstance(test_data, dict):
                finding = test_data.get('finding', 'completed')
            else:
                finding = test_data
            clinical_doc_parts.append(f"- {test_name}: {finding}")
        clinical_doc_parts.append("")

    if phase_2_evidence and phase_2_evidence.get('approved_request'):
        approved_req = phase_2_evidence['approved_request']
        req_details = approved_req.get('request_details', {})
        if req_details.get('treatment_justification'):
            clinical_doc_parts.append(f"TREATMENT JUSTIFICATION (Phase 2): {req_details['treatment_justification']}")
        if req_details.get('clinical_evidence'):
            clinical_doc_parts.append(f"CLINICAL EVIDENCE (Phase 2): {req_details['clinical_evidence']}")
        clinical_doc_parts.append("")

    combined_clinical_doc = "\n".join(clinical_doc_parts) if clinical_doc_parts else "No additional documentation"

    # build service details
    if service_request:
        from src.models.schemas import CaseType
        if case_type == CaseType.SPECIALTY_MEDICATION:
            service_details = f"""SERVICE DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage Administered: {service_request.get('dosage')}
- Route: {service_request.get('route', 'N/A')}
- Frequency: {service_request.get('frequency', 'N/A')}"""
        else:
            service_name = service_request.get('service_name', service_request.get('treatment_name', service_request.get('procedure_name', 'procedure')))
            service_details = f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}
- Clinical Indication: {service_request.get('clinical_indication', service_request.get('treatment_justification', 'N/A'))}"""
    else:
        service_details = "SERVICE DELIVERED: (service details not provided)"

    # build coding & billing section
    if coding_options and len(coding_options) > 0:
        coding_section_parts = ["CODING & BILLING OPTIONS:"]
        coding_section_parts.append("You must select ONE diagnosis code based on clinical documentation:")
        coding_section_parts.append("")
        for i, option in enumerate(coding_options, 1):
            coding_section_parts.append(f"OPTION {i}: {option.get('icd10', 'N/A')} - {option.get('diagnosis', 'Unknown')}")
            coding_section_parts.append(f"  - Payment: ${option.get('payment', 0):,.2f}")
            coding_section_parts.append(f"  - DRG: {option.get('drg_code', 'N/A')}")
            coding_section_parts.append("")
        coding_section = "\n".join(coding_section_parts)
    else:
        if cost_ref:
            from src.models.schemas import CaseType
            if case_type == CaseType.SPECIALTY_MEDICATION:
                total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
                coding_section = f"""BILLING INFORMATION:
- Drug Acquisition Cost: ${cost_ref.get('drug_acquisition_cost', 7800):.2f}
- Administration Fee: ${cost_ref.get('administration_fee', 150):.2f}
- Total Amount Billed: ${total_billed:.2f}"""
            else:
                total_billed = cost_ref.get('procedure_cost', 7800)
                coding_section = f"BILLING INFORMATION:\n- Procedure Cost: ${total_billed:.2f}"
        else:
            coding_section = "BILLING INFORMATION: (billing details not provided)"

    provider_behavior_section = ""

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS} - PHASE 3: RETROSPECTIVE REVIEW (POST-SERVICE)

{stage_instruction}{provider_behavior_section}
CRITICAL OPERATIONAL CONTEXT - PHASE 3:
- Timing: AFTER care has been completed
- Record status: FIXED - clinical events already happened
- You CANNOT order new tests or change clinical facts
- You CAN ONLY: clarify existing documentation, submit additional existing records
- Decision sought: PAYMENT for services already rendered
- Your goal: Demonstrate that documentation supports reimbursement
- If Phase 2 approved the service, assume it WAS delivered as authorized. Submit a payable, itemized claim.

{prior_context}{claim_lines_summary}
PATIENT INFORMATION:
- Age: {state.admission.patient_demographics.age}
- Sex: {state.admission.patient_demographics.sex}
- Chief Complaint: {state.clinical_presentation.chief_complaint}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}
- Current Diagnoses: {', '.join(state.admission.preliminary_diagnoses)}

{service_details}

PHASE 2 COVERAGE/UTILIZATION REVIEW DECISION:
- Status: {state.authorization_request.authorization_status if state.authorization_request else 'approved'}
- Reviewer: {state.authorization_request.reviewer_type if state.authorization_request and state.authorization_request.reviewer_type else 'Unknown'} (Level {state.authorization_request.review_level if state.authorization_request and state.authorization_request.review_level is not None else 'N/A'})
- Service: {state.authorization_request.service_name if state.authorization_request else 'N/A'}

CLINICAL DOCUMENTATION:
{combined_clinical_doc}

{coding_section}

TASK: Submit claim documentation for payment review.

IMPORTANT CONSTRAINTS - PHASE 3:
1. You CANNOT order new tests (care is complete)
2. You CANNOT change clinical facts (record is fixed)
3. You CAN clarify documentation, submit discharge summaries, add supporting notes
4. Each appeal costs staff time - consider abandoning if unlikely to succeed

RESPONSE FORMAT (JSON):
{{
    "internal_rationale": {{
        "reasoning": "<why you expect this claim to be paid or denied>",
        "documentation_completeness": "<assessment of your documentation>"
    }},
    "insurer_request": {{
        "diagnosis_codes": [
            {{
                "icd10": "<ICD-10 code>",
                "description": "<diagnosis description>"
            }}
        ],
        "procedure_codes": [
            {{
                "code": "<CPT/HCPCS/J-code>",
                "code_type": "CPT" or "HCPCS" or "J-code",
                "description": "<service description>",
                "quantity": <number>,
                "amount_billed": <dollar amount per unit>
            }}
        ],
        "total_amount_billed": <total dollar amount>,
        "clinical_notes": "<narrative documentation of care delivered>",
        "discharge_summary": "<if applicable, final discharge documentation>",
        "supporting_documentation": "<any additional clarifying records>"
    }}
}}

IMPORTANT: The internal_rationale is for YOUR use only.
The insurer_request section is what you send to the payor for claims adjudication."""

    return base_prompt


def create_unified_phase3_payor_review_prompt(
    state, provider_request, iteration, stage=None, level=None,
    service_request=None, cost_ref=None, case=None, phase_2_evidence=None,
    case_type="specialty_medication", provider_billed_amount=None
):
    """
    Phase 3 unified payor prompt: retrospective review / claims adjudication

    KEY OPERATIONAL DIFFERENCE FROM PHASE 2:
    - Timing: AFTER care is complete
    - Record is FIXED: cannot request new clinical actions, only existing documentation
    - Decision: PAYMENT determination (not authorization)
    - REQUEST_INFO at this phase: "submit discharge summary" NOT "order another test"

    uses WORKFLOW_LEVELS for level-specific semantics (same 3 levels as Phase 2):
    - Level 0 (initial_determination): claims review, can REQUEST_INFO for missing docs
    - Level 1 (internal_reconsideration): medical reviewer appeal review, can REQUEST_INFO
    - Level 2 (independent_review): IRE, terminal, cannot REQUEST_INFO, must decide
    """
    def sum_procedure_billed_amount(procedure_codes):
        total = 0.0
        has_amount = False
        for proc in procedure_codes:
            amount = proc.get("amount_billed")
            quantity = proc.get("quantity", 1)
            if isinstance(amount, (int, float)):
                has_amount = True
                if isinstance(quantity, (int, float)):
                    total += amount * quantity
                else:
                    total += amount
        return total if has_amount else None

    # resolve level from stage name if not provided directly
    if level is None and stage:
        level = LEVEL_NAME_MAP.get(stage, 0)
    elif level is None:
        level = 0

    level_config = WORKFLOW_LEVELS.get(level, WORKFLOW_LEVELS[0])

    # build service summary
    from src.models.schemas import CaseType
    if service_request:
        if case_type == CaseType.SPECIALTY_MEDICATION:
            service_name = service_request.get('medication_name', 'medication')
            service_summary = f"""CLAIM SUBMITTED:
- Medication: {service_request.get('medication_name')}
- Dosage Administered: {service_request.get('dosage')}"""
        else:
            service_name = service_request.get('service_name', service_request.get('treatment_name', service_request.get('procedure_name', 'procedure')))
            service_summary = f"""CLAIM SUBMITTED:
- Procedure/Service: {service_name}
- Clinical Indication: {service_request.get('clinical_indication', service_request.get('treatment_justification', 'N/A'))}"""
    else:
        service_summary = "CLAIM SUBMITTED: (service details not provided)"

    # get billed amount
    total_billed = None
    if provider_billed_amount is not None:
        total_billed = provider_billed_amount

    if total_billed is None:
        provider_total = provider_request.get("total_amount_billed")
        if isinstance(provider_total, (int, float)):
            total_billed = provider_total

    procedure_codes = provider_request.get('procedure_codes', [])
    if total_billed is None and procedure_codes:
        total_billed = sum_procedure_billed_amount(procedure_codes)

    if total_billed is None and cost_ref:
        if case_type == CaseType.SPECIALTY_MEDICATION:
            total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
        else:
            total_billed = cost_ref.get('procedure_cost', 7800)

    if total_billed is None:
        total_billed = 0.0

    # build clinical documentation
    clinical_doc_parts = []
    if state.clinical_presentation:
        clinical_doc_parts.append("INITIAL PRESENTATION:")
        clinical_doc_parts.append(f"Chief Complaint: {state.clinical_presentation.chief_complaint}")
        if state.clinical_presentation.history_of_present_illness:
            clinical_doc_parts.append(f"History: {state.clinical_presentation.history_of_present_illness}")
        if state.clinical_presentation.physical_exam_findings:
            clinical_doc_parts.append(f"Physical Exam: {state.clinical_presentation.physical_exam_findings}")
        clinical_doc_parts.append("")

    if phase_2_evidence and phase_2_evidence.get('test_results'):
        clinical_doc_parts.append("DIAGNOSTIC WORKUP (Phase 2):")
        for test_name, test_data in phase_2_evidence['test_results'].items():
            if isinstance(test_data, dict):
                finding = test_data.get('finding', 'completed')
            else:
                finding = test_data
            clinical_doc_parts.append(f"- {test_name}: {finding}")
        clinical_doc_parts.append("")

    # provider's submitted documentation
    if provider_request.get('clinical_notes'):
        clinical_doc_parts.append("PROVIDER CLINICAL NOTES:")
        clinical_doc_parts.append(provider_request['clinical_notes'])
        clinical_doc_parts.append("")

    if provider_request.get('discharge_summary'):
        clinical_doc_parts.append("DISCHARGE SUMMARY:")
        clinical_doc_parts.append(provider_request['discharge_summary'])
        clinical_doc_parts.append("")

    combined_clinical_doc = "\n".join(clinical_doc_parts) if clinical_doc_parts else "No documentation provided"

    # get diagnosis codes if present
    diagnosis_codes = provider_request.get('diagnosis_codes', [])
    diagnosis_summary = ""
    if diagnosis_codes:
        diagnosis_summary = "\nDiagnosis Codes:\n" + "\n".join([
            f"  - {d.get('icd10')}: {d.get('description')}" for d in diagnosis_codes
        ])

    # extract procedure codes (line-level billing)
    procedure_summary = ""
    if procedure_codes:
        procedure_summary = "\nProcedure Codes Submitted:\n"
        for idx, proc in enumerate(procedure_codes, 1):
            procedure_summary += f"  Line {idx}: {proc.get('code')} ({proc.get('code_type')})\n"
            procedure_summary += f"    Description: {proc.get('description')}\n"
            procedure_summary += f"    Quantity: {proc.get('quantity')}\n"
            procedure_summary += f"    Amount Billed: ${proc.get('amount_billed', 0):.2f}\n"

    # inject payor policy view if available
    policy_section = ""
    if hasattr(state, 'payor_policy_view') and state.payor_policy_view:
        import json
        policy_view = state.payor_policy_view
        content_data = policy_view.get("content", {}).get("data", {})
        if content_data:
            policy_section = f"""
YOUR PAYMENT POLICY:
{json.dumps(content_data, indent=2)}

Review the claim documentation against payment guidelines.

"""

    # level-specific payor instructions from WORKFLOW_LEVELS
    role_label = level_config["role_label"]
    review_style = level_config["review_style"]
    level_description = level_config["description"]
    can_pend = level_config["can_pend"]
    is_terminal = level_config["terminal"]
    is_independent = level_config["independent"]

    if can_pend:
        decision_options = "approved | denied | pending_info"
    else:
        decision_options = "approved | denied"

    stage_instruction = f"""LEVEL {level} - {level_config['name'].upper()} ({role_label}):
Reviewer: {role_label}
Mode: {review_style}
Decision options: {decision_options}
{level_description}

CRITICAL - PHASE 3 OPERATIONAL CONTEXT:
- This is RETROSPECTIVE REVIEW: care already completed
- You are deciding PAYMENT, not authorization
- Record is FIXED: you cannot request new clinical actions
- REQUEST_INFO can only ask for EXISTING documentation (discharge summary, records)
- Provider may abandon pended claims (pends have high abandonment rate)

"""
    if is_terminal:
        stage_instruction += """CRITICAL: This is a TERMINAL review level. You MUST issue a final APPROVED or DENIED decision.
REQUEST_INFO (pending_info) is NOT available at this level.

"""
    if is_independent:
        stage_instruction += """NOTE: As an independent external reviewer, you do NOT have access to plan-internal notes.
Your decision must be based solely on the submitted claim documentation.

"""

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS} - PHASE 3: RETROSPECTIVE REVIEW (CLAIMS ADJUDICATION)

{stage_instruction}{policy_section}PATIENT CONTEXT:
- Age: {state.admission.patient_demographics.age}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}
- Current Diagnoses: {', '.join(state.admission.preliminary_diagnoses)}

{service_summary}
- Amount Billed: ${total_billed:,.2f}
{diagnosis_summary}{procedure_summary}

PHASE 2 COVERAGE/UTILIZATION REVIEW DECISION:
- Status: {state.authorization_request.authorization_status if state.authorization_request else 'approved'}
- Reviewer: {state.authorization_request.reviewer_type if state.authorization_request and state.authorization_request.reviewer_type else 'Unknown'} (Level {state.authorization_request.review_level if state.authorization_request and state.authorization_request.review_level is not None else 'N/A'})
- Service Approved: {state.authorization_request.service_name if state.authorization_request else 'N/A'}

CLINICAL DOCUMENTATION:
{combined_clinical_doc}

TASK: Review claim and decide on PAYMENT.

EVALUATION CRITERIA (RETROSPECTIVE):
- Does documentation support that services were medically necessary?
- Does the delivered service align with the Phase 2 coverage decision and documented indications?
- Is billing consistent with services documented?
- Is documentation complete enough to justify payment?

DECISION GUIDANCE:
- APPROVED: documentation complete, claim valid, service aligns with Phase 2 decision/record
- DENIED: service not covered OR clearly contradicts Phase 2 decision/record OR insufficient documentation
- PENDED (if available at this level): request EXISTING documentation (discharge summary, records)
  - NOTE: Cannot request new tests or clinical actions (care is complete)
  - Pended claims have high provider abandonment rate (regulatory arbitrage)
  - Do NOT cite "no procedure codes" or "$0 billed" if procedure lines are listed or total billed is nonzero

RESPONSE FORMAT (JSON):
{{
    "authorization_status": "{decision_options.replace(' | ', '" or "')}",  // overall: "approved", "denied", "partial", or "pending_info"

    // LINE-LEVEL ADJUDICATION (X12 835 remittance advice aligned)
    // adjudicate each submitted procedure code line separately
    "line_adjudications": [
        {{
            "line_number": <1-based index into procedure_codes array>,
            "procedure_code": "<CPT/HCPCS code from submission>",
            "adjudication_status": "approved" or "denied" or "partial",
            "billed_amount": <amount provider billed>,
            "allowed_amount": <payor's contractual allowed amount>,
            "paid_amount": <actual payment amount>,
            "adjustment_reason": "<reason for denial or adjustment, if any>"
        }}
    ],

    // OVERALL CLAIM-LEVEL FIELDS
    "total_paid_amount": <sum of all line paid_amounts>,

    // if pending_info (only for Levels 0-1):
    "pend_reason": "<what EXISTING documentation is missing>",
    "requested_documents": ["<discharge summary>", "<operative report>", etc.],

    // if fully denied (all lines denied):
    "denial_reason": "<overall reason for full claim denial>",

    "criteria_used": "<payment guidelines or policies applied>",
    "reviewer_type": "{role_label}",
    "level": {level}
}}

IMPORTANT:
- You are reviewing payment for services ALREADY RENDERED
- You must adjudicate EACH procedure code line separately in line_adjudications array
- Set overall authorization_status to "partial" if some lines approved and some denied
- Cannot prevent care (it already happened), can only approve/deny/pend payment"""

    return base_prompt
