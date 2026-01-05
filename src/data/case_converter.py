"""
Convert raw case dictionaries to structured Pydantic models
"""
import json
from pathlib import Path
from src.models.schemas import (
    PatientDemographics,
    InsuranceInfo,
    AdmissionNotification,
    ClinicalPresentation
)


def load_case_from_json(json_path):
    """load case from JSON file"""
    with open(json_path, 'r') as f:
        return json.load(f)


def convert_case_to_models(case_dict):
    """
    Convert raw case dictionary to structured models for simulation.
    This allows cases to be stored as simple dicts but converted to
    Pydantic models when needed by the simulation.
    handles all case types with one unified workflow.
    """
    patient_pres = case_dict.get("patient_visible_data")
    if not patient_pres:
        raise ValueError("case must have patient_visible_data")

    case_type = case_dict.get("case_type")
    if not case_type:
        raise ValueError("case must have case_type field")

    patient_demographics = PatientDemographics(
        patient_id=patient_pres["patient_id"],
        age=patient_pres["age"],
        sex=patient_pres["sex"],
        mrn=patient_pres.get("patient_id")
    )

    insurance_info = InsuranceInfo(
        plan_type="MA",
        payer_name="Medicare Advantage",
        member_id=patient_demographics.patient_id,
        authorization_required=True
    )

    admission = AdmissionNotification(
        patient_demographics=patient_demographics,
        insurance=insurance_info,
        admission_source=patient_pres.get("admission_source", ""),
        chief_complaint=patient_pres["chief_complaint"],
        preliminary_diagnoses=[]
    )

    clinical_presentation = ClinicalPresentation(
        chief_complaint=patient_pres["chief_complaint"],
        history_of_present_illness=patient_pres.get("presenting_symptoms", ""),
        vital_signs=patient_pres["vital_signs"],
        physical_exam_findings="",
        medical_history=patient_pres["medical_history"]
    )

    case_dict["admission"] = admission
    case_dict["clinical_presentation"] = clinical_presentation
    case_dict["case_type"] = case_type
    # provider creates authorization_request during simulation
    # intended_request stays in environment_hidden_data for ground truth comparison only

    return case_dict
