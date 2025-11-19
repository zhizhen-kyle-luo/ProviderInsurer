"""
exercise stress test for chest pain - cardiac testing pa validation

case: 59yo male police officer with atypical chest pain, multiple cardiac risk factors
"""

CHEST_PAIN_CASE = {
    "case_id": "chest_pain_stress_test_001",
    "pa_type": "cardiac_testing",

    "patient_visible_data": {
        "patient_id": "PT-2024-CP-001",
        "age": 59,
        "sex": "M",
        "occupation": "Police Officer",
        "admission_date": "2024-03-10",
        "admission_source": "ER",

        "chief_complaint": "Intermittent sternal chest pain x 2 weeks",

        "vital_signs": {
            "temperature": "97.5 F",
            "heart_rate": "79 bpm",
            "blood_pressure": "153/94 mmHg",
            "respiratory_rate": "20/min",
            "spO2": "99%",
            "weight": "100 kg"
        },

        "medical_history": [
            "GERD",
            "Tobacco use (1 ppd)",
            "Hyperlipidemia (untreated)"
        ],

        "medications": [
            "Omeprazole",
            "Calcium carbonate"
        ],

        "presenting_symptoms": "Dull, squeezing sternal chest pain rated 7-9/10. Unrelieved by antacids. No radiation. Worse with eating."
    },

    "environment_hidden_data": {
        "true_diagnosis": "Coronary Artery Disease (Severe)",
        "disease_severity": "Critical (99% LAD occlusion found later)",
        "clinical_context": "High risk patient (smoker, age, HTN) with atypical but concerning symptoms. Resting ECG has T-wave inversions V2-V4."
    },

    "procedure_request": {
        "procedure_name": "Exercise Tolerance Test with Echocardiography",
        "cpt_code": "93015",
        "icd10_codes": ["R07.9", "I25.10"],
        "clinical_indication": "Risk stratification for atypical chest pain in patient with multiple cardiac risk factors (smoking, HTN, age). Baseline ECG shows T-wave inversions."
    },

    "insurance_info": {
        "plan_type": "Commercial",
        "payer_name": "BlueCross",
        "authorization_required": True
    }
}


def get_chest_pain_case():
    """returns chest pain stress test case for simulation"""
    return CHEST_PAIN_CASE
