"""
generate mermaid graph execution traces from audit logs

creates session execution trace as directed graph showing chronological
flow of provider-payor-environment interactions.
Aggressively cleans text to prevent Mermaid syntax errors.
"""

import textwrap
from src.models.schemas import EncounterState

class MermaidAuditGenerator:
    """generates mermaid execution trace graphs from audit logs"""

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Aggressively cleans text for Mermaid labels.
        Removes ALL brackets, quotes, and special chars that break syntax.
        Returns only safe characters.
        """
        if not text:
            return ""
        # 1. Convert to string
        text = str(text)
        # 2. Replace specific problem chars with space or empty string
        # We remove [ ] ( ) " ' entirely to be safe
        for char in ['[', ']', '(', ')', '"', "'"]:
            text = text.replace(char, '')
        
        # 3. Collapse multiple spaces into one
        return " ".join(text.split())

    @staticmethod
    def wrap_text(text: str, width: int = 25) -> str:
        """Clean and wrap text with <br/> for vertical stacking"""
        clean = MermaidAuditGenerator.clean_text(text)
        return "<br/>".join(textwrap.wrap(clean, width=width))

    @staticmethod
    def generate_from_encounter_state(state: EncounterState) -> str:
        """generate mermaid graph TD execution trace from encounter state"""
        if not state.audit_log:
            return "graph TD\n    Start((No Audit Log))"

        lines = ["graph TD"]
        
        # Styles
        lines.append("    classDef prov fill:#dbeafe,stroke:#2563eb,color:#1e3a8a;")
        lines.append("    classDef pay fill:#fce7f3,stroke:#db2777,color:#831843;")
        lines.append("    classDef env fill:#e2e8f0,stroke:#334155,color:#0f172a;")
        lines.append("    Start((Start))")

        last_node_id = "Start"
        node_counter = 0

        # --- PHASE 1: PRESENTATION ---
        phase1_nodes = []
        for env_action in state.audit_log.environment_actions:
            if env_action.phase == "phase_1_presentation":
                node_counter += 1
                node_id = f"P1_Env_{node_counter}"
                
                # Clean and wrap text
                desc = MermaidAuditGenerator.wrap_text(env_action.description, width=30)
                
                # Simple quoted label
                label = f'Environment<br/>{desc}'
                phase1_nodes.append(f'{node_id}["{label}"]:::env')

        if phase1_nodes:
            lines.append("    subgraph P1 [Phase 1]")
            lines.append("        direction TB")
            for node_def in phase1_nodes:
                # Extract ID from definition (simple string split before bracket)
                curr_id = node_def.split('[')[0]
                lines.append(f"        {node_def}")
                lines.append(f"        {last_node_id} --> {curr_id}")
                last_node_id = curr_id
            lines.append("    end")

        # --- PHASE 2: PRIOR AUTH ---
        interactions = state.audit_log.interactions
        p2_interactions = [i for i in interactions if i.phase.startswith("phase_2")]

        if p2_interactions:
            lines.append("    subgraph P2 [Phase 2]")
            lines.append("        direction TB")
            
            for interaction in p2_interactions:
                node_counter += 1
                # Determine Agent & Style
                is_prov = interaction.agent.lower() == "provider"
                style = "prov" if is_prov else "pay"
                agent_name = "Provider" if is_prov else "Payor"
                
                # Format Label
                action_text = MermaidAuditGenerator.get_action_label(interaction)
                node_id = f"P2_Node_{node_counter}"
                
                # Standard double-quote wrap
                lines.append(f'        {node_id}["<b>{agent_name}</b><br/>{action_text}"]:::{style}')
                lines.append(f"        {last_node_id} --> {node_id}")
                last_node_id = node_id
                
                # Check for Environment Events (Test Results) linked to this step
                iter_num = interaction.metadata.get("iteration")
                # Only show env result if Payor approved something (Test or Tx)
                if not is_prov and "approved" in str(interaction.parsed_output).lower():
                    for ea in state.audit_log.environment_actions:
                        if ea.phase == "phase_2_pa" and ea.metadata.get("iteration") == iter_num:
                            node_counter += 1
                            env_id = f"P2_Env_{node_counter}"
                            
                            raw_name = ea.outcome.get("test_name", "Result")
                            res_text = MermaidAuditGenerator.wrap_text(raw_name, width=25)
                            
                            lines.append(f'        {env_id}["<b>Environment</b><br/>Generated: {res_text}"]:::env')
                            lines.append(f"        {last_node_id} --> {env_id}")
                            last_node_id = env_id

            lines.append("    end")

        # --- PHASE 3: CLAIMS ---
        p3_interactions = [i for i in interactions if i.phase == "phase_3_claims"]
        if p3_interactions:
            lines.append("    subgraph P3 [Phase 3]")
            lines.append("        direction TB")
            for interaction in p3_interactions:
                node_counter += 1
                is_prov = interaction.agent.lower() == "provider"
                style = "prov" if is_prov else "pay"
                agent_name = "Provider" if is_prov else "Payor"
                
                action_text = MermaidAuditGenerator.get_action_label(interaction)
                node_id = f"P3_Node_{node_counter}"
                
                lines.append(f'        {node_id}["<b>{agent_name}</b><br/>{action_text}"]:::{style}')
                lines.append(f"        {last_node_id} --> {node_id}")
                last_node_id = node_id
            lines.append("    end")

        lines.append(f"    {last_node_id} --> End((Settled))")
        return "\n".join(lines)

    @staticmethod
    def get_action_label(interaction) -> str:
        """Extracts a clean, short label for the node"""
        act = interaction.action
        parsed = interaction.parsed_output
        wrap = MermaidAuditGenerator.wrap_text
        clean = MermaidAuditGenerator.clean_text

        # Request Logic
        if "request" in act:
            req_type = parsed.get("request_type", "")
            if req_type == "treatment":
                name = parsed.get("request_details", {}).get("treatment_name", "Tx")
                return f"Req Tx: {wrap(name, 20)}"
            elif req_type == "diagnostic_test":
                name = parsed.get("request_details", {}).get("test_name", "Test")
                return f"Req Test: {wrap(name, 20)}"
            return "Requesting..."

        # Review Logic
        if "review" in act:
            status = parsed.get("authorization_status") or parsed.get("claim_status") or "Unknown"
            return f"Decision: {clean(status).upper()}"
        
        # Claim Submission
        if "submission" in act:
            amt = parsed.get("claim_submission", {}).get("amount_billed") or parsed.get("amount_billed")
            if amt:
                return f"Claim: ${amt}"
            return "Claim Submitted"

        # Appeals/Decisions
        if "decision" in act:
            dec = parsed.get("action") or parsed.get("decision") or "Unknown"
            return f"Action: {clean(dec).capitalize()}"

        # Fallback
        return wrap(act, 20)

    @staticmethod
    def save_from_state(state: EncounterState, filepath: str):
        diagram = MermaidAuditGenerator.generate_from_encounter_state(state)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(diagram)