# Experiment Run Configurations

## Overview
Single-case "AI arms race" experiment using infliximab Crohn's case.

## Parameters
- **Ic**: Insurer copilot strength (W=weak, S=strong)
- **Pc**: Provider copilot strength (W=weak, S=strong)
- **Ie**: Insurer effort level (L=low, H=high)
- **Pe**: Provider effort level (L=low, H=high)

## Run Configurations

### Run A: Baseline (Ic=W, Pc=W, Ie=H, Pe=H)
Both agents use weak copilots, high effort
```python
sim = UtilizationReviewSimulation(
    provider_llm="azure",              # strong base (default)
    payor_llm="azure",                 # strong base (default)
    provider_copilot_llm="azure",      # weak copilot
    payor_copilot_llm="azure",         # weak copilot
    provider_params=high_effort_params,
    payor_params=high_effort_params
)
```

### Run B: Asymmetric Offense (Ic=S, Pc=W, Ie=L, Pe=H)
Insurer has strong copilot & low effort, Provider has weak copilot & high effort
```python
sim = UtilizationReviewSimulation(
    provider_llm="azure",
    payor_llm="azure",
    provider_copilot_llm="azure",      # weak copilot
    payor_copilot_llm=None,            # strong copilot (use base)
    provider_params=high_effort_params,
    payor_params=low_effort_params
)
```

### Run C: Arms Race High Effort (Ic=S, Pc=S, Ie=H, Pe=H)
Both agents use strong copilots, high effort
```python
sim = UtilizationReviewSimulation(
    provider_llm="azure",
    payor_llm="azure",
    provider_copilot_llm=None,         # strong copilot (use base)
    payor_copilot_llm=None,            # strong copilot (use base)
    provider_params=high_effort_params,
    payor_params=high_effort_params
)
```

### Run C': Arms Race Low Effort (Ic=S, Pc=S, Ie=L, Pe=H)
Both agents use strong copilots, low provider but high insurer effort
```python
sim = UtilizationReviewSimulation(
    provider_llm="azure",
    payor_llm="azure",
    provider_copilot_llm=None,         # strong copilot (use base)
    payor_copilot_llm=None,            # strong copilot (use base)
    provider_params=low_effort_params,
    payor_params=low_effort_params
)
```

### Run D: Governance (TBD)
Configuration to be determined

## Environment Variables

### Required for all runs:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_NAME` (strong model)
- `AZURE_OPENAI_API_VERSION`

### Required for weak copilot runs (A, B):
- `AZURE_COPILOT_DEPLOYMENT_NAME` (weak model)
- `AZURE_COPILOT_API_VERSION` (optional, defaults to 2024-12-01-preview)

### Optional (for weak base agents):
- `AZURE_WEAK_DEPLOYMENT_NAME` (if using provider_llm="azure_weak" or payor_llm="azure_weak")

## Effort Level Parameters

### High Effort (example):
```python
high_effort_params = {
    "reasoning_depth": "thorough",
    "documentation_quality": "comprehensive",
    "oversight_level": "high"
}
```

### Low Effort (example):
```python
low_effort_params = {
    "reasoning_depth": "minimal",
    "documentation_quality": "brief",
    "oversight_level": "low"
}
```

## Verification
✅ Base agents support both strong ("azure") and weak ("azure_weak") models
✅ Copilots support both strong (None = use base) and weak ("azure") configurations
✅ All four experimental parameters can be independently varied
✅ Design supports all required experiment runs A, B, C, C', D
