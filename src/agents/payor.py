from typing import Dict, Any, List
import json
from langchain_core.messages import HumanMessage
from src.agents.game_agent import GameAgent
from src.models.schemas import EncounterState, AppealSubmission
from src.utils.cpt_calculator import CPTCostCalculator
from src.utils.prompts import create_payor_prompt


class PayorAgent(GameAgent):
    """Payer agent for concurrent utilization review and appeals - STRICT AUDITOR MODE."""

    SYSTEM_PROMPT = create_payor_prompt()

    def __init__(self, llm, config: Dict[str, Any] = None):
        super().__init__(llm, "Payor", config)
        self.cost_calculator = CPTCostCalculator()

    def strict_authorization_review(
        self,
        state: EncounterState,
        provider_request: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """
        Strict auditor review using payor's rigid coverage policy.

        CRITICAL: If numeric thresholds are not met EXACTLY, MUST deny or pend.
        No approval on "clinical vibes" or fuzzy clinical judgment.

        Returns dict with:
        - authorization_status: Literal["approved", "denied", "pended"]
        - denial_reason: str (if denied/pended)
        - missing_criteria: List[str] (specific thresholds not met)
        """
        policy_view = state.payor_policy_view or {}
        policy_name = policy_view.get("policy_name", "Medical Policy")
        inpatient = policy_view.get("inpatient_criteria", {})
        must_meet = inpatient.get("must_meet_one_of", [])
        prerequisites = inpatient.get("prerequisites", [])
        exclusions = policy_view.get("observation_only_triggers", [])

        prompt = f"""{self.SYSTEM_PROMPT}

STRICT AUDITOR MODE - Authorization Review (Iteration {iteration})

YOUR POLICY: {policy_name}

PREREQUISITES (must be documented):
{self._format_exclusions(prerequisites)}

INPATIENT CRITERIA - MUST MEET AT LEAST ONE:
{self._format_coverage_criteria(must_meet)}

OBSERVATION-ONLY TRIGGERS (deny inpatient if present):
{self._format_exclusions(exclusions)}

PROVIDER'S REQUEST:
{json.dumps(provider_request, indent=2, default=str)}

PATIENT CLINICAL DATA:
{self._format_patient_presentation(state)}

CLINICAL DOCUMENTATION:
{self._format_clinical_documentation(state)}

STRICT AUDITOR INSTRUCTIONS:
1. You MUST deny if numeric thresholds are not met exactly
2. Do NOT approve based on "clinical judgment" or "patient looks sick"
3. If pH is not < 7.35, SpO2 is not <= 88%, etc. → DENY
4. If documentation is vague or missing specific values → PEND for more info
5. If any absolute exclusion applies → DENY immediately

RESPONSE FORMAT (JSON):
{{
    "authorization_status": "approved" | "denied" | "pended",
    "reviewer_type": "AI Algorithm" | "UM Nurse",
    "denial_reason": "<specific threshold not met>",
    "missing_criteria": ["<criterion 1>", "<criterion 2>"],
    "criteria_used": "{policy_name}",
    "requires_peer_to_peer": true | false,
    "reasoning": "<strict policy-based rationale>"
}}"""

        messages = [HumanMessage(content=prompt)]
        response = self.llm.invoke(messages)
        return self._parse_response(response.content)

    def concurrent_review(
        self,
        state: EncounterState,
        tests_ordered: List[str],
        iteration: int
    ) -> Dict[str, Any]:
        """
        Real-time test authorization during concurrent review.

        Returns dict with:
        - approved: List[str]
        - denied: List[str]
        - denial_reasons: Dict[test_name, reason]
        """
        policy_view = state.payor_policy_view or {}

        prompt = f"""{self.SYSTEM_PROMPT}

CONCURRENT UTILIZATION REVIEW - Test Authorization

YOUR POLICY: {policy_view.get('policy_name', 'Medical Policy')}

PROVIDER REQUESTING TESTS:
{self._format_test_list(tests_ordered)}

PATIENT CLINICAL DATA:
{self._format_patient_presentation(state)}

Your task: Authorize or deny tests based on medical necessity criteria.

AUTHORIZATION CRITERIA:
- Medical necessity for requested tests
- Appropriateness for clinical presentation
- Cost-effectiveness
- Alignment with evidence-based guidelines

RESPONSE FORMAT (JSON):
{{
    "approved": ["<test1>", ...],
    "denied": ["<test2>", ...],
    "denial_reasons": {{
        "<test2>": "<specific reason for denial>",
        ...
    }},
    "reasoning": "<authorization rationale>"
}}"""

        messages = [HumanMessage(content=prompt)]
        response = self.llm.invoke(messages)
        return self._parse_response(response.content)

    def make_authorization_decision(self, state: EncounterState) -> Dict[str, Any]:
        """
        Final utilization review decision on level of care.
        Delegates to strict_authorization_review for friction model.
        """
        return self.strict_authorization_review(state, {}, 1)

    def review_appeal(
        self,
        state: EncounterState,
        appeal: AppealSubmission
    ) -> Dict[str, Any]:
        """
        Review provider's appeal - still applies strict criteria.

        Returns dict with:
        - reviewer_credentials: str
        - appeal_outcome: str
        - final_authorized_level: str
        - decision_rationale: str
        """
        policy_view = state.payor_policy_view or {}
        inpatient = policy_view.get("inpatient_criteria", {})
        must_meet = inpatient.get("must_meet_one_of", [])

        prompt = f"""{self.SYSTEM_PROMPT}

PEER-TO-PEER APPEAL REVIEW - STRICT AUDITOR MODE

YOUR POLICY: {policy_view.get('policy_name', 'Medical Policy')}

INPATIENT CRITERIA - MUST MEET AT LEAST ONE:
{self._format_coverage_criteria(must_meet)}

INITIAL DENIAL:
{state.utilization_review.denial_reason if state.utilization_review else "No denial on record"}

PROVIDER'S APPEAL:
Appeal Type: {appeal.appeal_type}
Additional Evidence: {appeal.additional_clinical_evidence}
Severity Documentation: {appeal.severity_documentation}
Guidelines Referenced: {', '.join(appeal.guideline_references)}

PATIENT CLINICAL DATA:
{self._format_patient_presentation(state)}

CLINICAL DOCUMENTATION:
{self._format_clinical_documentation(state)}

STRICT APPEAL REVIEW:
Even on appeal, you MUST verify that specific numeric thresholds are now met.
- Does new evidence provide EXACT values meeting criteria?
- Clinical narratives alone are insufficient - need numbers.

RESPONSE FORMAT (JSON):
{{
    "reviewer_credentials": "Board-Certified [Specialty]",
    "appeal_outcome": "approved" | "upheld_denial" | "partial_approval",
    "final_authorized_level": "inpatient" | "observation",
    "decision_rationale": "<specific values that met/did not meet criteria>",
    "criteria_applied": "<criteria or guidelines used>",
    "peer_to_peer_conducted": true,
    "peer_to_peer_notes": "<discussion notes>"
}}"""

        messages = [HumanMessage(content=prompt)]
        response = self.llm.invoke(messages)
        return self._parse_response(response.content)

    def _format_coverage_criteria(self, criteria: List[Dict]) -> str:
        if not criteria:
            return "No specific criteria defined"

        lines = []
        for i, crit in enumerate(criteria, 1):
            metric = crit.get("metric", "Unknown")
            # handle different criterion formats (InterQual 2022 structure)
            if "threshold" in crit:
                threshold = crit["threshold"]
                if "with" in crit:
                    lines.append(f"{i}. {metric} {threshold} WITH {crit['with']}")
                else:
                    lines.append(f"{i}. {metric} {threshold}")
            elif "range" in crit:
                lines.append(f"{i}. {metric}: {crit['range']}")
            elif "values" in crit:
                lines.append(f"{i}. {metric}: {', '.join(crit['values'])}")
            elif "description" in crit:
                lines.append(f"{i}. {metric}: {crit['description']}")
            else:
                lines.append(f"{i}. {metric}")
        return "\n".join(lines)

    def _format_exclusions(self, exclusions: List[str]) -> str:
        if not exclusions:
            return "No absolute exclusions"
        return "\n".join([f"- {e}" for e in exclusions])

    def _format_test_list(self, test_names: List[str]) -> str:
        return "\n".join([f"- {test}" for test in test_names])

    def _format_patient_presentation(self, state: EncounterState) -> str:
        presentation = state.clinical_presentation
        demographics = state.admission.patient_demographics
        return f"""Age: {demographics.age}
Sex: {demographics.sex}
Chief Complaint: {presentation.chief_complaint}
Vitals: {presentation.vital_signs}
Physical Exam: {presentation.physical_exam_findings}
Medical History: {', '.join(presentation.medical_history)}"""

    def _format_clinical_documentation(self, state: EncounterState) -> str:
        if not state.provider_documentation:
            return "No clinical documentation available"

        lines = []
        doc = state.provider_documentation

        if doc.final_diagnoses:
            lines.append(f"Diagnoses: {', '.join(doc.final_diagnoses)}")

        if doc.lab_results:
            lines.append("\nLab Results:")
            for lab in doc.lab_results:
                lines.append(f"  - {lab.test_name}: {lab.result_summary}")

        if doc.imaging_results:
            lines.append("\nImaging:")
            for img in doc.imaging_results:
                lines.append(f"  - {img.exam_name}: {img.impression}")

        if doc.severity_indicators:
            lines.append("\nSeverity Indicators:")
            for indicator in doc.severity_indicators:
                lines.append(f"  - {indicator}")

        return "\n".join(lines)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        try:
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                json_str = content[start:end]
                return json.loads(json_str)
        except ValueError:
            pass

        return {
            "authorization_status": "denied",
            "denial_reason": "Error parsing response - defaulting to deny",
            "missing_criteria": [],
            "reasoning": "Parse error"
        }

    def make_decision(self, state: EncounterState) -> Dict[str, Any]:
        """Make strategic decision based on game state (stub implementation)."""
        return {"action": "review_authorization", "state": "utilization_review"}

    def calculate_payoff(self, state: EncounterState) -> float:
        """Calculate utility/payoff from game outcome (stub implementation)."""
        if state.financial_settlement:
            return -state.financial_settlement.payer_payment
        return 0.0

    def calculate_metrics(self, state: EncounterState) -> Dict[str, float]:
        """Calculate agent-specific metrics (stub implementation)."""
        metrics = {
            "denial_issued": float(state.denial_occurred),
            "appeal_reviewed": float(state.appeal_filed),
            "appeal_upheld": float(not state.appeal_successful) if state.appeal_filed else 0.0
        }
        return metrics
