"""
Smoke-test a minimal Phase 3 interaction with deterministic fake LLMs.
Run: python tests/test_smoke_interaction.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.data.case_registry import get_case
from src.data.case_converter import convert_case_to_models
from src.models.authorization import AuthorizationRequest
from src.models.state import EncounterState
from src.simulation.phases.unified_review import run_unified_multi_level_review
from src.utils.audit_logger import AuditLogger
from src.utils.prompts import (
    create_unified_phase3_provider_request_prompt,
    create_unified_phase3_payor_review_prompt,
)


@dataclass
class _FakeResponse:
    content: str
    additional_kwargs: dict[str, Any]


class _FakeLLM:
    def __init__(self, role: str):
        self.role = role

    @staticmethod
    def _extract_amount_billed(prompt: str) -> float | None:
        for line in prompt.splitlines():
            if "Amount Billed:" not in line:
                continue
            match = re.search(r"\$([\d,]+(?:\.\d{2})?)", line)
            if not match:
                continue
            return float(match.group(1).replace(",", ""))
        return None

    def invoke(self, messages):
        prompt = messages[0].content if messages else ""

        if "DRAFT TO REVIEW:" in prompt and "Return JSON" in prompt:
            payload = {
                "needs_editing": False,
                "review_notes": "draft is acceptable",
                "revised_text": None,
                "changes_made": [],
            }
            return _FakeResponse(json.dumps(payload), {})

        if self.role == "provider_copilot":
            payload = {
                "internal_rationale": {
                    "reasoning": "Submit itemized claim for approved medication.",
                    "documentation_completeness": "complete",
                },
                "insurer_request": {
                    "diagnosis_codes": [{"icd10": "K50.012", "description": "Crohn's"}],
                    "procedure_codes": [
                        {"code": "J1745", "code_type": "J-code", "description": "Infliximab", "requested_quantity": 10, "charge_amount": 100.0},
                        {"code": "96413", "code_type": "CPT", "description": "Infusion", "requested_quantity": 1, "charge_amount": 250.0},
                    ],
                    "total_amount_billed": 1250.0,
                    "clinical_notes": "Infliximab infusion administered as authorized.",
                    "discharge_summary": "Outpatient infusion visit.",
                    "supporting_documentation": "Infusion record and MAR.",
                },
            }
            return _FakeResponse(json.dumps(payload), {})

        if self.role == "payor_copilot":
            amount_billed = self._extract_amount_billed(prompt)
            has_lines = "Procedure Codes Submitted:" in prompt
            status = "approved" if amount_billed and amount_billed > 0 and has_lines else "denied"
            payload = {
                "action": status,
                "total_paid_amount": amount_billed if status == "approved" else 0.0,
                "criteria_used": "Test criteria",
            }
            return _FakeResponse(json.dumps(payload), {})

        return _FakeResponse("{}", {})


class _DummySim:
    def __init__(self, case_id: str):
        self.provider_params = {"oversight_intensity": "low"}
        self.payor_params = {"oversight_intensity": "low"}
        self.master_seed = 1
        self.audit_logger = AuditLogger(case_id=case_id)
        self.provider_copilot = _FakeLLM("provider_copilot")
        self.payor_copilot = _FakeLLM("payor_copilot")
        self.provider_copilot_name = "fake"
        self.payor_copilot_name = "fake"
        self.provider_base_llm = _FakeLLM("oversight")
        self.payor_base_llm = _FakeLLM("oversight")
        self.test_result_cache = {}

    def _generate_test_result(self, _test_name, _case):
        return {"value": "normal"}


def main() -> int:
    case_id = "infliximab_crohns_2015"
    case = convert_case_to_models(get_case(case_id))
    state = EncounterState(
        case_id=case["case_id"],
        admission=case["admission"],
        clinical_presentation=case["clinical_presentation"],
        case_type=case["case_type"],
    )
    # avoid policy warnings in preflight output
    state.provider_policy_view = {"policy_name": "stub", "content": {"data": {}}}
    state.payor_policy_view = {"policy_name": "stub", "content": {"data": {}}}
    state.authorization_request = AuthorizationRequest(
        request_type="treatment",
        service_name="Infliximab",
        clinical_rationale="test",
        diagnosis_codes=["K50.012"],
        authorization_status="approved",
    )

    sim = _DummySim(case_id)
    state = run_unified_multi_level_review(
        sim=sim,
        state=state,
        case=case,
        phase="phase_3_claims",
        provider_prompt_fn=create_unified_phase3_provider_request_prompt,
        payor_prompt_fn=create_unified_phase3_payor_review_prompt,
        provider_prompt_kwargs={
            "service_request": {"medication_name": "Infliximab", "dosage": "5 mg/kg"},
            "cost_ref": case.get("cost_reference", {}),
            "phase_2_evidence": {},
            "case_type": case["case_type"],
            "coding_options": [],
        },
        payor_prompt_kwargs={
            "service_request": {"medication_name": "Infliximab", "dosage": "5 mg/kg"},
            "cost_ref": None,
            "case": case,
            "phase_2_evidence": {},
            "case_type": case["case_type"],
            "provider_billed_amount": None,
        },
        max_iterations=3,
    )

    interactions = sim.audit_logger.get_audit_log().interactions
    provider_req = [
        i for i in interactions
        if i.phase == "phase_3_claims"
        and i.agent == "provider"
        and (i.parsed_output or {}).get("procedure_codes")
    ]
    if not provider_req:
        print("Missing provider claim submission with procedure codes.")
        return 1
    payor_review = [
        i for i in interactions
        if i.phase == "phase_3_claims"
        and i.agent == "payor"
        and (i.parsed_output or {}).get("authorization_status") == "approved"
    ]
    if not payor_review:
        print("Missing approved payor decision in Phase 3.")
        return 1
    if state.claim_rejected:
        print("Claim was rejected in smoke test (expected approved).")
        return 1

    print("Smoke interaction test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
