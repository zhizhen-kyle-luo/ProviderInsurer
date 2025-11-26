"""
infliximab for crohn's disease case b - specialty medication pa validation

case: 64yo female with recurrent ileal crohn's disease post-surgical, refractory to azathioprine
"""

INFLIXIMAB_CASE_B = {
    "case_id": "infliximab_crohns_case_b",
    "pa_type": "specialty_medication",

    "patient_visible_data": {
        "patient_id": "PT-2024-CD-002",
        "age": 64,
        "sex": "F",
        "admission_date": "2024-01-15",
        "admission_source": "Direct",

        "chief_complaint": "Recurrent abdominal pain and obstructive symptoms",

        "vital_signs": {
            "temperature": "37.1 C",
            "heart_rate": "78 bpm",
            "blood_pressure": "128/76 mmHg",
            "respiratory_rate": "16/min"
        },

        "medical_history": [
            "Ileal Crohn's disease (diagnosed >20 years ago)",
            "History of ileocecal resection (2004)",
            "Arterial hypertension",
            "Recurrent subocclusive episodes"
        ],

        "medications": [
            "Azathioprine 2 mg/kg/day",
            "Amlodipine 5mg",
            "Captopril"
        ],

        "presenting_symptoms": "Long-standing Crohn's disease with recent recurrence of obstructive symptoms. Colonoscopy reveals inflammatory stenosis at anastomosis site."
    },

    "environment_hidden_data": {
        "true_diagnosis": "Recurrent ileal Crohn's disease with anastomotic stenosis",
        "disease_severity": "Moderate-to-severe",
        "clinical_context": "Post-surgical recurrence refractory to immunomodulator maintenance (Azathioprine). Requires biologic escalation.",
        "medically_necessary": True
    },

    "medication_request": {
        "medication_name": "Infliximab",
        "dosage": "5 mg/kg",
        "frequency": "Weeks 0, 2, 6 then every 8 weeks",
        "duration": "12 months",
        "icd10_codes": ["K50.012", "K56.60"],
        "clinical_rationale": "Patient has failed maintenance therapy with Azathioprine. documented endoscopic recurrence with stenosis. Combination therapy (Infliximab + Azathioprine) indicated for high-risk phenotype.",
        "prior_therapies_failed": ["Azathioprine (maintenance failure)"],
        "step_therapy_completed": True
    },

    "cost_reference": {
        "drug_acquisition_cost": 7800.00,
        "administration_fee": 150.00,
        "pa_review_cost": 75.00,
        "claim_review_cost": 50.00,
        "appeal_cost": 180.00
    },

    "insurance_info": {
        "plan_type": "MA",
        "payer_name": "Medicare Advantage",
        "authorization_required": True,
        "utilization_review_criteria": "Step therapy failure (Azathioprine) AND documented endoscopic recurrence."
    }
}
