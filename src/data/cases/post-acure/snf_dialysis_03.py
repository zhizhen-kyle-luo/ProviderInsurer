"""
SNF Case 3: Cardiopulmonary Renal Failure
Source: https://orchardhillrehab.com/case-studies/
Ambiguity Probe: Missing BP values despite 'hemodynamic instability' claim.
"""

SNF_DIALYSIS_03 = {
    "case_id": "snf_dialysis_03",
    "pa_type": "post_acute_care",

    # INPUT: High Ambiguity
    "patient_visible_data": {
        "patient_id": "SNF-2024-003",
        "age": 59,
        "sex": "M",
        "chief_complaint": "Dialysis requirements, cardiac management",
        
        "medical_history": [
            "Acute CHF",
            "Acute-on-chronic renal failure (Dialysis)",
            "UTI"
        ],

        "medications": [
            "IV Cefepime"
            # MISSING: Cardiac meds mentioned in history but not listed.
        ],

        "clinical_notes": "Hemodynamic instability requiring frequent medication titration.",
        
        "vital_signs": {
            "o2_requirements": "4 LPM"
            # MISSING: Blood Pressure (Critical for 'hemodynamic instability')
        }
    },

    # GROUND TRUTH
    "environment_hidden_data": {
        "true_diagnosis": "ESRD with acute CHF exacerbation",
        "clinical_context": "Dialysis 3x/week. Cachexic morphology.",
        "true_vitals": {"bp": "90/60 mmHg (Labile)", "hr": "110 bpm"},
        "medically_necessary": True
    },

    "insurance_info": {
        "payer_name": "Medicare Advantage",
        "authorization_required": True,
        "utilization_review_criteria": "SNF approved for 'Hemodynamic Instability' requiring monitoring >3x/day. Must document BP log."
    }
}