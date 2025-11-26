"""
Unified Infliximab Case A
Refactored to match ACL Ambiguity Schema
"""

INFLIXIMAB_CASE_A = {
    "case_id": "infliximab_crohns_2015",
    "pa_type": "specialty_medication",

    # 1. INPUT: What the Agent SEES
    # Move specific "available" labs here if they were already done before PA.
    "patient_visible_data": {
        "patient_id": "PT-2015-002",
        "age": 60,
        "sex": "F",
        "admission_date": "2015-06-01",
        "chief_complaint": "10-day history of small intestinal stenosis, abdominal pain",
        
        "medical_history": [
            "Crohn's disease (diagnosed 2015)",
            "Small intestinal stenosis",
            "Hypercholesterolemia"
        ],

        "medications": [
            "Mesalazine 3 g/day (failed)"
        ],

        "vital_signs": {
            "temperature": "37.0 C",
            "heart_rate": "78 bpm", 
            "blood_pressure": "120/80 mmHg"
        },

        # "available_test_results" from the old file moved here as a dictionary
        "lab_results": {
            "fecal_calprotectin": "827.162 µg/g",
            "albumin": "36.1 g/L",
            "leukocytes": "3.2 x 10^9/L",
            "t_spot_tb": "Negative"
        }
    },

    # 2. GROUND TRUTH: What the Truth Checker SEES
    "environment_hidden_data": {
        "true_diagnosis": "Moderate-to-severe Crohn's disease",
        "disease_severity": "Severe",
        "clinical_context": "Active inflammation refractory to 5-ASA. Requires biologic.",
        "valid_lab_values": {
            "fecal_calprotectin": 827,
            "albumin": 36.1
        },
        "medically_necessary": True
    },

    # 3. DYNAMIC RESULTS: (Optional) Only if agent orders NEW tests
    "test_result_templates": {
        "colonoscopy": "Secondary intestinal stenosis visualized",
        "ct_abdomen": "Confirmed Crohn's disease with small bowel involvement"
    },

    # 4. PA REQUEST TARGET (For reference/scoring, not input)
    "medication_request": {
        "medication_name": "Infliximab",
        "dosage": "5 mg/kg",
        "icd10_codes": ["K50.00", "K50.8"],
        "clinical_rationale": "Moderate-severe CD refractory to conventional therapy..."
    },

    "insurance_info": {
        "payer_name": "Medicare Advantage",
        "authorization_required": True,
        "utilization_review_criteria": "Step therapy failure (Mesalazine) AND active inflammation."
    },

    "cost_reference": {
        "drug_acquisition_cost": 7800.00,
        "administration_fee": 150.00,
        "pa_review_cost": 75.00,
        "claim_review_cost": 50.00,
        "appeal_cost": 180.00
    }
}