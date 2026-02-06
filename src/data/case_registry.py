"""
case registry - central loading of all simulation cases from JSON files
"""
import json
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"
CASE_PATHS = {
    "infliximab_crohns_2015": CASES_DIR / "specialty_medications" / "infliximab_crohns_case_a.json",
}

def get_case(case_id: str):
    """retrieve case by id from JSON file"""
    if case_id not in CASE_PATHS:
        raise ValueError(f"case {case_id} not found in registry. available: {list(CASE_PATHS.keys())}")

    case_path = CASE_PATHS[case_id]
    with open(case_path, 'r') as f:
        return json.load(f)

def list_cases():
    """list all registered case ids"""
    return list(CASE_PATHS.keys())

def get_cases_by_type(case_type: str):
    """get all cases of a specific case type"""
    matching_cases = []
    for case_id in CASE_PATHS:
        case_data = get_case(case_id)
        if case_data.get("case_type") == case_type:
            matching_cases.append(case_id)
    return matching_cases
