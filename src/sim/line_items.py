from __future__ import annotations

from typing import Any, Dict, List

from src.models.financial import ServiceLineRequest

#internal
_ALLOWED_CODE_TYPES = {
    "CPT",
    "HCPCS",
    "J-CODE",
    "J_CODE",
    "JCODE",
    "NDC",
}


def _normalize_code_type(code_type: str) -> str:
    ct = str(code_type).strip().upper()
    if ct not in _ALLOWED_CODE_TYPES:
        raise ValueError(f"unsupported code_type={code_type}")
    if ct in {"J_CODE", "JCODE"}:
        return "J-code"
    if ct == "J-CODE":
        return "J-code"
    return ct


def ensure_phase2_service_lines(state, insurer_request: Dict[str, Any]) -> None:
    if getattr(state, "service_lines", None):
        return

    requested = insurer_request.get("requested_services")
    if not isinstance(requested, list) or not requested:
        raise ValueError("insurer_request.requested_services must be non-empty list")

    dx = insurer_request.get("diagnosis_codes")
    if not isinstance(dx, list):
        raise ValueError("insurer_request.diagnosis_codes must be list")

    icd10_codes: List[str] = []
    for item in dx:
        if isinstance(item, dict) and item.get("icd10"):
            icd10_codes.append(str(item["icd10"]))

    lines: List[ServiceLineRequest] = []
    for svc in requested:
        if not isinstance(svc, dict):
            raise ValueError("requested_services entries must be dict")

        for k in ("line_number", "request_type", "procedure_code", "code_type", "service_name", "requested_quantity", "quantity_unit"):
            if k not in svc:
                raise ValueError(f"requested_services missing {k}: {svc}")

        rt = str(svc["request_type"]).strip()
        code = str(svc["procedure_code"]).strip()
        ct = _normalize_code_type(svc["code_type"])
        name = str(svc["service_name"]).strip()

        rationale = ""
        if rt == "diagnostic_test":
            rationale = str(svc.get("test_justification") or "")
            exp = str(svc.get("expected_findings") or "")
            if exp:
                rationale = (rationale + " " + exp).strip()
        elif rt == "treatment":
            rationale = str(svc.get("clinical_evidence") or "")
        elif rt == "level_of_care":
            rationale = str(svc.get("severity_indicators") or "")
        else:
            raise ValueError(f"bad request_type: {rt}")

        line = ServiceLineRequest(
            line_number=int(svc["line_number"]),
            procedure_code=code,
            code_type=ct,
            service_description=name,
            requested_quantity=int(svc["requested_quantity"]),
            quantity_unit=str(svc["quantity_unit"]),
            charge_amount=float(svc["charge_amount"]) if svc.get("charge_amount") else None,
            diagnosis_codes=icd10_codes or None,
            clinical_rationale=rationale or None,
            request_type=rt,
            service_name=name or None,
        )

        if ct == "NDC":
            line.ndc_code = code
        elif ct == "J-code":
            line.j_code = code
        elif ct == "CPT":
            line.cpt_code = code

        lines.append(line)

    state.service_lines = lines
