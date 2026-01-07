"""
Sources:
- GOLD 2023: Agustí et al. npj Primary Care Respiratory Medicine (2023)
  https://www.nature.com/articles/s41533-023-00349-4
- InterQual 2022: Physician Admission Guide (Adult)
  https://www.stqn.org/upload/docs/STQN/Quarter%201%202023/2022%20Interqual%20Physician%20Admission%20Guide%20Adult.pdf
"""


class COPDPolicies:

    PROVIDER_GUIDELINES = {
        "gold_2023": {
            "policy_id": "gold_2023_copd",
            "policy_type": "provider_guideline",
            "issuer": "Global Initiative for Chronic Obstructive Lung Disease (GOLD)",
            "source": {
                "url": "https://www.nature.com/articles/s41533-023-00349-4"
            },
            "phase2": {
                "requires_phase2": "unknown",
                "phase2_type": "unknown"
            },
            "content": {
                "format": "structured",
                "data": {
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
                },
                "text": ""
            },
            "notes_free_text": "GOLD 2023 recommends hospital admission for COPD exacerbation if any of the listed indications are present.",
        }
    }

    PAYOR_POLICIES = {
        "interqual_2022": {
            "policy_id": "interqual_2022_copd",
            "policy_type": "payer_coverage_policy",
            "issuer": "Change Healthcare (InterQual)",
            "source": {
                "url": "https://www.stqn.org/upload/docs/STQN/Quarter%201%202023/2022%20Interqual%20Physician%20Admission%20Guide%20Adult.pdf"
            },
            "phase2": {
                "requires_phase2": True,
                "phase2_type": "concurrent_review"
            },
            "content": {
                "format": "structured",
                "data": {
                    "policy_name": "InterQual 2022 COPD Criteria",
                    "observation_criteria": {
                        "prerequisites": [">=2 doses short-acting beta-agonist prior to admission"],
                        "must_meet_one_of": [
                            {"metric": "SpO2", "range": "90-91%"},
                            {"metric": "PaO2", "range": "56-60 mmHg"},
                            {"metric": "PCO2", "range": "41-44 mmHg"},
                            {"metric": "work_of_breathing", "description": "functional descriptors present"}
                        ]
                    },
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
                    "observation_only_triggers": [
                        "SpO2 >= 92% on room air",
                        "Patient at baseline respiratory status",
                        "No prerequisite treatments attempted"
                    ],
                    "decision_logic": "Gated by: treatment prerequisites -> numeric thresholds -> ventilation flags -> risk factors"
                },
                "text": ""
            },
            "notes_free_text": "InterQual 2022 uses gated criteria: treatment prerequisites -> numeric thresholds -> clinical severity markers. Observation level has less stringent thresholds than inpatient level.",
        }
    }