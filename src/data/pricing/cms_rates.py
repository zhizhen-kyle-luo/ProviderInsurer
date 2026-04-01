"""
CMS reimbursement rates for service line pricing.

sources:
- drugs: WV BMS ASP Pricing File, CMS national ASP + 6%, Q4 2025
- labs: WV BMS Clinical Lab Fee Schedule, 04/2025-03/2026
- procedures/imaging: CMS PFS Look-Up Tool, 2026 national non-facility payment amounts
  (MAC locality 0000000, no modifier, non-QPP, CY2026 CF = $33.4009)
- admin: CAQH 2023 Index (electronic and manual rates)
- IRE: Sanjay personal communication ($500-$800 range); corroborated by Texas TDI IRO Tier 1 fee
- prompt-pay interest: Bureau of Fiscal Service H1 2026 rate (4.125%), 42 CFR 422.520
- review timeline: 67 days (7+30+30) per CMS-4208-F effective 2026-01-01

drug rates are per infusion (30 units for 60kg patient at 5mg/kg).
lab/procedure rates are per test/session.
run verify_against_appendix() to cross-check against paper appendix.
"""

from __future__ import annotations
from typing import Dict, List, NamedTuple, Optional, Tuple


class CodeInfo(NamedTuple):
    rate: float
    description: str
    keywords: List[str]  # for hallucination detection against LLM service_name

DRUG_CODES: Dict[str, CodeInfo] = {
    "J1745": CodeInfo(932.70, "Injection, infliximab, excludes biosimilar, 10 mg", ["infliximab"]),
    "Q5121": CodeInfo(612.15, "Injection, infliximab-axxq, biosimilar, 10 mg", ["infliximab"]),
    "Q5104": CodeInfo(809.97, "Injection, infliximab-dyyb, biosimilar, 10 mg", ["infliximab"]),
    "Q5105": CodeInfo(809.97, "HALLUCINATED: Q5105 is Retacrit (epoetin alfa-epbx); paper maps to Q5104 infliximab pricing", ["infliximab"]),
    "Q5102": CodeInfo(809.97, "Injection, infliximab-dyyb (Inflectra), biosimilar, 10 mg", ["infliximab"]),
    "Q5103": CodeInfo(599.70, "Injection, infliximab-dyyb (Inflectra), biosimilar, 10 mg", ["infliximab"]),
    "J1200": CodeInfo(1.26, "Injection, diphenhydramine HCl, up to 50 mg", ["diphenhydramine"]),
}

LAB_CODES: Dict[str, CodeInfo] = {
    "80074": CodeInfo(42.87, "Acute hepatitis panel", ["hepatitis"]),
    "80053": CodeInfo(9.50, "Comprehensive metabolic panel", ["metabolic"]),
    "85025": CodeInfo(6.99, "Complete CBC, automated, and target differential WBC count", ["cbc", "blood count"]),
    "86140": CodeInfo(4.66, "C-reactive protein", ["reactive protein", "crp"]),
    "87340": CodeInfo(9.30, "Hepatitis B surface antigen (HBsAg)", ["hepatitis", "hbsag"]),
    "86704": CodeInfo(10.85, "Hepatitis B core antibody, total", ["hepatitis", "hbc", "anti-hb"]),
    "86706": CodeInfo(9.67, "Hepatitis B surface antibody", ["hepatitis", "hbs", "anti-hb"]),
    "86803": CodeInfo(12.84, "Hepatitis C antibody", ["hepatitis", "hcv"]),
    "83993": CodeInfo(17.67, "Calprotectin, fecal", ["calprotectin"]),
}

PROCEDURE_CODES: Dict[str, CodeInfo] = {
    "96413": CodeInfo(133.27, "Chemotherapy administration, IV infusion, up to 1 hour", ["infusion", "chemo", "iv"]),
    "96415": CodeInfo(40.00, "Chemotherapy administration, IV infusion, each additional hour", ["infusion", "chemo", "iv"]),
    "96365": CodeInfo(67.14, "IV infusion, therapeutic/diagnostic, up to 1 hour", ["infusion", "iv"]),
    "96366": CodeInfo(25.00, "IV infusion, therapeutic/diagnostic, each additional hour", ["infusion", "iv"]),
    "74183": CodeInfo(336.01, "MRI abdomen without contrast, then with contrast", ["mri", "abdomen"]),
    "72197": CodeInfo(334.34, "MRI pelvis without contrast, then with contrast", ["mri", "pelvis"]),
}

# level 0 (electronic): CAQH 2023 Index
ADMIN_COST_PROVIDER_L0: float = 5.79
ADMIN_COST_INSURER_L0: float = 0.05
# levels 1-2 (manual, human physician review): CAQH 2023 Index
ADMIN_COST_PROVIDER_L12: float = 10.97
ADMIN_COST_INSURER_L12: float = 3.52
# IRE reversal costs: Sanjay personal communication, corroborated by Texas TDI IRO Tier 1 fee
IRE_CASE_COST: float = 650.00
# prompt-payment interest: Bureau of Fiscal Service H1 2026, applied under 42 CFR 422.520
PROMPT_PAY_RATE: float = 0.04125
REVIEW_DELAY_DAYS: int = 67  # 7 (L0) + 30 (L1) + 30 (L2), per CMS-4208-F effective 2026-01-01

# kept for backward compatibility — equals L0 electronic rate
ADMIN_COST_PROVIDER_PER_TURN: float = ADMIN_COST_PROVIDER_L0
ADMIN_COST_INSURER_PER_TURN: float = ADMIN_COST_INSURER_L0

_ALL_CODES: Dict[str, CodeInfo] = {**DRUG_CODES, **LAB_CODES, **PROCEDURE_CODES}
_ALL_RATES: Dict[str, float] = {code: info.rate for code, info in _ALL_CODES.items()}


_APPENDIX_EXPECTED: Dict[str, float] = {
    # drugs: WV BMS ASP Q4 2025
    "J1745": 932.70, "Q5121": 612.15, "Q5104": 809.97, "Q5103": 599.70,
    # labs: WV BMS CLFS 2025
    "80074": 42.87, "80053": 9.50, "85025": 6.99, "86140": 4.66,
    "87340": 9.30, "86704": 10.85, "86706": 9.67, "86803": 12.84,
    "83993": 17.67,
    # procedures/imaging: CMS PFS 2026 national non-facility
    "96413": 133.27, "96365": 67.14, "74183": 336.01, "72197": 334.34,
}


def verify_against_appendix() -> List[str]:
    """cross-check rates against paper appendix, returns error list"""
    errors: List[str] = []
    for code, expected in _APPENDIX_EXPECTED.items():
        actual = _ALL_RATES.get(code)
        if actual is None:
            errors.append(f"{code}: missing from rate table (expected ${expected})")
        elif abs(actual - expected) > 0.005:
            errors.append(f"{code}: rate mismatch — got ${actual}, expected ${expected}")
    if abs(ADMIN_COST_PROVIDER_PER_TURN - 5.79) > 0.005:
        errors.append(f"admin_provider: got ${ADMIN_COST_PROVIDER_PER_TURN}, expected $5.79")
    if abs(ADMIN_COST_INSURER_PER_TURN - 0.05) > 0.005:
        errors.append(f"admin_insurer: got ${ADMIN_COST_INSURER_PER_TURN}, expected $0.05")
    return errors


def check_code_match(procedure_code: str, llm_service_name: str) -> Tuple[bool, str]:
    """returns (is_consistent, warning) by checking keywords against LLM service_name"""
    if not procedure_code or not llm_service_name:
        return True, ""
    code = str(procedure_code).strip().upper()
    info = _ALL_CODES.get(code)
    if info is None:
        return True, ""
    name_lower = llm_service_name.lower()
    for kw in info.keywords:
        if kw in name_lower:
            return True, ""
    return False, (
        f"POSSIBLE HALLUCINATION: code {code} official='{info.description}' "
        f"but LLM called it '{llm_service_name}'. "
        f"Expected keywords: {info.keywords}"
    )


class UnknownProcedureCodeError(ValueError):
    pass


def lookup_rate(procedure_code: str) -> float:
    """raises UnknownProcedureCodeError if code not in table"""
    if not procedure_code:
        raise UnknownProcedureCodeError("empty procedure code")
    code = str(procedure_code).strip().upper()
    rate = _ALL_RATES.get(code)
    if rate is None:
        raise UnknownProcedureCodeError(
            f"no CMS rate for procedure code '{code}'. "
            f"Known codes: {sorted(_ALL_RATES.keys())}"
        )
    return rate


def get_description(procedure_code: str) -> Optional[str]:
    if not procedure_code:
        return None
    info = _ALL_CODES.get(str(procedure_code).strip().upper())
    return info.description if info else None


def line_value(procedure_code: str, quantity: int) -> float:
    """raises on unknown code or bad quantity"""
    rate = lookup_rate(procedure_code)
    if quantity <= 0:
        raise ValueError(f"invalid quantity {quantity} for code {procedure_code}")
    return rate * quantity
