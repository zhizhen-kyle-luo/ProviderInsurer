# Service Line Schema

This schema defines service line requests and decisions used in Phase 2 (prior authorization) and Phase 3 (claims). Aligned with X12 278/837/835 transaction sets.

> **Note:** Financial amount fields (`charge_amount`, `allowed_amount`, `paid_amount`, `adjustment_amount`) are defined in this schema for future implementation but are **not currently active** in the simulation. They are commented out in the codebase and do not appear in LLM prompts or audit logs.

---

## Design Principles

- Single `ServiceLineRequest` model spans both phases (PA and claims lifecycle)
- Maps to X12 segments: 278 SV1/SV2/HCR (authorization), 837 SV1 (claims), 835 SVC/CAS (remittance)
- Per-line independence: each line adjudicated separately
- Provider action decided AFTER seeing payor response (strategic choice point)

---

## X12 Mapping Reference

| Field | X12 278 | X12 837 | X12 835 |
|-------|---------|---------|---------|
| `procedure_code` | SV1-01/SV2-02 | SV1-01 | SVC-01 |
| `code_type` | SV1 qualifier | SV1 qualifier | SVC qualifier |
| `requested_quantity` | HSD-01 | SV1-04 | - |
| `charge_amount` *(not implemented)* | - | SV1-02 | - |
| `authorization_status` | HCR-01 | - | - |
| `authorization_number` | REF-02 | REF*9F | - |
| `adjudication_status` | - | - | CLP-02 |
| `allowed_amount` *(not implemented)* | - | - | SVC-02 |
| `paid_amount` *(not implemented)* | - | - | SVC-03 |
| `adjustment_group_code` | - | - | CAS-01 |

---

## Service Line Request Fields

### Identification

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `line_number` | int | Yes | Sequential line identifier (1, 2, 3...). Maps to 837 LX-01. |
| `procedure_code` | string | Yes | Primary billing code. CPT (5 digits), HCPCS (letter + 4 digits), J-code (J + 4 digits), or NDC (11 digits). |
| `code_type` | string | Yes | Qualifier for procedure_code. One of: `"CPT"`, `"HCPCS"`, `"J-code"`, `"NDC"`. |

### Request Details

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_type` | string | Yes | Category of service. One of: `"diagnostic_test"`, `"treatment"`, `"level_of_care"`. |
| `service_name` | string | Yes | Human-readable name (e.g., "Infliximab", "MRI Abdomen", "ICU admission"). |
| `service_description` | string | No | Detailed description of the service being requested. |
| `requested_quantity` | int | Yes | Number of units requested (infusions, days, visits, etc.). |
| `quantity_unit` | string | No | Unit type. One of: `"days"`, `"visits"`, `"units"`, `"infusions"`. |
| `charge_amount` | float | No | *(Not implemented)* Billed amount in USD. Optional in 278, required in 837. |

### Clinical Justification

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `diagnosis_codes` | list[str] | No | ICD-10 codes supporting medical necessity for this line. |
| `clinical_rationale` | string | No | Free-text clinical justification. Include: patient demographics, symptoms, objective findings (labs/imaging), guideline citations, step-therapy rationale. |

### Optional Code Identifiers

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ndc_code` | string | No | National Drug Code (11 digits, format 5-4-2). More specific than J-code for drugs. |
| `j_code` | string | No | HCPCS J-code for injectable/infused medications. |
| `cpt_code` | string | No | CPT code if different from primary procedure_code. |

### Service Specifics (Optional)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dosage` | string | No | Drug dosage (e.g., "5 mg/kg"). |
| `frequency` | string | No | Administration frequency (e.g., "q8 weeks"). |
| `duration` | string | No | Treatment duration (e.g., "12 months"). |
| `visit_count` | int | No | Number of visits if applicable. |

---

## Phase 2 Decision Fields (Authorization)

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `authorization_status` | string | `"approved"`, `"modified"`, `"denied"`, `"pending_info"` | Payor's authorization decision. Maps to X12 278 HCR-01. |
| `approved_quantity` | int | - | Quantity approved (may differ from requested). |
| `authorization_number` | string | - | Auth number issued if approved/modified. Links to 837 claim. |
| `modification_type` | string | `"quantity_reduction"`, `"site_change"`, `"code_downgrade"` | Type of modification if status is `"modified"`. |
| `decision_reason` | string | - | Explanation of decision (approval rationale, denial reason, etc.). |
| `requested_documents` | list[str] | - | Documents needed if status is `"pending_info"`. |

---

## Phase 3 Decision Fields (Claims Adjudication)

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `adjudication_status` | string | `"approved"`, `"modified"`, `"denied"`, `"pending_info"` | Payor's claims decision. Maps to X12 835 CLP-02. |
| `allowed_amount` | float | - | *(Not implemented)* Contractual allowed amount in USD. |
| `paid_amount` | float | - | *(Not implemented)* Actual payment amount in USD. |
| `adjustment_group_code` | string | `"CO"`, `"PR"`, `"OA"` | Who is responsible for adjustment. CO=Contractual, PR=Patient, OA=Other. |
| `adjustment_amount` | float | - | *(Not implemented)* Amount adjusted (difference between billed and allowed). |

---

## Workflow Tracking Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `current_review_level` | int | 0 | Phase 2 appeal level. 0=Initial, 1=Reconsideration, 2=IRE (final). |
| `claims_review_level` | int | 0 | Phase 3 appeal level. 0=MAC, 1=QIC, 2=ALJ (final). |
| `reviewer_type` | string | - | Who reviewed (e.g., "UM Triage", "Medical Director", "IRE"). |
| `pend_round` | int | 0 | Times pended at current level. |
| `pend_total` | int | 0 | Total times pended across all levels. |
| `superseded_by_line` | int | null | If resubmitted, points to new line_number. |
| `accepted_modification` | bool | false | Whether provider accepted modified terms. |
| `treat_anyway` | bool | false | Whether provider delivered service despite denial (absorbs cost). |
| `delivered` | bool | false | Whether service was actually delivered (for Phase 3). |
| `request_revision` | int | 0 | Version number if line was resubmitted. |

---

## Provider Action Schema

Provider decides action AFTER seeing payor's response. This is the strategic choice point.
The action is determined by an LLM call (3rd LLM call per turn, after provider submission and payor response).

### Two Action Types

**1. RESUBMIT (bundle-level)** - Withdraw entire PA, start fresh at level 0
```json
{
  "action": "RESUBMIT",
  "resubmit_reason": "<explanation of what you're correcting>",
  "reasoning": "<brief explanation>"
}
```

**2. LINE_ACTIONS (per-line)** - Specify action for each non-approved line
```json
{
  "action": "LINE_ACTIONS",
  "line_actions": [
    {"line_number": 1, "action": "ACCEPT_MODIFY"},
    {"line_number": 2, "action": "PROVIDE_DOCS"},
    {"line_number": 3, "action": "APPEAL", "to_level": 1},
    {"line_number": 4, "action": "ABANDON", "mode": "NO_TREAT"}
  ],
  "reasoning": "<brief explanation>"
}
```

### Per-Line Actions (within LINE_ACTIONS)

| Line Status | Valid Actions | Required Fields |
|-------------|---------------|-----------------|
| `approved` | *(omit - already terminal)* | - |
| `modified` | `ACCEPT_MODIFY`, `APPEAL`, `ABANDON` | APPEAL: `to_level`; ABANDON: `mode` |
| `pending_info` | `PROVIDE_DOCS`, `ABANDON` | ABANDON: `mode` |
| `denied` | `APPEAL`, `ABANDON` | APPEAL: `to_level`; ABANDON: `mode` |

### Per-Line Action Definitions

- **ACCEPT_MODIFY**: Accept payor's modification. Line becomes terminal, service will be delivered.
- **PROVIDE_DOCS**: Will provide requested documents in next submission's `clinical_evidence`.
- **APPEAL**: Escalate to next review level. `to_level` must be `current_review_level + 1` (max 2).
- **ABANDON**: Give up on this line. Requires `mode`.

### RESUBMIT vs APPEAL - Critical Distinction

| Scenario | Action | Rationale |
|----------|--------|-----------|
| Denial due to **YOUR ERROR** (wrong codes, missing diagnoses, insufficient documentation) | `RESUBMIT` | Fix errors and try again at level 0 |
| Denial due to **PAYOR'S INCORRECT DECISION** (your submission was complete and accurate) | `APPEAL` | Dispute their decision at higher review level |
| Want to request **DIFFERENT services** than originally submitted | `RESUBMIT` | Starts fresh with new request |

Real-world context:
- RESUBMIT is a strategic alternative to formal appeal when errors caused the denial
- ~83% of appeals succeed, but take 15-45 days and consume staff resources
- RESUBMIT avoids burning an appeal level on fixable errors

### Abandon Modes

| Mode | Phase | Description |
|------|-------|-------------|
| `NO_TREAT` | Phase 2 | Patient does not receive service |
| `TREAT_ANYWAY` | Phase 2 | Provider delivers service, absorbs cost |
| `WRITE_OFF` | Phase 3 | Provider writes off unpaid claim |

---

## Authorization Status Mapping (X12 278 HCR-01)

| Our Status | X12 Code | X12 Description |
|------------|----------|-----------------|
| `approved` | A1 | Certified in Total |
| `modified` | A6 | Modified |
| `denied` | A3 | Not Certified |
| `pending_info` | A4 | Pended |

---

## Review Levels (Medicare Appeal Mapping)

### Phase 2 (Prior Authorization)

| Level | Name | Description |
|-------|------|-------------|
| 0 | Initial Review | UM nurse/triage reviews against policy checklist |
| 1 | Reconsideration | Medical Director peer-to-peer review (Medicare: QIC) |
| 2 | Independent Review | External IRE; final binding decision (Medicare: ALJ) |

### Phase 3 (Claims)

| Level | Name | Description |
|-------|------|-------------|
| 0 | MAC | Medicare Administrative Contractor initial review |
| 1 | QIC | Qualified Independent Contractor reconsideration |
| 2 | ALJ | Administrative Law Judge hearing (final) |

**Note:** `pending_info` is NOT allowed at level 2 (final review must be terminal).
