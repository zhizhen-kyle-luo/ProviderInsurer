from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal, Union
from datetime import date
from pydantic import BaseModel, Field
import json


# pa type discriminator for different authorization workflows
class PAType:
    INPATIENT_ADMISSION = "inpatient_admission"
    SPECIALTY_MEDICATION = "specialty_medication"
    OUTPATIENT_IMAGING = "outpatient_imaging"
    POST_ACUTE_CARE = "post_acute_care"
    CARDIAC_TESTING = "cardiac_testing"


class PatientDemographics(BaseModel):
    patient_id: str
    age: int
    sex: Literal["M", "F"]
    mrn: str


class InsuranceInfo(BaseModel):
    plan_type: Literal["MA", "Commercial", "Medicare_FFS", "Medicaid"]
    payer_name: str
    member_id: str
    group_number: Optional[str] = None
    authorization_required: bool = True


class AdmissionNotification(BaseModel):
    patient_demographics: PatientDemographics
    insurance: InsuranceInfo
    admission_date: date
    admission_source: Literal["ER", "Direct", "Transfer"]
    chief_complaint: str
    preliminary_diagnoses: List[str]
    expected_drg: Optional[str] = None
    expected_los_days: Optional[int] = None


class ClinicalPresentation(BaseModel):
    chief_complaint: str
    history_of_present_illness: str
    vital_signs: Dict[str, Any]
    physical_exam_findings: str
    medical_history: List[str]


class DiagnosticTest(BaseModel):
    test_name: str
    cpt_code: Optional[str] = None
    icd10_codes: List[str] = Field(default_factory=list)
    clinical_rationale: str


class LabResult(BaseModel):
    test_name: str
    result_summary: str


class ImagingResult(BaseModel):
    exam_name: str
    impression: str


class FrictionMetrics(BaseModel):
    """tracks administrative friction in PA negotiations"""
    # AAV (Administrative Action Volume): discrete moves (submissions, appeals, denials, pends)
    provider_actions: int = 0
    payor_actions: int = 0

    # CPL (Clinical Probing Load): tests ordered to satisfy coverage gates
    probing_tests_count: int = 0

    # ED (Escalation Depth): 0=Approved First Try, 1=First Appeal, 2=Second Appeal, 3=Abandon
    escalation_depth: int = 0

    @property
    def total_friction(self) -> int:
        return self.provider_actions + self.payor_actions + self.probing_tests_count + self.escalation_depth


class SubmissionPacket(BaseModel):
    """
    what provider has submitted for insurer review (visible at all levels)
    this is the official record that even independent reviewers can see
    """
    clinical_notes: str = ""
    diagnosis_codes: List[Dict[str, Any]] = Field(default_factory=list)
    procedure_codes: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    test_results: Dict[str, Any] = Field(default_factory=dict)
    prior_authorization_reference: Optional[str] = None
    appeal_arguments: List[str] = Field(default_factory=list)
    submitted_at_level: int = 0


class InternalNotes(BaseModel):
    """
    plan-internal notes visible only to Level 0 and Level 1 reviewers
    Level 2 (independent review) must NOT see these
    """
    gating_results: Dict[str, bool] = Field(default_factory=dict)
    missing_required_fields: List[str] = Field(default_factory=list)
    policy_match_score: Optional[str] = None
    prior_denial_rationale_template: Optional[str] = None
    internal_flags: List[str] = Field(default_factory=list)
    copilot_recommendations: List[str] = Field(default_factory=list)
    reviewer_notes: str = ""


class LevelDecisionRecord(BaseModel):
    """record of a decision made at a specific level"""
    level: int
    role: str
    decision: Literal["APPROVE", "DENY", "REQUEST_INFO"]
    rationale: str
    criteria_cited: List[str] = Field(default_factory=list)
    request_info_cycles_at_level: int = 0
    internal_notes_available: bool = False


class ClinicalIteration(BaseModel):
    iteration_number: int
    action_type: Literal["order_tests", "request_treatment", "abandon"] = "order_tests"
    tests_ordered: List[str] = Field(default_factory=list)
    tests_approved: List[str] = Field(default_factory=list)
    tests_denied: List[str] = Field(default_factory=list)
    denial_reasons: Dict[str, str] = Field(default_factory=dict)
    differential_diagnoses: List[str] = Field(default_factory=list)


class ProviderClinicalRecord(BaseModel):
    iterations: List[ClinicalIteration] = Field(default_factory=list)
    final_diagnoses: List[str]
    lab_results: List[LabResult] = Field(default_factory=list)
    imaging_results: List[ImagingResult] = Field(default_factory=list)
    clinical_justification: str
    severity_indicators: List[str] = Field(default_factory=list)


class UtilizationReviewDecision(BaseModel):
    reviewer_type: str
    authorization_status: Literal["approved_inpatient", "denied_suggest_observation", "pending_info"]
    authorized_level_of_care: Literal["inpatient", "observation", "outpatient"]
    denial_reason: Optional[str] = None
    criteria_used: str
    criteria_met: bool = True
    missing_documentation: List[str] = Field(default_factory=list)
    requires_peer_to_peer: bool = False


class AppealSubmission(BaseModel):
    appeal_type: Literal["peer_to_peer", "written_appeal", "expedited"]
    additional_clinical_evidence: str
    severity_documentation: str
    guideline_references: List[str] = Field(default_factory=list)
    new_lab_results: List[LabResult] = Field(default_factory=list)
    new_imaging: List[ImagingResult] = Field(default_factory=list)


class AppealDecision(BaseModel):
    reviewer_credentials: str
    appeal_outcome: Literal["approved", "upheld_denial", "partial_approval"]
    final_authorized_level: Literal["inpatient", "observation", "outpatient"]
    decision_rationale: str
    criteria_applied: str
    peer_to_peer_conducted: bool = False
    peer_to_peer_notes: Optional[str] = None


class AppealRecord(BaseModel):
    initial_denial: UtilizationReviewDecision
    appeal_submission: Optional[AppealSubmission] = None
    appeal_decision: Optional[AppealDecision] = None
    appeal_filed: bool = False
    appeal_successful: bool = False


class ServiceLineItem(BaseModel):
    service_description: str
    cpt_or_drg_code: str
    billed_amount: float
    allowed_amount: float
    paid_amount: float


class DRGAssignment(BaseModel):
    drg_code: str
    drg_description: str
    relative_weight: float
    geometric_mean_los: float
    base_payment_rate: float
    total_drg_payment: float


class FinancialSettlement(BaseModel):
    line_items: List[ServiceLineItem] = Field(default_factory=list)
    drg_assignment: Optional[DRGAssignment] = None
    total_billed_charges: float
    total_allowed_amount: float
    payer_payment: float
    patient_responsibility: float
    outlier_payment: float = 0.0
    quality_adjustments: float = 0.0
    total_hospital_revenue: float
    estimated_hospital_cost: float
    hospital_margin: float


class EncounterState(BaseModel):
    case_id: str
    encounter_id: str = Field(default_factory=lambda: f"ENC-{date.today().strftime('%Y%m%d')}")

    # pa type discriminator
    pa_type: str = PAType.INPATIENT_ADMISSION

    admission_date: date
    review_date: Optional[date] = None
    appeal_date: Optional[date] = None
    settlement_date: Optional[date] = None

    admission: AdmissionNotification
    clinical_presentation: ClinicalPresentation

    # inpatient-specific fields
    provider_documentation: Optional[ProviderClinicalRecord] = None
    utilization_review: Optional[UtilizationReviewDecision] = None
    appeal_record: Optional[AppealRecord] = None
    financial_settlement: Optional[FinancialSettlement] = None
    final_authorized_level: Optional[Literal["inpatient", "observation", "outpatient"]] = None

    # medication-specific fields
    medication_request: Optional[MedicationRequest] = None
    medication_authorization: Optional[MedicationAuthorizationDecision] = None
    medication_financial: Optional[MedicationFinancialSettlement] = None

    # procedure-specific fields
    procedure_request: Optional[ProcedureRequest] = None

    denial_occurred: bool = False
    appeal_filed: bool = False
    appeal_successful: bool = False

    # phase 3 pend tracking
    claim_pended: bool = False
    claim_rejected: bool = False
    claim_abandoned_via_pend: bool = False
    pend_iterations: int = 0

    # phase 3 billing - Provider's actual chosen amount (for DRG upcoding analysis)
    phase_3_billed_amount: Optional[float] = None
    phase_3_diagnosis_code: Optional[str] = None

    # friction model - policy asymmetry and friction tracking
    friction_metrics: Optional[FrictionMetrics] = None
    provider_policy_view: Dict[str, Any] = Field(default_factory=dict)  # fuzzy clinical view (GOLD)
    payor_policy_view: Dict[str, Any] = Field(default_factory=dict)  # strict coverage view (InterQual)

    ground_truth_outcome: Optional[Union[Literal["inpatient", "observation"], Literal["approved", "denied"]]] = None
    simulation_matches_reality: Optional[bool] = None

    # level-specific tracking for Medicare Advantage workflow (0-indexed: L0=triage, L1=reconsideration, L2=IRE)
    current_level: int = 0
    level_decision_history: List["LevelDecisionRecord"] = Field(default_factory=list)
    submission_packet: Optional["SubmissionPacket"] = None
    internal_notes: Optional["InternalNotes"] = None
    independent_review_reached: bool = False  # true when escalated to Level 2 (IRE)
    request_info_cycles_by_level: Dict[int, int] = Field(default_factory=dict)

    # audit log for LLM interactions
    audit_log: Optional["AuditLog"] = None

    # truth checking results (deception detection)
    # using Any to avoid circular import with src.evaluation.truth_checker
    truth_check_phase2: Optional[Any] = None  # FactCheckResult type
    truth_check_phase3: Optional[Any] = None  # FactCheckResult type


class Message(BaseModel):
    id: str
    session_id: str
    turn_id: int
    speaker: Literal["user", "agent"]
    agent: Optional[Literal["Provider", "Payer"]] = None
    role: Literal["system", "assistant", "user"]
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TestOrdered(BaseModel):
    test_name: str
    cpt_code: Optional[str] = None
    rationale: Optional[str] = None


# specialty medication pa models
class MedicationRequest(BaseModel):
    medication_name: str
    ndc_code: Optional[str] = None
    j_code: Optional[str] = None
    dosage: str
    frequency: str
    duration: str
    icd10_codes: List[str] = Field(default_factory=list)
    clinical_rationale: str
    prior_therapies_failed: List[str] = Field(default_factory=list)
    step_therapy_completed: bool = False


# cardiac/procedure pa models
class ProcedureRequest(BaseModel):
    procedure_name: str
    cpt_code: Optional[str] = None
    clinical_indication: str
    icd10_codes: List[str] = Field(default_factory=list)


class MedicationAuthorizationDecision(BaseModel):
    reviewer_type: str
    authorization_status: Literal["approved", "rejected", "pended", "denied", "pending_info"]  # keep denied/pending_info for backward compat
    denial_reason: Optional[str] = None
    criteria_used: str
    step_therapy_required: bool = False
    missing_documentation: List[str] = Field(default_factory=list)
    approved_quantity: Optional[str] = None
    approved_duration_days: Optional[int] = None
    requires_peer_to_peer: bool = False


class MedicationFinancialSettlement(BaseModel):
    medication_name: str
    j_code: Optional[str] = None
    acquisition_cost: float
    administration_fee: float = 0.0
    total_billed: float
    payer_payment: float
    patient_copay: float
    prior_auth_cost: float = 0.0
    appeal_cost: float = 0.0
    total_administrative_cost: float


# Audit Log Schemas for LLM Interaction Tracking
class LLMInteraction(BaseModel):
    """Single LLM prompt-response interaction."""
    interaction_id: str
    timestamp: str
    phase: Literal["phase_1_presentation", "phase_2_pa", "phase_2_utilization_review", "phase_2_pa_appeal", "phase_3_claims", "phase_4_financial"]
    agent: Literal["provider", "payor", "environment"]
    action: str  # e.g., "order_tests", "concurrent_review", "submit_appeal", "review_appeal"
    system_prompt: str
    user_prompt: str
    llm_response: str
    parsed_output: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EnvironmentAction(BaseModel):
    """environment agent action (test result generation, noise injection, etc)"""
    action_id: str
    timestamp: str
    phase: str
    action_type: str  # "generate_test_result", "inject_noise", "calculate_settlement"
    description: str
    outcome: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentConfiguration(BaseModel):
    """agent behavioral parameters and system prompt"""
    agent_name: str
    behavioral_parameters: Dict[str, Any]
    system_prompt: str


class AuditLog(BaseModel):
    """Complete audit log for a case simulation."""
    case_id: str
    simulation_start: str
    simulation_end: Optional[str] = None
    interactions: List[LLMInteraction] = Field(default_factory=list)
    environment_actions: List[EnvironmentAction] = Field(default_factory=list)
    agent_configurations: List[AgentConfiguration] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)

    def save_to_markdown(self, filepath: str):
        """save audit log to markdown file with full interaction details"""
        lines = []

        # header
        lines.append(f"# Audit Log: {self.case_id}")
        lines.append("")
        lines.append(f"**Simulation Start:** {self.simulation_start}")
        lines.append(f"**Simulation End:** {self.simulation_end or 'In Progress'}")
        lines.append("")

        # guide section
        lines.append("## How to Read This Audit Log")
        lines.append("")
        lines.append("Each interaction below contains the following sections:")
        lines.append("")
        lines.append("| Section | Description | Source |")
        lines.append("|---------|-------------|--------|")
        lines.append("| **System Prompt** | Agent's role, incentives, and behavioral parameters | Defined in `prompts.py`, constant per agent |")
        lines.append("| **User Prompt** | Task-specific instructions with case data | Generated per interaction from case/prior outputs |")
        lines.append("| **LLM Response** | Raw text returned by LLM | Generated by LLM (may include extra commentary) |")
        lines.append("| **Parsed Output** | Structured JSON extracted from LLM response | Parsed from LLM response, **actually used by simulation** |")
        lines.append("| **Rationale/Context** *(if present)* | LLM's reasoning explanation | Spontaneously added by LLM (not requested, not used) |")
        lines.append("")
        lines.append("**Note:** Only the \"Parsed Output\" is used to drive simulation decisions. Extra sections like \"Rationale\" are logged for transparency but do not affect outcomes.")
        lines.append("")

        # summary
        if self.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(f"- **Total Interactions:** {self.summary.get('total_interactions', 0)}")
            lines.append(f"- **Duration:** {self.summary.get('simulation_duration_seconds', 0):.2f} seconds")
            lines.append("")

            if "interactions_by_phase" in self.summary:
                lines.append("**Interactions by Phase:**")
                for phase, count in self.summary["interactions_by_phase"].items():
                    lines.append(f"- {phase}: {count}")
                lines.append("")

            if "interactions_by_agent" in self.summary:
                lines.append("**Interactions by Agent:**")
                for agent, count in self.summary["interactions_by_agent"].items():
                    lines.append(f"- {agent}: {count}")
                lines.append("")

            if "behavioral_parameters" in self.summary:
                lines.append("**Behavioral Parameters:**")
                params = self.summary["behavioral_parameters"]
                if "provider" in params:
                    lines.append("- **Provider:**")
                    for key, value in params["provider"].items():
                        lines.append(f"  - {key}: {value}")
                if "payor" in params:
                    lines.append("- **Payor:**")
                    for key, value in params["payor"].items():
                        lines.append(f"  - {key}: {value}")
                lines.append("")

            if "truth_check_summary" in self.summary:
                lines.append("**Truth Check Summary:**")
                tc = self.summary["truth_check_summary"]
                if tc.get("phase2"):
                    lines.append("- **Phase 2 (PA Request):**")
                    lines.append(f"  - Deceptive: {tc['phase2'].get('is_deceptive', 'N/A')}")
                    lines.append(f"  - Deception Score: {tc['phase2'].get('deception_score', 0.0):.2f}")
                    lines.append(f"  - Hallucinated Claims: {len(tc['phase2'].get('hallucinated_claims', []))}")
                if tc.get("phase3"):
                    lines.append("- **Phase 3 (Appeal):**")
                    lines.append(f"  - Deceptive: {tc['phase3'].get('is_deceptive', 'N/A')}")
                    lines.append(f"  - Deception Score: {tc['phase3'].get('deception_score', 0.0):.2f}")
                    lines.append(f"  - Hallucinated Claims: {len(tc['phase3'].get('hallucinated_claims', []))}")
                    if tc['phase2'] and tc['phase3']:
                        doubled_down = tc['phase3']['deception_score'] > tc['phase2']['deception_score']
                        lines.append(f"  - **Doubled Down on Lies:** {'Yes' if doubled_down else 'No'}")
                lines.append("")

        lines.append("---")
        lines.append("")

        # detailed interactions
        for i, interaction in enumerate(self.interactions, 1):
            # interaction header
            phase_name = self._format_phase_name(interaction.phase)
            lines.append(f"## Interaction {i}: {phase_name}")
            lines.append("")
            lines.append(f"**Timestamp:** {interaction.timestamp}")
            lines.append(f"**Agent:** {interaction.agent.capitalize()}")
            lines.append(f"**Action:** {interaction.action.replace('_', ' ').title()}")
            lines.append("")

            # metadata
            if interaction.metadata:
                lines.append("**Metadata:**")
                for key, value in interaction.metadata.items():
                    if isinstance(value, (list, dict)):
                        lines.append(f"- {key}: `{json.dumps(value)}`")
                    else:
                        lines.append(f"- {key}: {value}")
                lines.append("")

            # system prompt
            lines.append("### System Prompt")
            lines.append("")
            lines.append("```")
            lines.append(interaction.system_prompt)
            lines.append("```")
            lines.append("")

            # user prompt
            lines.append("### User Prompt")
            lines.append("")
            lines.append("```")
            lines.append(interaction.user_prompt)
            lines.append("```")
            lines.append("")

            # llm response
            lines.append("### LLM Response")
            lines.append("")
            lines.append("```")
            lines.append(interaction.llm_response)
            lines.append("```")
            lines.append("")

            # parsed output
            lines.append("### Parsed Output")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(interaction.parsed_output, indent=2))
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

        # write to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

    def _format_phase_name(self, phase: str) -> str:
        """format phase identifier as readable name"""
        phase_names = {
            "phase_2_pa": "Phase 2: Prior Authorization",
            "phase_2_pa_appeal": "Phase 2: PA Appeal Process",
            "phase_3_claims": "Phase 3: Claims Adjudication",
            "phase_4_financial": "Phase 4: Financial Settlement"
        }
        return phase_names.get(phase, phase.replace("_", " ").title())

    def save_to_folder(self, output_dir: str):
        """save audit log split into organized folder structure

        creates:
            {output_dir}/
                00_config.md         - agent configs
                phase2_iter01.md     - P2 iteration 1 (provider + payor)
                phase2_iter02.md     - P2 iteration 2 ...
                phase3_claims.md     - claim submission + adjudication
                summary.md           - compact decision trace
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        # 1. Config file - agent settings
        config_lines = []
        config_lines.append(f"# Configuration: {self.case_id}")
        config_lines.append("")
        config_lines.append(f"**Simulation:** {self.simulation_start} → {self.simulation_end or 'In Progress'}")
        config_lines.append("")

        if self.summary.get("behavioral_parameters"):
            params = self.summary["behavioral_parameters"]
            config_lines.append("## Agent Parameters")
            config_lines.append("")
            if "provider" in params:
                config_lines.append("### Provider")
                for k, v in params["provider"].items():
                    config_lines.append(f"- {k}: {v}")
                config_lines.append("")
            if "payor" in params:
                config_lines.append("### Payor")
                for k, v in params["payor"].items():
                    config_lines.append(f"- {k}: {v}")
                config_lines.append("")

        with open(os.path.join(output_dir, "00_config.md"), 'w', encoding='utf-8') as f:
            f.write("\n".join(config_lines))

        # 2. Phase 2 files - one per iteration (provider + payor pair)
        phase_2_interactions = [i for i in self.interactions if i.phase == "phase_2_pa"]

        # group by iteration
        iterations = {}
        for interaction in phase_2_interactions:
            iter_num = interaction.metadata.get("iteration", 0)
            if iter_num not in iterations:
                iterations[iter_num] = []
            iterations[iter_num].append(interaction)

        for iter_num, iter_interactions in sorted(iterations.items()):
            iter_lines = []
            iter_lines.append(f"# Phase 2 - Iteration {iter_num}")
            iter_lines.append("")

            for interaction in iter_interactions:
                iter_lines.append(f"## {interaction.agent.capitalize()} - {interaction.action.replace('_', ' ').title()}")
                iter_lines.append("")

                # metadata
                if interaction.metadata:
                    meta_items = [f"{k}={v}" for k, v in interaction.metadata.items()
                                  if k not in ["word_count"]]
                    iter_lines.append(f"**Meta:** {', '.join(meta_items)}")
                    iter_lines.append("")

                # user prompt (collapsible)
                iter_lines.append("<details>")
                iter_lines.append("<summary>User Prompt</summary>")
                iter_lines.append("")
                iter_lines.append("```")
                iter_lines.append(interaction.user_prompt)
                iter_lines.append("```")
                iter_lines.append("</details>")
                iter_lines.append("")

                # parsed output
                iter_lines.append("### Decision")
                iter_lines.append("")
                iter_lines.append("```json")
                iter_lines.append(json.dumps(interaction.parsed_output, indent=2))
                iter_lines.append("```")
                iter_lines.append("")
                iter_lines.append("---")
                iter_lines.append("")

            filename = f"phase2_iter{iter_num:02d}.md"
            with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
                f.write("\n".join(iter_lines))

        # 3. Phase 3 files - claims adjudication (may have multiple iterations for appeals/resubmissions)
        phase_3_interactions = [i for i in self.interactions if i.phase == "phase_3_claims"]
        if phase_3_interactions:
            # group by iteration (claims can be pended/appealed)
            p3_iterations = {}
            for interaction in phase_3_interactions:
                iter_num = interaction.metadata.get("iteration", interaction.metadata.get("appeal_round", 1))
                if iter_num not in p3_iterations:
                    p3_iterations[iter_num] = []
                p3_iterations[iter_num].append(interaction)

            for iter_num, iter_interactions in sorted(p3_iterations.items()):
                p3_lines = []
                p3_lines.append(f"# Phase 3 - Claims (Round {iter_num})")
                p3_lines.append("")

                for interaction in iter_interactions:
                    p3_lines.append(f"## {interaction.agent.capitalize()} - {interaction.action.replace('_', ' ').title()}")
                    p3_lines.append("")

                    if interaction.metadata:
                        meta_items = [f"{k}={v}" for k, v in interaction.metadata.items()
                                      if k not in ["word_count"]]
                        p3_lines.append(f"**Meta:** {', '.join(meta_items)}")
                        p3_lines.append("")

                    p3_lines.append("<details>")
                    p3_lines.append("<summary>User Prompt</summary>")
                    p3_lines.append("")
                    p3_lines.append("```")
                    p3_lines.append(interaction.user_prompt)
                    p3_lines.append("```")
                    p3_lines.append("</details>")
                    p3_lines.append("")

                    p3_lines.append("### Decision")
                    p3_lines.append("")
                    p3_lines.append("```json")
                    p3_lines.append(json.dumps(interaction.parsed_output, indent=2))
                    p3_lines.append("```")
                    p3_lines.append("")
                    p3_lines.append("---")
                    p3_lines.append("")

                # single iteration -> phase3_claims.md, multiple -> phase3_round01.md etc
                if len(p3_iterations) == 1:
                    filename = "phase3_claims.md"
                else:
                    filename = f"phase3_round{iter_num:02d}.md"
                with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
                    f.write("\n".join(p3_lines))

        # 4. Summary file
        self.save_summary(os.path.join(output_dir, "summary.md"))

    def save_summary(self, filepath: str):
        """save compact decision trace summary - much smaller than full audit log

        focuses on:
        - simulation config and patient info
        - key decisions by each agent with brief reasoning
        - outcomes and financial results
        """
        lines = []

        # header
        lines.append(f"# Decision Trace: {self.case_id}")
        lines.append("")
        lines.append(f"**Run:** {self.simulation_start} → {self.simulation_end or 'In Progress'}")
        lines.append("")

        # agent configs (compact)
        if self.summary.get("behavioral_parameters"):
            params = self.summary["behavioral_parameters"]
            lines.append("## Agent Configuration")
            lines.append("")
            if "provider" in params:
                prov = params["provider"]
                lines.append(f"**Provider:** risk={prov.get('risk_tolerance', 'mod')}, care={prov.get('patient_care_weight', 'mod')}, docs={prov.get('documentation_style', 'mod')}")
            if "payor" in params:
                pay = params["payor"]
                lines.append(f"**Payor:** cost={pay.get('cost_focus', 'mod')}, denial={pay.get('denial_threshold', 'mod')}, ai={pay.get('ai_reliance', 'mod')}")
            lines.append("")

        # decision trace by phase
        lines.append("## Decision Trace")
        lines.append("")

        # group interactions by phase
        phase_2_interactions = [i for i in self.interactions if i.phase == "phase_2_pa"]
        phase_3_interactions = [i for i in self.interactions if i.phase == "phase_3_claims"]

        # phase 2 summary
        if phase_2_interactions:
            lines.append("### Phase 2: Prior Authorization")
            lines.append("")
            lines.append("| Iter | Agent | Action | Key Decision | Outcome |")
            lines.append("|------|-------|--------|--------------|---------|")

            for interaction in phase_2_interactions:
                iter_num = interaction.metadata.get("iteration", "?")
                agent = interaction.agent.upper()[:4]
                action = interaction.action.replace("_request", "").replace("_review", "")

                # extract key decision info from parsed output
                parsed = interaction.parsed_output or {}
                if interaction.agent == "provider":
                    conf = parsed.get("confidence", interaction.metadata.get("confidence", "?"))
                    req_type = parsed.get("request_type", interaction.metadata.get("request_type", "?"))
                    key_decision = f"conf={conf:.1f}" if isinstance(conf, float) else f"conf={conf}"
                    outcome = req_type
                else:
                    status = parsed.get("authorization_status", "?")
                    reason = parsed.get("denial_reason", "")[:30] if parsed.get("denial_reason") else ""
                    key_decision = status.upper()
                    outcome = reason + "..." if reason else status

                lines.append(f"| {iter_num} | {agent} | {action} | {key_decision} | {outcome} |")

            lines.append("")

        # phase 3 summary
        if phase_3_interactions:
            lines.append("### Phase 3: Claims Adjudication")
            lines.append("")
            lines.append("| Agent | Action | Key Decision | Amount |")
            lines.append("|-------|--------|--------------|--------|")

            for interaction in phase_3_interactions:
                agent = interaction.agent.upper()[:4]
                action = interaction.action.replace("claim_", "")
                parsed = interaction.parsed_output or {}

                if interaction.agent == "provider":
                    # extract diagnosis and amount
                    claim = parsed.get("claim_submission", parsed)
                    codes = claim.get("diagnosis_codes", [])
                    dx = codes[0].get("icd10", "?") if codes else "?"
                    amount = claim.get("total_amount_billed", "?")
                    key_decision = f"Dx: {dx}"
                    amt_str = f"${amount:,.0f}" if isinstance(amount, (int, float)) else str(amount)
                else:
                    status = parsed.get("claim_status", "?")
                    key_decision = status.upper()
                    amt = parsed.get("approved_amount", "")
                    amt_str = f"${amt:,.0f}" if isinstance(amt, (int, float)) else "-"

                lines.append(f"| {agent} | {action} | {key_decision} | {amt_str} |")

            lines.append("")

        # outcome summary
        lines.append("## Outcome")
        lines.append("")
        if self.summary:
            lines.append(f"- **Total Interactions:** {self.summary.get('total_interactions', 0)}")
            if "interactions_by_phase" in self.summary:
                p2_count = self.summary["interactions_by_phase"].get("phase_2_pa", 0)
                p3_count = self.summary["interactions_by_phase"].get("phase_3_claims", 0)
                lines.append(f"- **Phase 2 Iterations:** {p2_count // 2}")  # div by 2 for provider+payor
                lines.append(f"- **Phase 3 Steps:** {p3_count}")

        # write
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

    def save_to_markdown_compact(self, filepath: str, include_prompts: bool = False):
        """save audit log with reduced verbosity

        args:
            filepath: output file path
            include_prompts: if False (default), omit system prompts and show only user prompt summary
        """
        lines = []

        # header
        lines.append(f"# Audit Log: {self.case_id}")
        lines.append("")
        lines.append(f"**Simulation Start:** {self.simulation_start}")
        lines.append(f"**Simulation End:** {self.simulation_end or 'In Progress'}")
        lines.append("")

        # summary (same as before)
        if self.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(f"- **Total Interactions:** {self.summary.get('total_interactions', 0)}")

            if "interactions_by_phase" in self.summary:
                lines.append("- **By Phase:** " + ", ".join(f"{k}: {v}" for k, v in self.summary["interactions_by_phase"].items()))

            if "behavioral_parameters" in self.summary:
                params = self.summary["behavioral_parameters"]
                if "provider" in params:
                    prov = params["provider"]
                    lines.append(f"- **Provider:** risk={prov.get('risk_tolerance')}, care={prov.get('patient_care_weight')}, docs={prov.get('documentation_style')}")
                if "payor" in params:
                    pay = params["payor"]
                    lines.append(f"- **Payor:** cost={pay.get('cost_focus')}, denial={pay.get('denial_threshold')}, ai={pay.get('ai_reliance')}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # interactions - compact format
        for i, interaction in enumerate(self.interactions, 1):
            phase_name = self._format_phase_name(interaction.phase)
            lines.append(f"## {i}. {phase_name} - {interaction.agent.capitalize()}")
            lines.append("")
            lines.append(f"**Action:** {interaction.action.replace('_', ' ').title()}")

            # metadata (compact)
            if interaction.metadata:
                meta_items = [f"{k}={v}" for k, v in interaction.metadata.items()
                              if k not in ["word_count", "cache_hit"]]
                if meta_items:
                    lines.append(f"**Meta:** {', '.join(meta_items)}")
            lines.append("")

            # user prompt (optional, truncated)
            if include_prompts:
                lines.append("<details>")
                lines.append("<summary>User Prompt (click to expand)</summary>")
                lines.append("")
                lines.append("```")
                # truncate long prompts
                prompt = interaction.user_prompt
                if len(prompt) > 2000:
                    prompt = prompt[:2000] + "\n... [truncated]"
                lines.append(prompt)
                lines.append("```")
                lines.append("</details>")
                lines.append("")

            # parsed output only (skip raw LLM response - it's redundant)
            lines.append("### Decision")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(interaction.parsed_output, indent=2))
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))


# rebuild models to resolve forward references
EncounterState.model_rebuild()
AuditLog.model_rebuild()
