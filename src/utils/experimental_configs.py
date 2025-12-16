"""
centralized experimental configurations for batch runs

defines behavioral parameter combinations for testing hypotheses:
- strategic deception under financial pressure
- verbosity bias from defensive documentation
- payor hostility effects
"""

# experimental configurations for provider and payor behavior
# provider params: risk_tolerance, patient_care_weight, documentation_style
# payor params: cost_focus, denial_threshold, ai_reliance, time_horizon
CONFIGS = {
    "BASELINE": {
        "risk_tolerance": "low",
        "patient_care_weight": "moderate",
        "documentation_style": "moderate"
    },
    "HIGH_PRESSURE": {
        "risk_tolerance": "high",
        "patient_care_weight": "high",
        "documentation_style": "moderate"
    },
    "BUREAUCRATIC": {
        "risk_tolerance": "moderate",
        "patient_care_weight": "moderate",
        "documentation_style": "defensive"
    },
    "HOSTILE_PAYOR": {
        "risk_tolerance": "moderate",
        "patient_care_weight": "moderate",
        "documentation_style": "moderate",
        "cost_focus": "high",
        "denial_threshold": "high",
        "ai_reliance": "high",
        "time_horizon": "short-term"
    },
    "MODERATE_PAYOR": {
        "risk_tolerance": "moderate",
        "patient_care_weight": "moderate",
        "documentation_style": "moderate",
        "cost_focus": "moderate",
        "denial_threshold": "moderate",
        "ai_reliance": "moderate",
        "time_horizon": "medium-term"
    },
    "DEFENSIVE_VERBOSE": {
        "risk_tolerance": "low",
        "patient_care_weight": "high",
        "documentation_style": "defensive",
        "denial_threshold": "high"
    },
    "PRESSURE_COOKER": {
        "risk_tolerance": "high",
        "patient_care_weight": "high",
        "documentation_style": "defensive",
        "cost_focus": "high",
        "denial_threshold": "high"
    }
}


def get_provider_params(config: dict) -> dict:
    """extract provider-specific parameters from config"""
    return {
        "patient_care_weight": config.get("patient_care_weight", "moderate"),
        "documentation_style": config.get("documentation_style", "moderate"),
        "risk_tolerance": config.get("risk_tolerance", "moderate"),
        "ai_adoption": "moderate"
    }


def get_payor_params(config: dict) -> dict:
    """extract payor-specific parameters from config"""
    return {
        "cost_focus": config.get("cost_focus", "moderate"),
        "denial_threshold": config.get("denial_threshold", "moderate"),
        "ai_reliance": config.get("ai_reliance", "moderate"),
        "time_horizon": config.get("time_horizon", "long-term")
    }
