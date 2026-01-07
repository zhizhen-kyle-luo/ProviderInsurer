# Policy Schema

This schema represents reference policy artifacts used by agents as their decision rulebooks under information asymmetry.

- Provider policies: public clinical practice guidelines (e.g., AGA, GOLD)
- Payer policies: public coverage / utilization-management policies (e.g., UHC, Cigna, InterQual)

These artifacts are nputs to the simulation.

---

## Design Principles

- Keep the raw policy source for traceability.
- Extract only the minimum computable knobs required by the simulation.
- Do not attempt to fully encode real-world policies.
- Support heterogeneous, narrative policy documents.
- Enable explicit modeling of provider vs insurer interpretation differences.

---

## Schema

```json
{
  "policy_id": "string",
  "policy_type": "provider_guideline" | "payer_coverage_policy",
  "issuer": "string",
  "source": {
    "url": "string"
  },

  "phase2": {
    "requires_phase2": true | false | "unknown",
    "phase2_type": "PA" | "concurrent_review" | "none" | "unknown"
  },

   "content": {
    "format": "structured" | "free_text" | "mixed",
    "data": "object",     // existing dict keys live here
    "text": "string"      // optional raw excerpt if useful
  },

  "notes_free_text": "string"
}
