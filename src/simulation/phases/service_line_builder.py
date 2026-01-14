"""build and update ServiceLineRequest objects from provider responses"""
from typing import Dict, Any, List

from src.models import EncounterState, ServiceLineRequest


def _extract_diagnosis_codes(provider_request: Dict[str, Any]) -> List[str]:
    """extract diagnosis codes from provider request"""
    diagnosis_codes = []
    if "diagnosis_codes" not in provider_request:
        return diagnosis_codes

    raw_codes = provider_request["diagnosis_codes"]
    if not isinstance(raw_codes, list):
        raise ValueError("provider_request.diagnosis_codes must be a list")

    for diag in raw_codes:
        if isinstance(diag, dict):
            if "icd10" not in diag or not diag["icd10"]:
                raise ValueError("diagnosis_codes entry missing required field 'icd10'")
            diagnosis_codes.append(diag["icd10"])
        elif isinstance(diag, str):
            diagnosis_codes.append(diag)
        else:
            raise ValueError("diagnosis_codes entries must be dicts or strings")
    return diagnosis_codes


def _get_clinical_rationale(requested_service: Dict[str, Any]) -> str:
    """extract clinical rationale from requested service based on request type"""
    if "clinical_evidence" in requested_service:
        return requested_service["clinical_evidence"]
    if "severity_indicators" in requested_service:
        return requested_service["severity_indicators"]
    if "test_justification" in requested_service:
        return requested_service["test_justification"]
    raise ValueError("requested_service missing clinical rationale field")


def _get_procedure_code(requested_service: Dict[str, Any]) -> tuple[str, str]:
    """extract procedure code and type from requested service, returns (code, code_type)"""
    procedure_code = requested_service.get("procedure_code")
    cpt_code = requested_service.get("cpt_code")
    ndc_code = requested_service.get("ndc_code")
    j_code = requested_service.get("j_code")

    if j_code:
        return j_code, "J-code"
    if ndc_code:
        return ndc_code, "NDC"
    if cpt_code:
        return cpt_code, "CPT"
    if procedure_code:
        code_type = requested_service.get("code_type", "CPT")
        return procedure_code, code_type

    raise ValueError("requested_service missing required procedure code field")


def _create_service_line_from_requested_service(
    requested_service: Dict[str, Any],
    line_number: int,
    diagnosis_codes: List[str],
    request_type: str
) -> ServiceLineRequest:
    """create a ServiceLineRequest from a requested_service dict"""
    if "service_name" not in requested_service or not requested_service["service_name"]:
        raise ValueError("requested_service missing required field 'service_name'")

    service_name = requested_service["service_name"]
    clinical_rationale = _get_clinical_rationale(requested_service)
    procedure_code, code_type = _get_procedure_code(requested_service)

    service_line = ServiceLineRequest(
        line_number=line_number,
        procedure_code=procedure_code,
        code_type=code_type,
        service_description=service_name,
        requested_quantity=requested_service.get("requested_quantity", 1),
        diagnosis_codes=diagnosis_codes,
        request_type=request_type,
        service_name=service_name,
        clinical_rationale=clinical_rationale
    )

    # optional fields
    service_line.cpt_code = requested_service.get("cpt_code") or requested_service.get("procedure_code")
    service_line.ndc_code = requested_service.get("ndc_code")
    service_line.j_code = requested_service.get("j_code")
    service_line.dosage = requested_service.get("dosage")
    service_line.frequency = requested_service.get("frequency")
    service_line.duration = requested_service.get("duration")
    service_line.visit_count = requested_service.get("visit_count")
    service_line.site_of_service = requested_service.get("site_of_service")

    return service_line


def create_service_lines_from_provider_request(
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any]
) -> None:
    """
    create or update ServiceLineRequests from provider request with multiple services.
    applies payor decision metadata to all created lines.
    """
    diagnosis_codes = _extract_diagnosis_codes(provider_request)

    if "requested_services" not in provider_request:
        raise ValueError("provider_request missing required field 'requested_services'")
    requested_services = provider_request["requested_services"]
    if not isinstance(requested_services, list) or not requested_services:
        raise ValueError("provider_request.requested_services must be a non-empty list")

    # create service lines for each requested service
    for svc in requested_services:
        if "line_number" not in svc:
            raise ValueError("requested_service missing required field 'line_number'")
        line_number = svc["line_number"]

        if "request_type" not in svc:
            raise ValueError("requested_service missing required field 'request_type'")
        request_type = svc["request_type"]

        # check if line already exists
        existing_line = None
        for line in state.service_lines:
            if line.line_number == line_number:
                existing_line = line
                break

        if existing_line:
            # update existing line
            existing_line.service_name = svc.get("service_name", existing_line.service_name)
            existing_line.diagnosis_codes = diagnosis_codes
            existing_line.request_type = request_type
            if svc.get("clinical_evidence") or svc.get("severity_indicators") or svc.get("test_justification"):
                existing_line.clinical_rationale = _get_clinical_rationale(svc)
        else:
            # create new line
            service_line = _create_service_line_from_requested_service(
                requested_service=svc,
                line_number=line_number,
                diagnosis_codes=diagnosis_codes,
                request_type=request_type
            )
            state.service_lines.append(service_line)

    # apply payor decision metadata to all lines
    reviewer_type = payor_decision.get("reviewer_type")
    level = payor_decision.get("level")
    for line in state.service_lines:
        if reviewer_type:
            line.reviewer_type = reviewer_type
        if level is not None:
            line.current_review_level = level


def create_or_update_service_line_from_approval(
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any],
    request_type: str  # kept for backwards compatibility, extracted from provider_request now
) -> None:
    """
    create or update ServiceLineRequest when treatment/level_of_care is approved.

    delegates to create_service_lines_from_provider_request for multi-line support.
    """
    _ = request_type  # unused, request_type now per-service in requested_services
    create_service_lines_from_provider_request(state, provider_request, payor_decision)


def finalize_service_lines_after_non_approval(
    state: EncounterState,
    provider_request: Dict[str, Any],
    phase: str,
    current_level: int,
    level_config: Dict[str, Any]
) -> None:
    """
    finalize service lines when Phase 2 ends without approval (deny/pend/abandon).

    creates minimal service lines to track what was requested and final status.
    """
    if not provider_request:
        raise ValueError("cannot finalize service lines without provider_request")

    diagnosis_codes = _extract_diagnosis_codes(provider_request)

    if "requested_services" not in provider_request:
        raise ValueError("provider_request missing required field 'requested_services'")
    requested_services = provider_request["requested_services"]
    if not isinstance(requested_services, list) or not requested_services:
        raise ValueError("provider_request.requested_services must be a non-empty list")

    # create service lines if they don't exist
    for svc in requested_services:
        line_number = svc.get("line_number", 1)
        request_type = svc.get("request_type")
        if not request_type:
            raise ValueError("requested_service missing required field 'request_type'")

        # check if line exists
        existing = None
        for line in state.service_lines:
            if line.line_number == line_number:
                existing = line
                break

        if not existing:
            service_line = _create_service_line_from_requested_service(
                requested_service=svc,
                line_number=line_number,
                diagnosis_codes=diagnosis_codes,
                request_type=request_type
            )
            state.service_lines.append(service_line)

    # set metadata on all lines
    for line in state.service_lines:
        line.reviewer_type = level_config["role_label"]
        line.current_review_level = current_level


# backwards compatibility alias
finalize_service_line_after_non_approval = finalize_service_lines_after_non_approval
