# Case Schema v2.0

**Principles:**
- Real-world data only (no fabrication)
- Required fields always present (empty `{}` or `[]` if not documented)
- One workflow for all cases (no case_type branching)
- Provider NOT told intended request (kept in environment_hidden_data)
- Medical necessity determined by policy.py (not hardcoded in cases)

---

## Required Schema

```json
{
  "case_id": "string",
  "case_type": "string",

  "patient_visible_data": {
    "patient_id": "string",
    "age": integer,
    "sex": "M" | "F",
    "admission_source": "string",  // free text, "" if not documented
    "chief_complaint": "string",
    "medical_history": [],
    "medications": [],
    "vital_signs": {},

    // optional if documented:
    "presenting_symptoms": "string",
    "physical_exam": "string",
    "clinical_notes": "string",
    "lab_results": {}  // structured objects (see below)
  },

  "environment_hidden_data": {
    "true_diagnosis": "string",
    "disease_severity": "string",
    "clinical_context": "string",

    "intended_request": {
      // What provider SHOULD request (ground truth)
      // Medication case:
      "medication_name": "string",
      "dosage": "string",
      "frequency": "string",
      "icd10_codes": [],
      "clinical_rationale": "string"

      // OR Procedure case:
      "procedure_name": "string",
      "cpt_code": "string",
      "icd10_codes": [],
      "clinical_indication": "string"
    }
  }
}
```

---

## Lab Results Structure

**Quantitative labs:**
```json
"lab_results": {
  "fecal_calprotectin": {
    "value": 827.162,
    "units": "ug/g"
  },
  "albumin": {
    "value": 36.1,
    "units": "g/L"
  }
}
```

**Qualitative labs:**
```json
"lab_results": {
  "t_spot_tb": {
    "result": "Negative"
  }
}
```

**If no labs documented:** `"lab_results": {}`

---

## Vital Signs (if documented)

```json
"vital_signs": {
  "temperature": "98.6 F",
  "heart_rate": "72 bpm",
  "blood_pressure": "120/80 mmHg",
  "respiratory_rate": "16/min",
  "spO2": "98%",
  "o2_requirements": "4 LPM"
}
```

**If not documented:** `"vital_signs": {}`
