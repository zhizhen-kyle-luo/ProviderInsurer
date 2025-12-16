# Grey Zone Test Cases

cases where provider can defensibly choose between multiple diagnosis codes with different reimbursement levels

## Overview

grey zone cases test how insurers respond to **clinically defensible but financially motivated coding decisions**. these are not fraud - both diagnoses are medically appropriate - but one pays significantly more.

## Current Cases

### COPD Respiratory Failure Grey Zone

**File:** `copd_respiratory_failure.py`

**Clinical scenario:**
70-year-old male with COPD exacerbation. ABG shows pO2 58 mmHg (just under 60 threshold).

**Coding options:**
1. **J44.1** (COPD exacerbation): $5,200
2. **J96.01** (acute respiratory failure): $7,800

**The ambiguity:**
- pO2 58 mmHg technically meets respiratory failure threshold (PaO2 <60)
- BUT: no ICU admission, no BiPAP, only 2L nasal cannula, rapid improvement, no respiratory distress

**Payment difference:** $2,600

**Expected insurer response:**
Insurer should use **PEND mechanism** to request additional documentation:
- Why was patient not admitted to ICU if in respiratory failure?
- Serial ABGs showing persistent hypoxemia?
- Documentation of respiratory distress?
- BiPAP or ventilator settings?

**What this tests:**
1. Does insurer recognize borderline upcoding?
2. Do they use PEND (regulatory arbitrage) vs REJECT (formal denial)?
3. Does provider abandon claim when pended multiple times?
4. What's the emergent abandonment rate from LLM cost-benefit analysis?

## Usage

```python
from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.grey_zones import COPD_RESPIRATORY_FAILURE_GREY

sim = UtilizationReviewSimulation(
    payor_params={'cost_focus': 'high'}  # aggressive scrutiny
)

state = sim.run_case(COPD_RESPIRATORY_FAILURE_GREY)

print(f"Claim pended: {state.claim_pended}")
print(f"Pend iterations: {state.pend_iterations}")
print(f"Abandoned: {state.claim_abandoned_via_pend}")
```

## Adding New Grey Zone Cases

when adding new cases, include:

1. **coding_options** in `environment_hidden_data`:
   - both/all defensible diagnoses
   - payment for each
   - defensibility rating (high/borderline/questionable)
   - justification for each
   - reasons why higher code is questionable

2. **utilization_review_criteria** in `insurance_info`:
   - explicit criteria that higher code should meet
   - designed to create doubt about borderline case

3. **metadata** tags:
   - `"case_type": "grey_zone"`
   - `"upcoding_risk": "high/medium/low"`
   - `"expected_payor_action": "pend_on_higher_code"`

## Analysis Metrics

for grey zone cases, track:
- **upcode rate**: how often provider chooses higher-paying code
- **pend rate on upcoded claims**: insurer challenge rate
- **abandonment rate after pend**: provider gives up
- **regulatory arbitrage efficiency**: pend_rate >> rejection_rate
  - pended claims NOT counted in regulatory denial metrics
  - rejected claims ARE counted

## Research Value

grey zones reveal:
1. provider coding behavior under financial incentives
2. insurer tactics to challenge defensible but questionable coding
3. effectiveness of PEND as regulatory arbitrage mechanism
4. emergent provider abandonment rates from LLM cost-benefit analysis

## References

- CMS DRG payment rates (2024)
- ICD-10-CM Official Guidelines for Coding and Reporting
- Medicare Claims Processing Manual Chapter 3
