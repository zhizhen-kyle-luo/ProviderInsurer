"""case type discriminator for different authorization workflows"""


class CaseType:
    INPATIENT_ADMISSION = "inpatient_admission"
    SPECIALTY_MEDICATION = "specialty_medication"
    OUTPATIENT_IMAGING = "outpatient_imaging"
    POST_ACUTE_CARE = "post_acute_care"
    CARDIAC_TESTING = "cardiac_testing"