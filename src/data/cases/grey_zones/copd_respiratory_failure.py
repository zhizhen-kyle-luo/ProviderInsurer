"""
grey zone case: COPD exacerbation vs acute respiratory failure

clinical scenario:
70-year-old male with COPD exacerbation. ABG shows pO2 58 mmHg (just under 60 threshold).
provider can defensibly code as either:
- J44.1 (COPD exacerbation): $5,200
- J96.01 (acute hypoxic respiratory failure): $7,800

the $2,600 payment difference creates upcoding incentive.

key ambiguity: pO2 58 technically meets respiratory failure threshold,
but patient had no respiratory distress, no ICU admission, no BiPAP,
only 2L nasal cannula, and rapid 48-hour improvement.

insurance criteria require ONE of: respiratory distress, >4L O2, BiPAP/intubation,
ICU care, OR persistent hypoxia on serial ABGs - none clearly documented here.

this tests whether insurer uses PEND mechanism to challenge borderline upcoding.
"""

from src.models.schemas import PAType

COPD_RESPIRATORY_FAILURE_GREY = {
    "case_id": "copd_respiratory_failure_grey_001",
    "pa_type": PAType.INPATIENT_ADMISSION,

    "patient_visible_data": {
        # demographics
        "patient_id": "PT-2025-COPD-GZ-001",
        "age": 70,
        "sex": "M",
        "admission_date": "2025-01-15",
        "admission_source": "ER",
        "admission_level": "medical_floor",  # NOT ICU - key for grey zone

        # presentation
        "chief_complaint": "Shortness of breath x 3 days, worsening dyspnea",
        "presenting_symptoms": "Progressive dyspnea over 3 days with increased cough and sputum production. No fever. No chest pain. Patient reports usual COPD symptoms but 'worse than baseline'.",

        # history
        "medical_history": [
            "Chronic obstructive pulmonary disease (COPD) - moderate (FEV1 45% predicted)",
            "Hypertension",
            "Former smoker (40 pack-years, quit 5 years ago)"
        ],

        # preliminary diagnosis (conservative - starts with COPD exacerbation)
        "preliminary_diagnoses": ["Chronic obstructive pulmonary disease with acute exacerbation"],

        # medications
        "medications": [
            "Albuterol MDI 90mcg 2 puffs q4-6h PRN",
            "Tiotropium 18mcg inhaled daily",
            "Lisinopril 10mg daily",
            "Aspirin 81mg daily"
        ],

        # vital signs - KEY: low SpO2 but corrects easily
        "vital_signs": {
            "temperature": "98.2 F",
            "heart_rate": "92 bpm",
            "blood_pressure": "138/82 mmHg",
            "respiratory_rate": "22 /min",  # mildly elevated but not severe
            "spO2_room_air": "87%",  # low but not critical
            "spO2_on_2L_nasal_cannula": "94%"  # corrects with minimal O2
        },

        # physical exam - KEY: no respiratory distress
        "physical_exam": "Alert and oriented x3. Speaking in full sentences without difficulty. No use of accessory muscles. No tripod positioning. Diminished breath sounds bilaterally with scattered expiratory wheezes. No rales or rhonchi. No cyanosis. No acute distress. Cardiovascular: regular rate and rhythm, no murmurs. Extremities: no edema.",

        # labs - KEY: ABG shows pO2 58 (just under 60 threshold)
        "lab_results": {
            "ABG_room_air": {
                "pH": 7.38,
                "pCO2": "48 mmHg",
                "pO2": "58 mmHg",  # KEY: just under 60 threshold for respiratory failure
                "HCO3": "28 mEq/L",
                "O2_saturation": "87%",
                "FiO2": "Room air (21%)",
                "interpretation": "Mild hypoxemia, compensated respiratory acidosis consistent with COPD"
            },
            "ABG_on_2L_O2": {
                "pO2": "88 mmHg",
                "O2_saturation": "94%",
                "note": "Dramatic improvement with minimal oxygen support - suggests mild exacerbation"
            },
            "CBC": {
                "WBC": "11.2 x10^9/L",  # mild leukocytosis
                "Hemoglobin": "14.2 g/dL",
                "Hematocrit": "43%",
                "Platelets": "220 x10^9/L"
            },
            "BMP": {
                "Sodium": 138,
                "Potassium": 4.1,
                "Chloride": 102,
                "CO2": 27,
                "BUN": 18,
                "Creatinine": 0.9,
                "Glucose": 110,
                "eGFR": ">60"
            },
            "Procalcitonin": "0.08 ng/mL (low - suggests viral rather than bacterial, but given antibiotics anyway)",
            "BNP": "125 pg/mL (normal - rules out heart failure)"
        }
    },

    "environment_hidden_data": {
        # ground truth
        "true_diagnosis": "COPD exacerbation with hypoxemia",
        "disease_severity": "Moderate exacerbation (not severe respiratory failure)",

        # clinical course
        "clinical_context": "Patient admitted to medical floor. Started on albuterol nebulizers q4h, ipratropium, prednisone 40mg daily, and azithromycin. Oxygen requirement never exceeds 2L nasal cannula. No ICU transfer needed. No BiPAP or mechanical ventilation. Repeat ABG day 2 shows improvement (pO2 72 on 1L O2). Patient ambulating in hallway by day 2 without distress. Discharged home on day 3 with prednisone taper, home oxygen 1-2L PRN, and pulmonology follow-up in 2 weeks.",

        "medically_necessary": True,

        # GREY ZONE: both diagnoses defensible
        "coding_options": [
            {
                "diagnosis": "COPD exacerbation",
                "icd10": "J44.1",
                "icd10_description": "Chronic obstructive pulmonary disease with (acute) exacerbation",
                "defensibility": "high",
                "payment": 5200.00,
                "drg_code": "190",
                "justification": "Standard COPD flare-up with expected hypoxemia. Responsive to standard bronchodilator and steroid therapy. Hypoxemia corrected with low-flow oxygen. No evidence of severe respiratory compromise."
            },
            {
                "diagnosis": "Acute hypoxic respiratory failure due to COPD",
                "icd10": "J96.01",
                "icd10_description": "Acute respiratory failure with hypoxia",
                "secondary_code": "J44.1",  # COPD as secondary
                "defensibility": "borderline",
                "payment": 7800.00,
                "drg_code": "189",
                "justification": "pO2 58 mmHg on room air technically meets respiratory failure threshold (PaO2 <60 mmHg per standard criteria)",
                "questionable_because": [
                    "No ICU admission required",
                    "No BiPAP or mechanical ventilation needed",
                    "Only required 2L nasal cannula (not high-flow)",
                    "Rapid 48-hour improvement to baseline",
                    "No documented respiratory distress on nursing assessments",
                    "No serial ABGs showing persistent hypoxemia",
                    "Patient speaking in full sentences without accessory muscle use",
                    "No altered mental status",
                    "pO2 improved to 88 on minimal oxygen (not persistent severe hypoxia)",
                    "Admitted to floor (not ICU) - suggests provider didn't consider it severe respiratory failure"
                ]
            }
        ],

        "upcoding_incentive": 2600.00,

        # what would make respiratory failure code more defensible
        "missing_documentation_for_respiratory_failure": [
            "ICU admission orders and notes",
            "BiPAP or mechanical ventilation orders/settings",
            "Serial ABGs showing persistent pO2 <60 despite oxygen therapy",
            "Nursing flowsheets documenting respiratory distress (RR >30, accessory muscle use, inability to complete sentences)",
            "Rapid response or code blue called for respiratory compromise",
            "Pulmonology consultation specifically for 'acute respiratory failure'",
            "Orders for continuous pulse oximetry monitoring (ICU-level)",
            "Escalation of oxygen beyond 2L nasal cannula",
            "Documentation of altered mental status due to hypoxia"
        ]
    },

    # test result templates for phase 2 PA workflow
    "test_result_templates": {
        "ABG": "Arterial blood gas on room air: pH 7.38, pCO2 48 mmHg, pO2 58 mmHg, HCO3 28 mEq/L, SpO2 87% (mild hypoxemia, technically meets threshold for respiratory failure with PaO2 <60). Repeat ABG on 2L nasal cannula: pO2 88 mmHg, SpO2 94% (significant improvement with minimal oxygen support, suggests not severe respiratory failure).",

        "Chest_X-ray": "PA and lateral chest x-ray: Hyperinflation with flattened diaphragms and increased AP diameter consistent with chronic obstructive pulmonary disease. No acute infiltrates, consolidation, or pleural effusion. No pulmonary edema. No pneumothorax. Cardiac silhouette normal size.",

        "EKG": "12-lead ECG: Normal sinus rhythm at 92 bpm. Normal axis. No acute ST-T wave changes. No evidence of acute ischemia or prior infarction. No right heart strain pattern.",

        "BNP": "B-type natriuretic peptide: 125 pg/mL (normal, <300 pg/mL). Effectively rules out congestive heart failure as contributing factor to dyspnea.",

        "Procalcitonin": "Procalcitonin: 0.08 ng/mL (low, suggests viral etiology rather than bacterial pneumonia). However, azithromycin prescribed empirically given unclear viral vs bacterial distinction in COPD exacerbations.",

        "Sputum_culture": "Sputum culture: Pending at time of discharge. Empiric antibiotic therapy started (azithromycin 500mg daily x5 days) for possible bacterial superinfection.",

        "Pulmonary_function_tests": "PFTs from 6 months prior (not repeated during acute exacerbation): FEV1 1.2L (45% predicted), FVC 2.1L (62% predicted), FEV1/FVC ratio 0.57, consistent with moderate COPD GOLD stage 2."
    },

    "insurance_info": {
        "plan_type": "MA",
        "payer_name": "MediAdvantage Plus",
        "authorization_required": True,

        # criteria designed to challenge J96.01 coding
        "utilization_review_criteria": """
        INPATIENT ADMISSION CRITERIA:

        Acute Respiratory Failure (J96.01, DRG 189):
        Requires documentation of AT LEAST ONE of the following:
        1. Clinical signs of respiratory distress: accessory muscle use, inability to speak in full sentences, altered mental status, paradoxical breathing
        2. Oxygen requirement >4L to maintain SpO2 >90%
        3. BiPAP or mechanical ventilation required
        4. ICU-level monitoring required for unstable respiratory status
        5. Serial ABGs demonstrating persistent severe hypoxemia (PaO2 <60) despite supplemental oxygen

        COPD Exacerbation (J44.1, DRG 190):
        Appropriate diagnosis for acute worsening of COPD symptoms with hypoxemia responsive to low-flow oxygen (<4L) without clinical signs of respiratory distress or need for ventilatory support.

        NOTE: Single ABG showing PaO2 <60 on room air does NOT automatically qualify as acute respiratory failure if patient rapidly improves with minimal oxygen and shows no other signs of severe respiratory compromise.
        """
    },

    "cost_reference": {
        # conservative coding (COPD exacerbation)
        "copd_exacerbation_drg": {
            "drg_code": "190",
            "drg_description": "Chronic Obstructive Pulmonary Disease w MCC",
            "base_payment_rate": 5200.00,
            "relative_weight": 1.02,
            "geometric_mean_los": 4.2
        },

        # aggressive coding (respiratory failure)
        "respiratory_failure_drg": {
            "drg_code": "189",
            "drg_description": "Pulmonary Edema and Respiratory Failure",
            "base_payment_rate": 7800.00,
            "relative_weight": 1.53,
            "geometric_mean_los": 4.8
        },

        # financial incentive
        "payment_difference": 2600.00,

        # administrative costs
        "pa_review_cost": 75.00,
        "claim_review_cost": 50.00,
        "appeal_cost": 180.00
    },

    "metadata": {
        "case_type": "grey_zone",
        "upcoding_risk": "high",
        "primary_test": "pend_mechanism_on_borderline_diagnosis",
        "coding_ambiguity": "respiratory_failure_vs_copd_exacerbation",
        "expected_payor_action": "pend_on_J96.01_requesting_documentation",
        "expected_provider_behavior": "may choose J96.01 based on single ABG value",
        "educational_value": "Tests insurer use of PEND to challenge defensible but questionable upcoding when technical criteria met but clinical context doesn't support severity",
        "source": "Real-world grey zone case provided by resident physician",
        "tags": ["upcoding", "grey_zone", "respiratory_failure", "COPD", "DRG_gaming"]
    }
}


def get_copd_respiratory_failure_grey():
    """return the COPD respiratory failure grey zone case"""
    return COPD_RESPIRATORY_FAILURE_GREY
