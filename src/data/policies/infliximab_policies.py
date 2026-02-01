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
                    "policy_name": "Cigna Drug Coverage Policy IP0660 (effective 2026-01-01)",
                    "crohns_disease_initial_criteria": {
                        "approve_if_all": [
                            "Patient is ≥ 6 years of age.",
                            "Patient meets ONE of the following (a, b, c, or d).",
                            "The medication is prescribed by or in consultation with a gastroenterologist."
                        ],
                        "step_therapy_options": {
                            "a": "Patient has tried or is currently taking corticosteroids, or corticosteroids are contraindicated. (Examples: prednisone, methylprednisolone.)",
                            "b": "Patient has tried one other conventional systemic therapy for Crohn's disease. (Examples: azathioprine, 6-mercaptopurine, methotrexate.)",
                            "c": "Patient has enterocutaneous (perianal or abdominal) or rectovaginal fistulas.",
                            "d": "Patient had ileocolonic resection (to reduce the chance of Crohn's disease recurrence).",
                        },
                        "step_therapy_exception": (
                            "An exception to the requirement for a trial of or contraindication to steroids "
                            "or a trial of one other conventional systemic agent can be made if the patient "
                            "has already tried at least one biologic other than the requested medication. "
                            "A biosimilar of the requested biologic does not count."
                        ),
                        "explicit_exclusion": "A trial of mesalamine does NOT count as a systemic therapy for Crohn's disease.",
                        "authorization_duration": "6 months",
                    },
                    "crohns_disease_continuation_criteria": {
                        "approve_if_all": [
                            "Patient has been established on therapy for at least 6 months.",
                            "Patient meets at least ONE of the following (a or b)."
                        ],
                        "response_options": {
                            "a": "When assessed by at least one objective measure, patient experienced a beneficial clinical response from baseline (prior to initiating an infliximab product).",
                            "b": "Compared with baseline (prior to initiating an infliximab product), patient experienced an improvement in at least one symptom.",
                        },
                        "objective_measure_examples": [
                            "fecal markers (e.g., fecal lactoferrin, fecal calprotectin)",
                            "serum markers (e.g., C-reactive protein)",
                            "imaging studies (magnetic resonance enterography [MRE], computed tomography enterography [CTE])",
                            "endoscopic assessment",
                            "reduced dose of corticosteroids"
                        ],
                        "symptom_improvement_examples": [
                            "decreased pain",
                            "decreased fatigue",
                            "decreased stool frequency",
                            "decreased blood in stool"
                        ],
                        "authorization_duration": "1 year",
                    },
                    "crohns_disease_dosing": {
                        "initial_therapy": "Up to 5 mg/kg as an intravenous infusion followed by additional similar doses at 2 and 6 weeks after the first infusion, and then no more frequently than once every 8 weeks thereafter.",
                        "currently_receiving": "Up to a maximum dose of 10 mg/kg administered intravenously no more frequently than once every 4 weeks.",
                    },
                    "preferred_product_note": (
                        "This product also requires the use of preferred products before approval of a "
                        "requested non-preferred infliximab intravenous product. Refer to the respective "
                        "Inflammatory Conditions – Infliximab Intravenous Products Preferred Specialty "
                        "Management Policy (PSM005) for additional preferred product criteria requirements and exceptions."
                    ),
                    "decision_logic": (
                        "Cigna IP0660: Approve Crohn's initial therapy if age ≥6 AND meets one step-therapy option "
                        "(corticosteroids tried/contraindicated OR conventional systemic therapy tried OR fistulas OR ileocolonic resection) "
                        "AND prescribed by/in consultation with gastroenterologist. Note: mesalamine does NOT count as systemic therapy. "
                        "Exception: prior biologic trial (non-biosimilar) can waive steroid/systemic-therapy requirement. "
                        "For continuation: requires ≥6 months on therapy plus objective response OR symptomatic improvement."
                    ),
                },
                "text": ""
            },
            "notes_free_text": (
                "Cigna IP0660 (effective 01/01/2026): Crohn's disease coverage requires step therapy. "
                "Mesalamine does not count as conventional systemic therapy. Prior biologic exception exists "
                "(biosimilar does not count). Initial approval 6 months; continuation 1 year with documented response. "
                "Dosing: initial up to 5 mg/kg (weeks 0, 2, 6, then q8wk); continuation up to 10 mg/kg q4wk max. "
                "Preferred products per PSM005 policy."
            ),
        }
    }