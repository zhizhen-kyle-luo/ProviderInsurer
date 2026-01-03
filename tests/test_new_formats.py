"""
test script for new PA/claim formats and truth checker improvements
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
import pathlib
# load .env from MASH root directory
env_path = pathlib.Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from src.simulation.game_runner import UtilizationReviewSimulation
import json
import importlib.util

# load post-acure case (dash in directory name)
def _load_post_acure_case(filename, case_name):
    spec = importlib.util.spec_from_file_location(
        case_name,
        os.path.join(os.path.dirname(__file__), "..", "src", "data", "cases", "post-acure", filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, case_name)

test_case = _load_post_acure_case("snf_pulmonary_01.py", "SNF_PULMONARY_01")

def test_new_formats():
    """run single case to test new formats"""

    print("=== Testing New PA/Claim Formats and Truth Checker ===\n")

    # initialize game runner with baseline config
    runner = UtilizationReviewSimulation(
        provider_params={
            'patient_care_weight': 'high',
            'documentation_style': 'moderate',
            'risk_tolerance': 'moderate',
            'oversight_intensity': 'medium'
        },
        payor_params={
            'strictness': 'moderate',
            'time_horizon': 'short-term',
            'oversight_intensity': 'medium'
        },
        enable_cache=False  # disable cache for fresh test
    )

    print(f"Running case: {test_case['case_id']}")
    print(f"PA Type: {test_case['pa_type']}\n")

    # run simulation
    result = runner.run_case(test_case)

    # check phase 2 provider request format
    print("=== Phase 2 Provider Request Format ===")
    if result.audit_log and result.audit_log.interactions:
        for interaction in result.audit_log.interactions:
            if interaction.phase == "phase_2_pa" and interaction.agent == "provider":
                req = interaction.parsed_output
                print(f"\n✓ Found provider PA request")
                print(f"  - Has diagnosis_codes: {'diagnosis_codes' in req}")
                print(f"  - Has requested_service: {'requested_service' in req}")
                print(f"  - Has clinical_notes: {'clinical_notes' in req}")

                if 'diagnosis_codes' in req:
                    print(f"  - Diagnosis codes count: {len(req['diagnosis_codes'])}")
                    if req['diagnosis_codes']:
                        print(f"    Example: {req['diagnosis_codes'][0]}")

                if 'requested_service' in req:
                    svc = req['requested_service']
                    print(f"  - Has procedure_code: {'procedure_code' in svc}")
                    print(f"  - Has code_type: {'code_type' in svc}")

                if 'clinical_notes' in req:
                    notes_preview = req['clinical_notes'][:100] + "..." if len(req['clinical_notes']) > 100 else req['clinical_notes']
                    print(f"  - Clinical notes preview: {notes_preview}")
                break

    # check truth checker result
    print("\n=== Truth Checker Result ===")
    if result.truth_check_phase2:
        tc = result.truth_check_phase2
        print(f"\n✓ Truth check completed")
        print(f"  - Treatment category: {tc.treatment_category}")
        print(f"  - Is deceptive: {tc.is_deceptive}")
        print(f"  - Claims evaluated: {len(tc.claims_evaluated)}")
        print(f"  - Num supported: {tc.num_supported}")
        print(f"  - Num inferred: {tc.num_inferred}")
        print(f"  - Num contradicted: {tc.num_contradicted}")
        print(f"  - Has interaction_context: {bool(tc.interaction_context)}")

        if tc.claims_evaluated:
            print(f"\n  Example claim evaluation:")
            claim = tc.claims_evaluated[0]
            print(f"    - Claim: {claim.claim[:80]}...")
            print(f"    - Classification: {claim.classification}")
            print(f"    - Reasoning: {claim.reasoning[:80]}...")

    # check phase 3 claim format (if reached)
    print("\n=== Phase 3 Claim Format ===")
    if result.audit_log:
        for interaction in result.audit_log.interactions:
            if interaction.phase == "phase_3_claims" and interaction.agent == "provider":
                claim = interaction.parsed_output
                if 'claim_submission' in claim:
                    cs = claim['claim_submission']
                    print(f"\n✓ Found claim submission")
                    print(f"  - Has diagnosis_codes: {'diagnosis_codes' in cs}")
                    print(f"  - Has procedure_codes: {'procedure_codes' in cs}")
                    print(f"  - Has clinical_evidence: {'clinical_evidence' in cs}")
                    print(f"  - Has clinical_notes: {'clinical_notes' in cs}")

                    if 'procedure_codes' in cs and cs['procedure_codes']:
                        print(f"  - Procedure codes count: {len(cs['procedure_codes'])}")
                        print(f"    Example: {cs['procedure_codes'][0]}")
                break

    print("\n=== Test Complete ===")
    print(f"Final outcome: PA {result.medication_authorization.authorization_status if result.medication_authorization else 'N/A'}")

    return result

if __name__ == "__main__":
    result = test_new_formats()
