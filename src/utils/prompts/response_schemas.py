from __future__ import annotations

from typing import Any, Dict, List

PHASE2_PROVIDER_EXAMPLE: Dict[str, Any] = {
    "insurer_request": {
        "diagnosis_codes": [{"icd10": "K50.90", "description": "Crohn's"}],
        "requested_services": [
            {
                "line_number": 1,
                "request_type": "treatment",
                "procedure_code": "J1745",
                "code_type": "J-code",
                "service_name": "infliximab infusion",
                "requested_quantity": 1,
                "clinical_evidence": "justification",
            }
        ],
        "clinical_notes": "short narrative",
    }
}

PHASE2_PAYOR_EXAMPLE: Dict[str, Any] = {
    "line_adjudications": [
        {
            "line_number": 1,
            "authorization_status": "approved",
            "decision_reason": "meets criteria",
            "approved_quantity": 1,
            "authorization_number": "AUTH123",
            "modification_type": None,
            "requested_documents": [],
        }
    ],
    "reviewer_type": "UM Triage",
    "level": 0,
}
