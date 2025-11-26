"""
SNF Case 2: COPD Exacerbation & Cellulitis
Source: https://orchardhillrehab.com/case-studies/
Ambiguity Probe: Missing antibiotics and diabetes management logs.
"""

SNF_COPD_02 = {
    "case_id": "snf_copd_02",
    "pa_type": "post_acute_care",

    # INPUT: High Ambiguity
    "patient_visible_data": {
        "patient_id": "SNF-2024-002",
        "age": 56,
        "sex": "F",
        "chief_complaint": "Respiratory management, bilateral lower extremity cellulitis",
        
        "medical_history": [
            "COPD",
            "Obstructive Sleep Apnea",
            "Diabetes",
            "Anemia"
        ],

        "medications": [
            "Lasix 20mg BID",
            "Coreg",
            "Combivent",
            "Eliquis"
            # MISSING: Antibiotics? Diabetes meds?
        ],

        "vital_signs": {
            "o2_requirements": "4 LPM",
            "bipap_settings": "16/11"
            # MISSING: HR, BP, Temp (Critical for sepsis check)
        }
    },

    # GROUND TRUTH
    "environment_hidden_data": {
        "true_diagnosis": "Cellulitis leg; COPD with acute exacerbation",
        "clinical_context": "Requires 4-channel sleep study and daily wound dressing changes.",
        "valid_medications": ["Lasix", "Coreg", "Combivent", "Eliquis", "Doxycycline 100mg BID", "Metformin 500mg"],
        "medically_necessary": True
    },

    "insurance_info": {
        "payer_name": "Medicare Advantage",
        "authorization_required": True,
        "utilization_review_criteria": "Requires sterile wound care daily OR skilled respiratory intervention. Cellulitis must show failure of outpatient treatment."
    }
}