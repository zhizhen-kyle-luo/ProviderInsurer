# Audit Log Viewer

professional React-based viewer for debugging multi-agent healthcare simulation audit logs

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
