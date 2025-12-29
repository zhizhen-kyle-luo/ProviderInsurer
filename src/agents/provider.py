from typing import Dict, Any, List
import json
from langchain_core.messages import HumanMessage
from src.agents.game_agent import GameAgent
from src.models.schemas import EncounterState, ClinicalIteration, UtilizationReviewDecision
from src.utils.cpt_calculator import CPTCostCalculator
from src.utils.prompts import create_provider_prompt


class ProviderAgent(GameAgent):
    """Provider agent for concurrent utilization review workflow."""

    SYSTEM_PROMPT = create_provider_prompt()

    def __init__(self, llm, config: Dict[str, Any] = None):
        super().__init__(llm, "Provider", config)
        self.cost_calculator = CPTCostCalculator()

    def determine_action(
        self,
        state: EncounterState,
        iteration: int,
        prior_iterations: List[ClinicalIteration]
    ) -> Dict[str, Any]:
        """
        Determine next action in friction model: order_tests, request_treatment, or abandon.

        Uses provider's fuzzy clinical guidelines (GOLD) to guide decision.
        Provider does NOT know the Payor's strict thresholds.

        Returns dict with:
        - action_type: Literal["order_tests", "request_treatment", "abandon"]
        - tests_ordered: List[str] (if action_type == "order_tests")
        - treatment_request: Dict (if action_type == "request_treatment")
        - reasoning: str
        """
        policy_view = state.provider_policy_view or {}
        policy_name = policy_view.get("policy_name", "Clinical Guidelines")
        criteria = policy_view.get("hospitalization_indications", [])

        prompt = f"""{self.SYSTEM_PROMPT}

FRICTION MODEL - Provider Decision (Iteration {iteration})

YOUR POLICY REFERENCE: {policy_name}
ADMISSION CRITERIA (your view):
{self._format_criteria(criteria)}

IMPORTANT WARNING:
The Insurer uses a HIDDEN, STRICTER policy with specific numeric thresholds.
Your clinical judgment may not align with their coverage criteria.
Gather evidence that demonstrates objective severity metrics.

PATIENT PRESENTATION:
{self._format_clinical_presentation(state)}

PRIOR ITERATIONS:
{self._format_prior_iterations(prior_iterations)}

DETERMINE YOUR NEXT ACTION:
1. "order_tests" - Order diagnostic tests to gather evidence for coverage
2. "request_treatment" - Submit prior authorization request for treatment
3. "abandon" - Stop pursuing authorization (patient won't receive care)

DECISION FACTORS:
- Do you have sufficient objective evidence (labs, vitals, imaging)?
- Will additional tests strengthen your case against a strict auditor?
- Is further iteration likely to succeed or just add friction?

RESPONSE FORMAT (JSON):
{{
    "action_type": "order_tests" | "request_treatment" | "abandon",
    "tests_ordered": ["<test_name>", ...],  // if order_tests
    "treatment_request": {{  // if request_treatment
        "diagnosis": "<primary diagnosis>",
        "treatment": "<requested treatment>",
        "justification": "<clinical justification>"
    }},
    "differential_diagnoses": ["<dx1>", "<dx2>"],
    "reasoning": "<clinical reasoning for this action>"
}}"""

        messages = [HumanMessage(content=prompt)]
        response = self.llm.invoke(messages)
        return self._parse_response(response.content)

    def order_tests(
        self,
        state: EncounterState,
        iteration: int,
        confidence: float,
        prior_iterations: List[ClinicalIteration]
    ) -> Dict[str, Any]:
        """
        Legacy method - Order diagnostic tests during concurrent review.
        Delegates to determine_action for friction model compatibility.
        """
        return self.determine_action(state, iteration, prior_iterations)

    def submit_appeal(
        self,
        state: EncounterState,
        denial: UtilizationReviewDecision
    ) -> Dict[str, Any]:
        """
        Submit appeal with peer-to-peer justification.

        Returns dict with:
        - appeal_type: str
        - additional_evidence: str
        - severity_documentation: str
        - guideline_references: List[str]
        """
        policy_view = state.provider_policy_view or {}

        prompt = f"""{self.SYSTEM_PROMPT}

APPEAL SUBMISSION - Peer-to-Peer Review

YOUR POLICY REFERENCE: {policy_view.get('policy_name', 'Clinical Guidelines')}

DENIAL REASON:
{denial.denial_reason}

PATIENT CLINICAL DATA:
{self._format_clinical_presentation(state)}

AVAILABLE EVIDENCE:
{self._format_clinical_evidence(state)}

CRITICAL: The Insurer denied based on strict numeric thresholds you may not know.
Your appeal must cite SPECIFIC objective values that demonstrate severity.

APPEAL REQUIREMENTS:
- Cite specific lab values and vital signs with numbers
- Document severity indicators and organ dysfunction
- Reference clinical guidelines or criteria
- Explain why observation level is insufficient

RESPONSE FORMAT (JSON):
{{
    "appeal_type": "peer_to_peer",
    "additional_evidence": "<specific clinical data with values>",
    "severity_documentation": "<severity indicators>",
    "guideline_references": ["<guideline>", ...]
}}"""

        messages = [HumanMessage(content=prompt)]
        response = self.llm.invoke(messages)
        return self._parse_response(response.content)

    def _format_criteria(self, criteria: List[str]) -> str:
        if not criteria:
            return "No specific criteria provided"
        return "\n".join([f"- {c}" for c in criteria])

    def _format_clinical_presentation(self, state: EncounterState) -> str:
        presentation = state.clinical_presentation
        demographics = state.admission.patient_demographics
        return f"""Age: {demographics.age}
Sex: {demographics.sex}
Chief Complaint: {presentation.chief_complaint}
History: {presentation.history_of_present_illness}
Vitals: {presentation.vital_signs}
Physical Exam: {presentation.physical_exam_findings}
Medical History: {', '.join(presentation.medical_history)}"""

    def _format_prior_iterations(self, iterations: List[ClinicalIteration]) -> str:
        if not iterations:
            return "No prior test orders"

        lines = []
        for iter in iterations:
            lines.append(f"Iteration {iter.iteration_number}:")
            lines.append(f"  Action: {iter.action_type}")
            lines.append(f"  Tests ordered: {iter.tests_ordered}")
            lines.append(f"  Approved: {iter.tests_approved}")
            lines.append(f"  Denied: {iter.tests_denied}")
        return "\n".join(lines)

    def _format_clinical_evidence(self, state: EncounterState) -> str:
        if not state.provider_documentation:
            return "No clinical documentation available"

        lines = []
        doc = state.provider_documentation

        if doc.lab_results:
            lines.append("LAB RESULTS:")
            for lab in doc.lab_results:
                lines.append(f"  - {lab.test_name}: {lab.result_summary}")

        if doc.imaging_results:
            lines.append("\nIMAGING RESULTS:")
            for img in doc.imaging_results:
                lines.append(f"  - {img.exam_name}: {img.impression}")

        if doc.severity_indicators:
            lines.append("\nSEVERITY INDICATORS:")
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
        except:
            pass

        return {
            "action_type": "abandon",
            "tests_ordered": [],
            "differential_diagnoses": [],
            "reasoning": "Error parsing response"
        }

    def make_decision(self, state: EncounterState) -> Dict[str, Any]:
        """Make strategic decision based on game state (stub implementation)."""
        return {"action": "order_tests", "state": "clinical_care"}

    def calculate_payoff(self, state: EncounterState) -> float:
        """Calculate utility/payoff from game outcome (stub implementation)."""
        if state.financial_settlement:
            return state.financial_settlement.hospital_margin
        return 0.0

    def calculate_metrics(self, state: EncounterState) -> Dict[str, float]:
        """Calculate agent-specific metrics (stub implementation)."""
        metrics = {
            "iterations_count": len(state.provider_documentation.iterations) if state.provider_documentation else 0,
            "appeal_filed": float(state.appeal_filed),
            "appeal_successful": float(state.appeal_successful)
        }
        return metrics
