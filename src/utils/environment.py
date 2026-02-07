from __future__ import annotations
from typing import Any, Dict, List, Optional
class Environment:
    def __init__(
        self,
        *,
        synthesis_llm=None,
        allow_synthesis: bool = True,
        max_labs_per_test: int = 5,
        audit_logger=None,
    ):
        self.synthesis_llm = synthesis_llm
        self.allow_synthesis = allow_synthesis
        self.max_labs_per_test = max_labs_per_test
        self.audit_logger = audit_logger

    def _log(self, *, state, phase: str, turn: int, kind: str, payload: Dict[str, Any]) -> None:
        if self.audit_logger is None:
            return
        try:
            self.audit_logger.log(
                phase=phase,
                turn=turn,
                kind=kind,
                actor="environment",
                payload=payload,
            )
        except Exception:
            pass

    def perform_approved_diagnostics(self, *, state) -> List[Dict[str, Any]]:
        import json

        pv_obj = getattr(state, "patient_visible_data", None)
        if pv_obj is None:
            raise ValueError("state.patient_visible_data is None")

        if hasattr(pv_obj, "model_dump"):
            pv = pv_obj.model_dump()
        elif isinstance(pv_obj, dict):
            pv = pv_obj
        else:
            raise ValueError("state.patient_visible_data must be PatientVisibleData model or dict")

        ht = getattr(state, "environment_hidden_data", None)
        if ht is None:
            ht = {}
        if not isinstance(ht, dict):
            raise ValueError("state.environment_hidden_data must be dict")

        if "lab_results" not in pv:
            pv["lab_results"] = {}
        if not isinstance(pv["lab_results"], dict):
            raise ValueError("patient_visible_data.lab_results must be dict")

        results_by_code = ht.get("diagnostic_results_by_code", {})
        if results_by_code is None:
            results_by_code = {}
        if not isinstance(results_by_code, dict):
            raise ValueError("environment_hidden_data.diagnostic_results_by_code must be dict")

        deltas: List[Dict[str, Any]] = []

        for line in getattr(state, "service_lines", []) or []:
            if getattr(line, "superseded_by_line", None) is not None:
                continue
            if (getattr(line, "request_type", "") or "").lower() != "diagnostic_test":
                continue

            status = (getattr(line, "authorization_status", "") or "").lower()
            if status in {"approved", "modified"}:
                pass
            else:
                continue

            proc = getattr(line, "procedure_code", None)
            if proc is None or str(proc).strip() == "":
                continue
            proc = str(proc)

            service_name = getattr(line, "service_name", None) or ""
            service_description = getattr(line, "service_description", None) or ""

            # If we already have ground-truth (or previously synthesized) results for this procedure,
            # skip when all expected labs are already present in the current patient-visible data.
            existing_payload = results_by_code.get(proc)
            if isinstance(existing_payload, dict) and existing_payload:
                missing = {k: v for k, v in existing_payload.items() if k not in pv["lab_results"]}
                if not missing:
                    continue

            before = dict(pv["lab_results"])

            payload = results_by_code.get(proc) if proc else None
            fabricated = False
            raw_llm_output: Optional[str] = None

            if payload is None and self.allow_synthesis:
                if self.synthesis_llm is None:
                    raise ValueError("allow_synthesis=True but synthesis_llm is None")

                pv_json = json.dumps(pv, ensure_ascii=False, indent=2)
                ht_json = json.dumps(ht, ensure_ascii=False, indent=2)

                prompt = f"""Generate simulated result for: {service_name}
Description: {service_description}

Patient context:
{pv_json}

Clinical context:
{ht_json}

Return ONLY valid JSON. Use EXACTLY one of these two formats:

For quantitative results (labs with numbers):
{{
  "lab_results_delta": {{
    "<snake_case_key>": {{"value": <number>, "units": "<string>"}}
  }}
}}

For qualitative results (positive/negative, or imaging findings):
{{
  "lab_results_delta": {{
    "<snake_case_key>": {{"result": "<string under 50 chars>"}}
  }}
}}

Rules:
- Key must be snake_case derived from service_name
- Return exactly one key-value pair
- No narratives or extra text outside the JSON
"""
                from langchain_core.messages import SystemMessage, HumanMessage
                resp = self.synthesis_llm.invoke([
                    SystemMessage(content="You are a medical lab result generator."),
                    HumanMessage(content=prompt)
                ])
                raw_llm_output = resp.content
                try:
                    obj = json.loads(raw_llm_output)
                except Exception:
                    from src.utils.json_parsing import extract_json_from_text
                    obj = extract_json_from_text(raw_llm_output)

                if not isinstance(obj, dict) or not isinstance(obj.get("lab_results_delta"), dict):
                    raise ValueError("synthesis_llm returned invalid lab_results_delta JSON")

                payload = obj["lab_results_delta"]
                fabricated = True

            if payload is None:
                self._log(
                    state=state,
                    phase="phase_2_utilization_review",
                    turn=int(getattr(state, "turn", 0)),
                    kind="env_diagnostic_no_results",
                    payload={"line_number": line.line_number, "procedure_code": proc},
                )
                continue

            if not isinstance(payload, dict):
                raise ValueError("diagnostic result payload must be dict")

            # don't overwrite existing labs
            payload = {k: v for k, v in payload.items() if k not in pv["lab_results"]}

            pv["lab_results"].update(payload)

            self._log(
                state=state,
                phase="phase_2_utilization_review",
                turn=int(getattr(state, "turn", 0)),
                kind="env_patient_visible_update",
                payload={
                    "source": "llm_synthesized" if fabricated else "ground_truth",
                    "fabricated": fabricated,
                    "line_number": line.line_number,
                    "procedure_code": proc,
                    "labs_added": payload,
                    "raw_llm_output": raw_llm_output,
                },
            )

            deltas.append(
                {
                    "kind": "patient_visible_update",
                    "source": "llm_synthesized" if fabricated else "ground_truth",
                    "fabricated": fabricated,
                    "line_number": line.line_number,
                    "procedure_code": proc,
                    "before": before,
                    "after": dict(pv["lab_results"]),
                }
            )

        from src.models.patient import PatientVisibleData
        state.patient_visible_data = PatientVisibleData(**pv)

        return deltas
