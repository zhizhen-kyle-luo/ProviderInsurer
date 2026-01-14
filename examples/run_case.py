"""
run utilization review simulation for any case study

usage:
  python examples/run_case.py infliximab_crohns_2015
  python examples/run_case.py --all
  python examples/run_case.py infliximab_crohns_case_b chest_pain_stress_test_001
"""
import sys
import os
import argparse
from dotenv import load_dotenv
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.case_registry import get_case, list_cases
from src.data.case_converter import convert_case_to_models


def print_results(result):
    """print simulation results"""
    print("\n" + "=" * 80)
    print("SIMULATION RESULTS")
    print("=" * 80)

    print("\nphase 1: patient presentation")
    print(f"patient: {result.admission.patient_demographics.age}yo {result.admission.patient_demographics.sex}")
    if result.clinical_presentation.medical_history:
        print(f"history: {', '.join(result.clinical_presentation.medical_history[:2])}")

    print("\nphase 2: prior authorization")
    if result.service_lines:
        line = result.service_lines[0]
        print(f"authorization status: {line.authorization_status or 'N/A'}")
    else:
        print("no authorization request")

    print("\nphase 3: claims adjudication")
    if result.service_lines and result.service_lines[0].adjudication_status:
        line = result.service_lines[0]
        print(f"adjudication status: {line.adjudication_status}")
    else:
        print("no claim adjudication")

    print("\nphase 4: financial settlement")
    if result.financial_settlement:
        fin = result.financial_settlement
        print(f"total billed: ${fin.total_billed_charges:,.2f}")
        print(f"payer payment: ${fin.payer_payment:,.2f}")
        print(f"patient responsibility: ${fin.patient_responsibility:,.2f}")
        if hasattr(fin, 'total_administrative_cost'):
            print(f"admin cost: ${fin.total_administrative_cost:,.2f}")


def save_outputs(result, output_dir="outputs"):
    """save audit log (JSON and markdown)"""
    if not result.audit_log:
        print("\nno audit log generated")
        return

    os.makedirs(output_dir, exist_ok=True)

    # save JSON for viewer
    json_path = f"{output_dir}/{result.audit_log.case_id}_audit_log.json"
    result.audit_log.save_to_json(json_path)
    print(f"\naudit log (JSON): {json_path}")

    # save markdown for reference
    md_path = f"{output_dir}/{result.audit_log.case_id}_audit_log.md"
    result.audit_log.save_to_markdown(md_path)
    print(f"audit log (markdown): {md_path}")


def run_case(case_id: str):
    """run simulation for a single case"""
    print("=" * 80)
    print(f"case: {case_id}")
    print("=" * 80)

    case = get_case(case_id)
    print(f"patient: {case['patient_visible_data']['age']}yo {case['patient_visible_data']['sex']}")
    print(f"complaint: {case['patient_visible_data']['chief_complaint']}")
    case_type = case.get('case_type', 'unknown')
    print(f"case type: {case_type}")

    case = convert_case_to_models(case)

    # simulation uses env vars (AZURE_OPENAI_ENDPOINT, etc.)
    sim = UtilizationReviewSimulation()
    result = sim.run_case(case)

    print_results(result)
    save_outputs(result)

    return result


def main():
    parser = argparse.ArgumentParser(description='run utilization review simulation')
    parser.add_argument('cases', nargs='*', help='case ids to run')
    parser.add_argument('--all', action='store_true', help='run all registered cases')
    parser.add_argument('--output-dir', default='outputs', help='output directory')
    args = parser.parse_args()

    if args.all:
        case_ids = list_cases()
        print(f"\nrunning all {len(case_ids)} registered cases\n")
    elif args.cases:
        case_ids = args.cases
    else:
        print("error: specify case ids or use --all")
        print(f"\navailable cases: {', '.join(list_cases())}")
        sys.exit(1)

    results = []
    for case_id in case_ids:
        try:
            result = run_case(case_id)
            results.append(result)
            print("\n")
        except Exception as e:
            print(f"error running {case_id}: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 80)
    print(f"completed {len(results)}/{len(case_ids)} cases")
    print("=" * 80)


if __name__ == "__main__":
    main()
