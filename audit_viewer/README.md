# Audit Log Viewer

professional React-based viewer for debugging multi-agent healthcare simulation audit logs

## Features

- **Debug Mode**: toggle between raw LLM responses and parsed JSON for every interaction
- **Error Visualization**: red border + warning badges for parse failures
- **Oversight Workflow**: visual grouping of draft → oversight → final sequences
- **Timeline View**: vertical timeline with phase grouping and color-coded agents
- **Paper Ready**: clean typography and professional styling for research figures

## Setup

```bash
cd audit_viewer
npm install
npm run dev
```

open http://localhost:3000

## Usage

1. run experiment to generate audit logs:
   ```bash
   cd ..
   python examples/run_experiment.py A
   ```
   this creates both `run_A_audit_log.md` (for reading) and `run_A_audit_log.json` (for viewer)

2. in the viewer, click "Choose File" or drag-drop the JSON file
   (e.g., `experiment_results/run_A_audit_log.json`)

3. toggle "Raw" / "Parsed" buttons on each card to debug JSON parsing

4. cards with parse errors show red border + error details

5. collapsible prompts section shows system/user prompts

## Color Scheme

- **Provider**: blue-500 to cyan-400 gradient, blue-50 background
- **Payor**: amber-500 to orange-400 gradient, orange-50 background
- **Parse Error**: red-500 border, red-50 background

## Input Format

expects JSON file from `audit_logger.save_to_json()`:

```json
{
  "case_id": "string",
  "simulation_start": "ISO timestamp",
  "simulation_end": "ISO timestamp",
  "interactions": [
    {
      "interaction_id": "string",
      "timestamp": "ISO timestamp",
      "phase": "phase_2_utilization_review | phase_3_claims",
      "agent": "provider | payor",
      "action": "copilot_draft | oversight_edit | ...",
      "system_prompt": "string",
      "user_prompt": "string",
      "llm_response": "raw text from LLM",
      "parsed_output": {},
      "metadata": {}
    }
  ],
  "summary": {}
}
```

## Build for Production

```bash
npm run build
npm run preview
```
