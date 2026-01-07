"""
DEPRECATED: This module is kept for backward compatibility.
Import from src.models instead.The schemas have been split into smaller modules:
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
    ServiceLineItem,
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
