"""
DEPRECATED: This module is kept for backward compatibility.
Import from src.models instead. The schemas have been split into smaller modules:
- src.models.case_types: CaseType constants
- src.models.patient: Patient demographics and clinical presentation
- src.models.clinical: Diagnostic tests and lab results
- src.models.authorization: AuthorizationRequest model
- src.models.financial: Financial settlement and claim line models
- src.models.metrics: FrictionMetrics
- src.models.state: EncounterState (main state object)
- src.models.audit: Audit logging models
"""

from .case_types import CaseType
from .patient import (
    PatientDemographics,
    InsuranceInfo,
    AdmissionNotification,
    ClinicalPresentation
)
from .clinical import (
    DiagnosticTest,
    LabResult,
    ImagingResult,
    TestOrdered
)
from .authorization import AuthorizationRequest
from .financial import (
    ClaimLineItem,  # NEW: line-level claim tracking (X12 837/835 aligned)
    ServiceLineItem,  # DEPRECATED: use ClaimLineItem for Phase 3
    DRGAssignment,
    FinancialSettlement
)
from .metrics import FrictionMetrics
from .state import EncounterState
from .audit import (
    Message,
    LLMInteraction,
    EnvironmentAction,
    AgentConfiguration,
    AuditLog
)

__all__ = [
    "CaseType",
    "PatientDemographics",
    "InsuranceInfo",
    "AdmissionNotification",
    "ClinicalPresentation",
    "DiagnosticTest",
    "LabResult",
    "ImagingResult",
    "TestOrdered",
    "AuthorizationRequest",
    "ServiceLineItem",
    "DRGAssignment",
    "FinancialSettlement",
    "FrictionMetrics",
    "EncounterState",
    "Message",
    "LLMInteraction",
    "EnvironmentAction",
    "AgentConfiguration",
    "AuditLog",
]
