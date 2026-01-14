"""build and update ServiceLineRequest objects from provider responses"""
from typing import Dict, Any, List

from src.models import EncounterState, ServiceLineRequest


def create_or_update_service_line_from_approval(
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any],
    request_type: str
) -> None:
    """
    create or update ServiceLineRequest when treatment/level_of_care is approved.

    this is for Phase 2 terminal approvals (TREATMENT or LEVEL_OF_CARE).
    For MVP: single service line only (list with 1 element).
    """
    # extract service details from provider_request
    if "requested_service" not in provider_request:
        raise ValueError("provider_request missing required field 'requested_service'")
    requested_service = provider_request["requested_service"]
    if not isinstance(requested_service, dict):
        raise ValueError("provider_request.requested_service must be a dict")
    if "service_name" not in requested_service or not requested_service["service_name"]:
        raise ValueError("requested_service missing required field 'service_name'")
    service_name = requested_service["service_name"]
    if "clinical_evidence" in requested_service:
        clinical_rationale = requested_service["clinical_evidence"]
    elif "severity_indicators" in requested_service:
        clinical_rationale = requested_service["severity_indicators"]
    else:
        raise ValueError("requested_service missing required field 'clinical_evidence' or 'severity_indicators'")

    diagnosis_codes = []
    if "diagnosis_codes" in provider_request:
        if not isinstance(provider_request["diagnosis_codes"], list):
            raise ValueError("provider_request.diagnosis_codes must be a list")
        for diag in provider_request["diagnosis_codes"]:
            if isinstance(diag, dict):
                if "icd10" not in diag or not diag["icd10"]:
                    raise ValueError("diagnosis_codes entry missing required field 'icd10'")
                diagnosis_codes.append(diag["icd10"])
            elif isinstance(diag, str):
                diagnosis_codes.append(diag)
            else:
                raise ValueError("diagnosis_codes entries must be dicts or strings")

    procedure_code = requested_service.get("procedure_code")
    cpt_code = requested_service.get("cpt_code")
    ndc_code = requested_service.get("ndc_code")
    j_code = requested_service.get("j_code")
    if not any([procedure_code, cpt_code, ndc_code, j_code]):
        raise ValueError("requested_service missing required procedure code field")

    # create or update first service line (MVP: single line)
    if not state.service_lines:
        service_line = ServiceLineRequest(
            line_number=1,
            procedure_code=procedure_code or cpt_code or ndc_code or j_code,
            code_type="CPT",  # default, will be refined
            service_description=service_name,
            requested_quantity=1,  # default
            diagnosis_codes=diagnosis_codes
        )
        state.service_lines.append(service_line)
    else:
        # update existing service line
        service_line = state.service_lines[0]
        service_line.service_description = service_name
        service_line.diagnosis_codes = diagnosis_codes

    # populate fields from requested_service
    service_line.request_type = request_type
    service_line.service_name = service_name
    service_line.clinical_rationale = clinical_rationale

    # extract coding information (CPT, NDC, J-code)
    service_line.cpt_code = cpt_code or procedure_code
    service_line.ndc_code = ndc_code
    service_line.j_code = j_code

    # determine code_type based on what's present
    if service_line.j_code:
        service_line.code_type = "J-code"
        service_line.procedure_code = service_line.j_code
    elif service_line.ndc_code:
        service_line.code_type = "NDC"
        service_line.procedure_code = service_line.ndc_code
    elif service_line.cpt_code:
        service_line.code_type = "CPT"
        service_line.procedure_code = service_line.cpt_code

    # extract service details (dosage, frequency, etc.)
    service_line.dosage = requested_service.get("dosage")
    service_line.frequency = requested_service.get("frequency")
    service_line.duration = requested_service.get("duration")
    service_line.visit_count = requested_service.get("visit_count")
    service_line.site_of_service = requested_service.get("site_of_service")

    # set payor decision fields for Phase 2
    service_line.authorization_status = "approved"
    if "decision_reason" in payor_decision and payor_decision["decision_reason"]:
        service_line.decision_reason = payor_decision["decision_reason"]

    # handle approved quantity
    approved_quantity = payor_decision.get("approved_quantity_amount")
    if approved_quantity is None:
        approved_quantity = payor_decision.get("approved_quantity")
    service_line.approved_quantity = approved_quantity

    # set reviewer metadata
    if "reviewer_type" in payor_decision and payor_decision["reviewer_type"]:
        service_line.reviewer_type = payor_decision["reviewer_type"]
    if "level" in payor_decision:
        service_line.current_review_level = payor_decision["level"]


def finalize_service_line_after_non_approval(
    state: EncounterState,
    provider_request: Dict[str, Any],
    last_payor_action: str,
    phase: str,
    current_level: int,
    level_config: Dict[str, Any]
) -> None:
    """
    finalize service line when Phase 2 ends without approval (deny/pend/abandon).

    Creates minimal service line to track what was requested and final status.
    For MVP: single service line only.
    """
    # extract basic info from last request if available
    last_request_type = None
    last_service_name = None
    last_clinical_rationale = None
    last_diagnosis_codes = None

    if provider_request:
        if "request_type" not in provider_request or not provider_request["request_type"]:
            raise ValueError("provider_request missing required field 'request_type'")
        last_request_type = provider_request["request_type"]
        if "requested_service" not in provider_request:
            raise ValueError("provider_request missing required field 'requested_service'")
        requested_service = provider_request["requested_service"]
        if not isinstance(requested_service, dict):
            raise ValueError("provider_request.requested_service must be a dict")
        if "service_name" not in requested_service or not requested_service["service_name"]:
            raise ValueError("requested_service missing required field 'service_name'")
        last_service_name = requested_service["service_name"]
        if "clinical_evidence" in requested_service:
            last_clinical_rationale = requested_service["clinical_evidence"]
        elif "severity_indicators" in requested_service:
            last_clinical_rationale = requested_service["severity_indicators"]
        else:
            raise ValueError("requested_service missing required field 'clinical_evidence' or 'severity_indicators'")
        if "diagnosis_codes" in provider_request:
            if not isinstance(provider_request["diagnosis_codes"], list):
                raise ValueError("provider_request.diagnosis_codes must be a list")
            last_diagnosis_codes = []
            for diag in provider_request["diagnosis_codes"]:
                if isinstance(diag, dict):
                    if "icd10" not in diag or not diag["icd10"]:
                        raise ValueError("diagnosis_codes entry missing required field 'icd10'")
                    last_diagnosis_codes.append(diag["icd10"])
                elif isinstance(diag, str):
                    last_diagnosis_codes.append(diag)
                else:
                    raise ValueError("diagnosis_codes entries must be dicts or strings")

    # create service line if doesn't exist
    if not state.service_lines:
        if last_request_type is None:
            raise ValueError("cannot finalize service line without provider_request details")
        service_line = ServiceLineRequest(
            line_number=1,
            procedure_code="",
            code_type="CPT",
            service_description=last_service_name,
            requested_quantity=1,
            request_type=last_request_type,
            service_name=last_service_name,
            clinical_rationale=last_clinical_rationale,
            diagnosis_codes=last_diagnosis_codes
        )
        state.service_lines.append(service_line)
    else:
        service_line = state.service_lines[0]

    # set authorization status based on last payor decision
    service_line.authorization_status = last_payor_action

    # set denial reason based on outcome
    if last_payor_action == "denied":
        service_line.decision_reason = f"{phase}: max iterations reached without approval"
    elif last_payor_action == "pending_info":
        service_line.decision_reason = f"{phase}: provider abandoned after pend"
    elif last_payor_action == "modified":
        service_line.decision_reason = f"{phase}: provider abandoned after modification"

    service_line.reviewer_type = level_config["role_label"]
    service_line.current_review_level = current_level
