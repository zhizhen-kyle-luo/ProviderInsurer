"""
test result generation for utilization review simulation

generates deterministic test results using:
1. pre-defined templates from case data
2. LLM generation with environment_hidden_data as ground truth
3. environment-based pattern matching
"""

from typing import Dict, Any
from langchain_core.messages import HumanMessage


def generate_test_result(
    test_name: str,
    case: Dict[str, Any],
    test_result_cache: Dict[str, Any],
    test_result_llm
) -> Dict[str, Any]:
    """
    generate deterministic test result using LLM + master_seed

    uses environment_hidden_data as ground truth context
    caches results to avoid regenerating same test multiple times
    """
    cache_key = f"{case['case_id']}_{test_name}"

    if cache_key in test_result_cache:
        return test_result_cache[cache_key]

    # check if test result is pre-defined in test_result_templates
    test_templates = case.get("test_result_templates", {})

    # normalize query
    query = test_name.lower().strip()

    # create normalized lookup dict
    normalized_templates = {k.lower().strip(): (k, v) for k, v in test_templates.items()}

    # exact match (case-insensitive)
    if query in normalized_templates:
        original_key, template_value = normalized_templates[query]
        result = {
            "test_name": test_name,
            "value": template_value,
            "generated": False
        }
        test_result_cache[cache_key] = result
        return result

    # partial match (e.g., "echo" matches "echocardiogram")
    for normalized_key, (_, template_value) in normalized_templates.items():
        if normalized_key in query or query in normalized_key:
            result = {
                "test_name": test_name,
                "value": template_value,
                "generated": False
            }
            test_result_cache[cache_key] = result
            return result

    # generate test result using LLM with environment_hidden_data
    hidden_data = case.get("environment_hidden_data", {})
    patient_data = case.get("patient_visible_data", {})

    prompt = f"""Generate realistic {test_name} test result for this patient.

PATIENT CONTEXT (ground truth):
- True diagnosis: {hidden_data.get('true_diagnosis', 'Unknown')}
- Disease severity: {hidden_data.get('disease_severity', 'Unknown')}
- Clinical context: {hidden_data.get('clinical_context', 'Unknown')}

PATIENT DEMOGRAPHICS:
- Age: {patient_data.get('age')}
- Sex: {patient_data.get('sex')}
- Chief complaint: {patient_data.get('chief_complaint')}

Generate ONLY the test result value with units and interpretation. Format as a single-line string.
Example: "827 microg/g (critically elevated - normal <50 microg/g)"

Test result for {test_name}:"""

    messages = [HumanMessage(content=prompt)]

    # use deterministic LLM with temperature=0 for reproducibility
    response = test_result_llm.invoke(messages)
    result_text = response.content.strip()

    # create structured result
    result = {
        "test_name": test_name,
        "value": result_text,
        "generated": True
    }

    test_result_cache[cache_key] = result
    return result
