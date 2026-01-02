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
    for normalized_key, (original_key, template_value) in normalized_templates.items():
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


def generate_test_result_from_environment(
    test_name: str,
    environment_data: Dict[str, Any],
    pa_type: str
) -> Dict[str, Any]:
    """
    generate realistic test results based on environment_hidden_data
    uses ground truth to simulate what test would actually find
    """
    true_diagnosis = environment_data.get("true_diagnosis", "").lower()
    disease_severity = environment_data.get("disease_severity", "").lower()
    clinical_context = environment_data.get("clinical_context", "")

    test_name_lower = test_name.lower()

    # resting ecg/ekg
    if "ecg" in test_name_lower or "ekg" in test_name_lower:
        if "stress" not in test_name_lower and "exercise" not in test_name_lower:
            if "coronary" in true_diagnosis or "cad" in true_diagnosis or "ischemia" in true_diagnosis:
                if "severe" in true_diagnosis or "critical" in disease_severity:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "Resting ECG shows T-wave inversions in leads V2-V4. ST segment abnormalities present. Concerning for significant coronary ischemia. Recommend urgent functional cardiac testing (stress test or coronary angiography)."
                    }
                else:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "Resting ECG shows nonspecific ST-T wave changes. Consider stress testing for further evaluation."
                    }
            else:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Normal sinus rhythm. No acute ST changes or ischemic findings."
                }

    # cardiac/stress testing results
    if "stress" in test_name_lower or "exercise" in test_name_lower or "echo" in test_name_lower:
        if "coronary" in true_diagnosis or "cad" in true_diagnosis or "ischemia" in true_diagnosis:
            if "severe" in true_diagnosis or "critical" in disease_severity or "occlusion" in disease_severity:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "ABNORMAL - Significant ST depression in leads V2-V4 at 5 minutes. Test terminated at 7 METS due to chest pain and ECG changes. Strongly positive for inducible ischemia. Immediate cardiology referral recommended."
                }
            else:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "ABNORMAL - Mild ST depression in inferior leads. Positive for inducible ischemia. Further workup recommended."
                }
        else:
            return {
                "test_name": test_name,
                "status": "completed",
                "finding": "Normal exercise tolerance. No ST changes or arrhythmias. Negative for inducible ischemia."
            }

    # inflammatory markers (crohn's, IBD)
    elif "calprotectin" in test_name_lower or "fecal" in test_name_lower:
        if "crohn" in true_diagnosis or "ibd" in true_diagnosis or "colitis" in true_diagnosis:
            if "severe" in disease_severity or "active" in clinical_context.lower():
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Fecal calprotectin: 850 mcg/g (severely elevated, ref <50). CRP: 45 mg/L (elevated). Consistent with active inflammatory bowel disease."
                }
            else:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Fecal calprotectin: 220 mcg/g (elevated, ref <50). Suggests active inflammation."
                }

    # colonoscopy/endoscopy
    elif "colonoscopy" in test_name_lower or "endoscopy" in test_name_lower:
        if "crohn" in true_diagnosis:
            return {
                "test_name": test_name,
                "status": "completed",
                "finding": "Colonoscopy shows deep ulcerations in terminal ileum and cecum with cobblestoning. Biopsies confirm transmural inflammation consistent with Crohn's disease. Stenosis noted at ileocecal valve."
            }

    # cardiac catheterization/angiography
    elif "catheter" in test_name_lower or "angio" in test_name_lower or "cath" in test_name_lower:
        if "coronary" in true_diagnosis:
            if "severe" in true_diagnosis or "99%" in disease_severity:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Coronary angiography: 99% stenosis of proximal LAD. 70% stenosis of RCA. High-grade multivessel disease requiring intervention."
                }

    # ct/mri imaging
    elif "ct" in test_name_lower or "mri" in test_name_lower:
        if "crohn" in true_diagnosis:
            return {
                "test_name": test_name,
                "status": "completed",
                "finding": "CT enterography shows thickened ileal wall (8mm) with surrounding fat stranding. Active inflammation and possible stricture."
            }
        elif "coronary" in true_diagnosis:
            return {
                "test_name": test_name,
                "status": "completed",
                "finding": "Coronary CT angiography shows calcified plaque in LAD with significant stenosis. Recommend functional stress testing."
            }

    # blood tests (CBC, metabolic)
    elif "cbc" in test_name_lower or "complete blood" in test_name_lower:
        if "crohn" in true_diagnosis or "anemia" in clinical_context.lower():
            return {
                "test_name": test_name,
                "status": "completed",
                "finding": "CBC: Hgb 9.2 g/dL (low), MCV 76 fL (microcytic). WBC 12.5k (elevated). Consistent with anemia of chronic disease and active inflammation."
            }

    # generic fallback for unknown tests
    return {
        "test_name": test_name,
        "status": "completed",
        "finding": f"Test completed. Findings consistent with {environment_data.get('true_diagnosis', 'clinical presentation')}."
    }
