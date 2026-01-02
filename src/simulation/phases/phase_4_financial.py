"""
phase 4: financial settlement based on CLAIM outcome (not PA outcome)

KEY: payment only happens if CLAIM approved in phase 3
PA approval does NOT guarantee payment
"""

from typing import Dict, Any
from datetime import timedelta

from src.models.schemas import EncounterState, MedicationFinancialSettlement


def run_phase_4_financial(
    state: EncounterState,
    case: Dict[str, Any]
) -> EncounterState:
    """
    phase 4: financial settlement based on CLAIM outcome (not PA outcome)

    KEY: payment only happens if CLAIM approved in phase 3
    PA approval does NOT guarantee payment
    """
    state.settlement_date = (state.appeal_date or state.review_date) + timedelta(days=7)

    cost_ref = case.get("cost_reference", {})

    # payment based on CLAIM outcome (phase 3), not PA outcome (phase 2)
    claim_approved = (
        state.medication_authorization and
        state.medication_authorization.authorization_status == "approved"
    )

    if claim_approved:
        # use Provider's actual billed amount from Phase 3 if available (DRG upcoding scenarios)
        if state.phase_3_billed_amount is not None:
            total_cost = state.phase_3_billed_amount
            # for DRG-based billing, acquisition_cost IS the billed amount (no separate admin fee)
            acquisition_cost = total_cost
            admin_fee = 0.0
        else:
            # fallback to cost_ref for non-DRG cases (e.g., specialty medications)
            acquisition_cost = cost_ref.get("drug_acquisition_cost", 7800.0)
            admin_fee = cost_ref.get("administration_fee", 150.0)
            total_cost = acquisition_cost + admin_fee

        # typical MA copay: 20% patient, 80% plan
        patient_copay = total_cost * 0.20
        payer_payment = total_cost * 0.80
    else:
        # claim denied - provider gets $0 even though they already treated patient
        if state.phase_3_billed_amount is not None:
            total_cost = state.phase_3_billed_amount
            acquisition_cost = total_cost
            admin_fee = 0.0
        else:
            acquisition_cost = cost_ref.get("drug_acquisition_cost", 7800.0)
            admin_fee = cost_ref.get("administration_fee", 150.0)
            total_cost = acquisition_cost + admin_fee
        patient_copay = 0.0
        payer_payment = 0.0

    # administrative costs: PA review + claim review + appeals
    pa_review_cost = cost_ref.get("pa_review_cost", 75.0)
    claim_review_cost = cost_ref.get("claim_review_cost", 50.0)
    appeal_cost = 0.0
    if state.appeal_filed:
        appeal_cost = cost_ref.get("appeal_cost", 180.0)

    total_admin_cost = pa_review_cost + claim_review_cost + appeal_cost

    state.medication_financial = MedicationFinancialSettlement(
        medication_name=case.get("medication_request", {}).get("medication_name", "Unknown"),
        j_code=case.get("medication_request", {}).get("j_code"),
        acquisition_cost=acquisition_cost,
        administration_fee=admin_fee,
        total_billed=total_cost,
        payer_payment=payer_payment,
        patient_copay=patient_copay,
        prior_auth_cost=pa_review_cost + claim_review_cost,
        appeal_cost=appeal_cost,
        total_administrative_cost=total_admin_cost
    )

    return state
