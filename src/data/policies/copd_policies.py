"""
Sources:
- GOLD 2023: Agustí et al. npj Primary Care Respiratory Medicine (2023)
  https://www.nature.com/articles/s41533-023-00349-4
- InterQual 2022: Physician Admission Guide (Adult)
  https://www.stqn.org/upload/docs/STQN/Quarter%201%202023/2022%20Interqual%20Physician%20Admission%20Guide%20Adult.pdf
"""


class COPDPolicies:
    """Provider vs insurer policy artifacts for COPD/respiratory failure cases.

    Structure:
    - PROVIDER_GUIDELINES: Clinical guidelines used by providers
    - PAYOR_POLICIES: Coverage policies used by insurers
    """

    PROVIDER_GUIDELINES = {
        "gold_2023": {
            "policy_name": "GOLD 2023 Guidelines",
            "hospitalization_indications": [
                "Severe symptoms such as sudden worsening of resting dyspnoea",
                "Oxygen saturation <= 92%",
                "Confusion or drowsiness",
                "Acute respiratory failure",
                "New physical signs (cyanosis, peripheral oedema)",
                "Failure to respond to initial medical management",
                "Serious comorbidities (heart failure, newly occurring arrhythmias)",
                "Insufficient home support"
            ],
            "decision_logic": "Admit if ANY hospitalization indication is present",
        }
    }

    PAYOR_POLICIES = {
        "interqual_2022": {
            "policy_name": "InterQual 2022 COPD Criteria",
            # observation level (6-48h) - gated requirements
            "observation_criteria": {
                "prerequisites": [">=2 doses short-acting beta-agonist prior to admission"],
                "must_meet_one_of": [
                    {"metric": "SpO2", "range": "90-91%"},
                    {"metric": "PaO2", "range": "56-60 mmHg"},
                    {"metric": "PCO2", "range": "41-44 mmHg"},
                    {"metric": "work_of_breathing", "description": "functional descriptors present"}
                ]
            },

            # inpatient level - stricter thresholds
            "inpatient_criteria": {
                "prerequisites": [
                    ">=2 SABA doses administered",
                    "Dyspnea present"
                ],
                "must_meet_one_of": [
                    {"metric": "SpO2", "threshold": "<= 89%"},
                    {"metric": "PaO2", "threshold": "<= 55 mmHg", "with": "pH > 7.45"},
                    {"metric": "PCO2", "threshold": "> 45 mmHg", "with": "pH < 7.35"},
                    {"metric": "ventilation", "values": ["impending intubation", "NIPPV", "mechanical ventilation"]},
                    {"metric": "physical_signs", "values": ["cyanosis", "paradoxical motion"]},
                    {"metric": "work_of_breathing", "description": "increased work of breathing with functional descriptors"}
                ],
                "risk_factors": [
                    "Age > 65",
                    "FEV1 < 50% predicted",
                    ">=3 exacerbations in past year",
                    "Comorbid cardiovascular disease"
                ]
            },

            # auto-deny triggers
            "observation_only_triggers": [
                "SpO2 >= 92% on room air",
                "Patient at baseline respiratory status",
                "No prerequisite treatments attempted"
            ],

            "decision_logic": "Gated by: treatment prerequisites -> numeric thresholds -> ventilation flags -> risk factors"
        }
    }