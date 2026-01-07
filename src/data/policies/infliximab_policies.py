"""
Sources:
- AGA guideline (2021) (open access, PMC): https://pmc.ncbi.nlm.nih.gov/articles/PMC8988893/
- UnitedHealthcare Commercial Medical Benefit Drug Policy (effective 2025-10-01):
  https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/infliximab-remicade-inflectra.pdf
- Cigna Drug Coverage Policy IP0660 (effective 2026-01-01):
  https://static.cigna.com/assets/chcp/pdf/coveragePolicies/pharmacy/ip_0660_coveragepositioncriteria_inflammatory_conditions_infliximab_intravenous_products_pa.pdf
"""


class InfliximabCrohnsPolicies:

    PROVIDER_GUIDELINES = {
        "aga_2021": {
            "policy_id": "aga_2021_crohns_infliximab",
            "policy_type": "provider_guideline",
            "issuer": "American Gastroenterological Association (AGA)",
            "source": {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8988893/"
            },
            "phase2": {
                "requires_phase2": True,
                "phase2_type": "PA"
            },
            "content": {
                "format": "structured",
                "data": {
                    "policy_name": "AGA 2021 (provider guideline)",
                    "scope": "Adult outpatients with moderate to severe luminal and/or fistulizing Crohn's disease",
                    "key_recommendations": [
                        "Use anti-TNF therapy (e.g., infliximab) for induction and maintenance of remission in moderate to severe Crohn's disease.",
                        "In biologic-naïve moderate to severe Crohn's disease, infliximab is a recommended option for induction.",
                        "Prefer early introduction of a biologic (± immunomodulator) rather than delaying until after failure of mesalamine and/or corticosteroids.",
                        "Recommend against 5-ASA/mesalamine for induction or maintenance of remission in moderate to severe Crohn's disease."
                    ],
                    "decision_logic": (
                        "If the clinical picture supports moderate–severe Crohn's disease (and/or high-risk/complicated features), "
                        "biologic therapy such as infliximab is guideline-concordant even if the patient has not formally 'failed' "
                        "mesalamine and/or corticosteroids."
                    ),
                    "documentation_focus": [
                        "Evidence the disease is moderate–severe (symptoms + objective markers such as fecal calprotectin/CRP/imaging/endoscopy).",
                        "If bypassing steroids/other conventional therapy, document rationale (planned effective induction strategy; contraindication; urgency/high-risk disease)."
                    ],
                },
                "text": ""
            },
            "notes_free_text": "AGA 2021 recommends anti-TNF therapy (infliximab) for moderate to severe Crohn's disease, preferring early biologic introduction rather than waiting for conventional therapy failure.",
        }
    }

    PAYOR_POLICIES = {
        "uhc_commercial_2025": {
            "policy_id": "uhc_commercial_2025_infliximab",
            "policy_type": "payer_coverage_policy",
            "issuer": "UnitedHealthcare",
            "source": {
                "url": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/infliximab-remicade-inflectra.pdf"
            },
            "phase2": {
                "requires_phase2": True,
                "phase2_type": "PA"
            },
            "content": {
                "format": "structured",
                "data": {
                    "policy_name": "UnitedHealthcare Commercial Medical Benefit Drug Policy (effective 2025-10-01)",
                    "notes": [
                        "Policy cross-references a related Medicare Advantage policy ('Medicare Part B Step Therapy Programs').",
                        "Crohn's diagnosis-specific criteria allow coverage via either (a) high-risk/complicated disease features OR (b) failure/contraindication/intolerance to conventional therapies."
                    ],
                    "crohns_disease_initial_criteria": {
                        "must_have": [
                            "Diagnosis of moderately to severely active Crohn's disease."
                        ],
                        "must_meet_one_of": [
                            "High-risk disease (e.g., fistulizing, stricturing, or extensive disease).",
                            "Failure, contraindication, or intolerance to conventional therapies (e.g., corticosteroids, thiopurines such as azathioprine/6-MP, methotrexate)."
                        ],
                        "prescriber_requirement": "Prescribed by or in consultation with a gastroenterologist or specialist experienced with Crohn's disease biologic therapy.",
                        "authorization_duration": "Initial authorization up to 12 months (per policy).",
                    },
                    "decision_logic": (
                        "Approve if moderate–severe Crohn's is established AND either high-risk features are documented "
                        "(e.g., stricturing) OR conventional-therapy failure/contraindication is documented. "
                        "Otherwise, request missing documentation (pend)."
                    ),
                },
                "text": ""
            },
            "notes_free_text": "UHC policy allows coverage for infliximab via either high-risk/complicated disease features OR conventional therapy failure. Authorization up to 12 months.",
        },
        "cigna_ip0660_2026": {
            "policy_id": "cigna_ip0660_2026_infliximab",
            "policy_type": "payer_coverage_policy",
            "issuer": "Cigna",
            "source": {
                "url": "https://static.cigna.com/assets/chcp/pdf/coveragePolicies/pharmacy/ip_0660_coveragepositioncriteria_inflammatory_conditions_infliximab_intravenous_products_pa.pdf"
            },
            "phase2": {
                "requires_phase2": True,
                "phase2_type": "PA"
            },
            "content": {
                "format": "structured",
                "data": {
                    "policy_name": "Cigna Drug Coverage Policy IP0660 (effective 2026-01-01) — stricter step therapy",
                    "crohns_disease_initial_criteria": {
                        "approve_if_all": [
                            "Age ≥ 6 years.",
                            "Meets at least ONE of: (a) tried/currently taking corticosteroids OR corticosteroids contraindicated; (b) tried one other conventional systemic therapy (e.g., azathioprine, 6-MP, methotrexate); (c) has enterocutaneous/rectovaginal fistulas; OR (d) had ileocolonic resection (post-op recurrence prevention).",
                            "Prescribed by or in consultation with a gastroenterologist."
                        ],
                        "explicit_notes": [
                            "A trial of mesalamine does NOT count as a systemic therapy for Crohn's disease."
                        ],
                        "objective_measures_examples": [
                            "Examples of objective measures include fecal markers (e.g., fecal calprotectin), serum markers (e.g., CRP), imaging (MRE/CTE), and endoscopic assessment (used especially for continuation review)."
                        ],
                        "authorization_duration": "Initial therapy approval 6 months (per policy).",
                    },
                    "decision_logic": (
                        "Approve only if Crohn's initial-therapy step criteria are satisfied; otherwise pend/deny for missing step-therapy "
                        "documentation, even if mesalamine trial is documented."
                    ),
                },
                "text": ""
            },
            "notes_free_text": "Cigna IP0660 requires stricter step therapy documentation. Mesalamine does not satisfy step therapy requirement. Authorization for 6 months.",
        }
    }