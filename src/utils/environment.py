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
        pv = getattr(state, "patient_visible_data", None)
        ht = getattr(state, "environment_hidden_data", None)

        if not isinstance(pv, dict):
            raise ValueError("state.patient_visible_data must be dict")
        if ht is None:
            ht = {}
        if not isinstance(ht, dict):
            raise ValueError("state.environment_hidden_data must be dict")

        pv.setdefault("lab_results", {})
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
            if (getattr(line, "authorization_status", "") or "").lower() != "approved":
                continue
            if getattr(line, "delivered", False):
                continue

            line.delivered = True

            proc = getattr(line, "procedure_code", None)
            before = dict(pv["lab_results"])

            payload = results_by_code.get(proc) if proc else None
            fabricated = False
            raw_llm_output: Optional[str] = None

            if payload is None and self.allow_synthesis:
                if self.synthesis_llm is None:
                    raise ValueError("allow_synthesis=True but synthesis_llm is None")

                prompt = f"""Return ONLY valid JSON:
{{
  "lab_results_delta": {{
    "<lab_name>": {{"value": <number>, "units": "<units>"}}
    OR
    "<lab_name>": {{"result": "<qualitative result>"}}
  }}
}}

Constraints:
- procedure_code={proc!r}
- at most {self.max_labs_per_test} entries
- ONLY new keys (do not overwrite existing labs)
"""
                raw_llm_output = self.synthesis_llm.invoke(prompt).content
                import json
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

        return deltas
