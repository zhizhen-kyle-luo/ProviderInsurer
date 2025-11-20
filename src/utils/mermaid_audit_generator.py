"""
generate mermaid graph execution traces from audit logs

creates session execution trace as directed graph showing chronological
flow of provider-payor-environment interactions
"""

from typing import List
from src.models.schemas import AuditLog, EncounterState


class MermaidAuditGenerator:
    """generates mermaid execution trace graphs from audit logs"""

    @staticmethod
    def generate_from_encounter_state(state: EncounterState) -> str:
        """generate mermaid graph TD execution trace from encounter state"""
        if not state.audit_log:
            return "graph TD\n    Start((No Audit Log))"

        lines = ["graph TD"]

        # style definitions
        lines.append("    %% Styles")
        lines.append("    classDef prov fill:#dbeafe,stroke:#2563eb,color:#1e3a8a;")
        lines.append("    classDef pay fill:#fce7f3,stroke:#db2777,color:#831843;")
        lines.append("    classDef env fill:#e2e8f0,stroke:#334155,color:#0f172a;")
        lines.append("")

        # start node
        lines.append("    Start((Start))")
        lines.append("")

        # track last node for edges
        last_node_id = "Start"
        node_counter = 0

        # phase 1: environment actions (noise introduction)
        phase1_nodes = []
        for env_action in state.audit_log.environment_actions:
            if env_action.phase == "phase_1_presentation":
                node_counter += 1
                node_id = f"Env_P1_{node_counter}"
                # show full description for environment actions
                action_desc = env_action.description

                phase1_nodes.append((node_id, f"[<b>Environment</b><br/>{action_desc}]:::env"))

        if phase1_nodes:
            lines.append("    %% --- PHASE 1: PATIENT PRESENTATION ---")
            lines.append("    subgraph Phase1 [Phase 1: Patient Presentation]")
            lines.append("        direction TB")
            lines.append("")

            for i, (node_id, node_def) in enumerate(phase1_nodes):
                lines.append(f"        {node_id}{node_def}")
                if i == 0:
                    lines.append(f"        {last_node_id} --> {node_id}")
                else:
                    prev_node = phase1_nodes[i-1][0]
                    lines.append(f"        {prev_node} --> {node_id}")
                last_node_id = node_id

            lines.append("    end")
            lines.append("")

        # phase 2: prior authorization interactions
        phase2_interactions = [i for i in state.audit_log.interactions if i.phase.startswith("phase_2")]

        if phase2_interactions:
            lines.append("    %% --- PHASE 2: PRIOR AUTHORIZATION ---")
            lines.append("    subgraph Phase2 [Phase 2: Prior Authorization]")
            lines.append("        direction TB")
            lines.append("")

            iteration_tracker = {}
            for interaction in phase2_interactions:
                node_counter += 1
                agent = interaction.agent.capitalize()

                # get iteration number from metadata
                iteration = interaction.metadata.get("iteration", 1)

                # create node id
                agent_prefix = "Prov" if interaction.agent == "provider" else "Pay"
                node_id = f"P2_Iter{iteration}_{agent_prefix}"

                # format action label
                action_label = MermaidAuditGenerator._format_action_label(interaction)

                # get confidence or status
                detail = ""
                if interaction.agent == "provider":
                    conf = interaction.metadata.get("confidence")
                    if conf:
                        detail = f"<br/>Conf: {conf:.2f}"
                elif interaction.agent == "payor":
                    status = interaction.parsed_output.get("authorization_status", "")
                    if status:
                        detail = f"<br/>{status.upper()}"

                # node style
                style_class = "prov" if interaction.agent == "provider" else "pay"

                # create node
                node_def = f"{node_id}[<b>{agent}</b><br/>{action_label}{detail}]:::{style_class}"
                lines.append(f"        {node_def}")

                # edge from last node
                lines.append(f"        {last_node_id} --> {node_id}")
                last_node_id = node_id

                # add environment actions between iterations
                # check if there are environment test generation actions
                for env_action in state.audit_log.environment_actions:
                    if (env_action.phase == "phase_2_pa" and
                        env_action.action_type == "generate_test_result" and
                        env_action.metadata.get("iteration") == iteration):

                        node_counter += 1
                        env_node_id = f"Env_P2_{node_counter}"
                        test_name = env_action.outcome.get("test_name", "test")[:30]
                        env_node_def = f"{env_node_id}[<b>Environment</b><br/>Generate: {test_name}]:::env"

                        lines.append(f"        {env_node_def}")
                        lines.append(f"        {last_node_id} --> {env_node_id}")
                        last_node_id = env_node_id

                lines.append("")

            lines.append("    end")
            lines.append("")

        # phase 3: claims adjudication interactions
        phase3_interactions = [i for i in state.audit_log.interactions if i.phase == "phase_3_claims"]

        if phase3_interactions:
            lines.append("    %% --- PHASE 3: CLAIMS ADJUDICATION ---")
            lines.append("    subgraph Phase3 [Phase 3: Claims Adjudication]")
            lines.append("        direction TB")
            lines.append("")

            p3_node_counter = 0
            for interaction in phase3_interactions:
                p3_node_counter += 1
                agent = interaction.agent.capitalize()
                agent_prefix = "Prov" if interaction.agent == "provider" else "Pay"
                node_id = f"P3_{agent_prefix}{p3_node_counter}"

                # format action label
                action_label = MermaidAuditGenerator._format_action_label(interaction)

                # node style
                style_class = "prov" if interaction.agent == "provider" else "pay"

                # create node
                node_def = f"{node_id}[<b>{agent}</b><br/>{action_label}]:::{style_class}"
                lines.append(f"        {node_def}")

                # edge from last node
                lines.append(f"        {last_node_id} --> {node_id}")
                last_node_id = node_id
                lines.append("")

            lines.append("    end")
            lines.append("")

        # end node
        lines.append(f"    {last_node_id} --> End((Settled))")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_action_label(interaction) -> str:
        """format interaction action into concise node label"""
        action = interaction.action
        parsed = interaction.parsed_output

        # phase 2 actions
        if action == "treatment_request":
            request_type = parsed.get("request_type", "")
            if request_type == "treatment":
                details = parsed.get("request_details", {})
                treatment_name = details.get("treatment_name", "treatment")[:35]
                return f"Req: {treatment_name}"
            elif request_type == "diagnostic_test":
                details = parsed.get("request_details", {})
                test_name = details.get("test_name", "test")[:35]
                return f"Test Req: {test_name}"
            else:
                return "PA Request"

        elif action == "diagnostic_test_request":
            # handle diagnostic test requests
            details = parsed.get("request_details", {})
            test_name = details.get("test_name", "diagnostic test")[:35]
            return f"Test Req: {test_name}"

        elif action == "diagnostic_test_review":
            status = parsed.get("authorization_status", "unknown")
            if status == "approved":
                return "Test APPROVED"
            elif status == "denied":
                return "Test DENIED"
            else:
                return f"Test {status.upper()}"

        elif action == "treatment_review":
            status = parsed.get("authorization_status", "unknown")
            if status == "approved":
                return "PA APPROVED"
            elif status == "denied":
                return "PA DENIED"
            else:
                return f"PA {status.upper()}"

        # phase 3 actions
        elif action == "claim_submission":
            amount = parsed.get("claim_submission", {}).get("amount_billed", 0)
            if amount:
                return f"Submit Claim (${amount:,.0f})"
            return "Submit Claim"

        elif action == "claim_review":
            status = parsed.get("claim_status", "unknown")
            if status == "approved":
                return "Claim APPROVED"
            elif status == "denied":
                return "Claim DENIED"
            else:
                return f"Claim {status.upper()}"

        elif action == "claim_denial_decision":
            decision = parsed.get("decision", "unknown")
            if decision == "write_off":
                return "Decision: Write Off"
            elif decision == "appeal":
                return "Decision: Appeal"
            elif decision == "bill_patient":
                return "Decision: Bill Patient"
            else:
                return "Provider Decision"

        elif action == "claim_appeal_submission":
            iteration = interaction.metadata.get("appeal_iteration", "")
            return f"Submit Appeal #{iteration}" if iteration else "Submit Appeal"

        elif action == "claim_appeal_review":
            outcome = parsed.get("appeal_outcome", "unknown")
            if outcome == "approved":
                return "Appeal APPROVED"
            elif outcome == "denied":
                return "Appeal DENIED"
            else:
                return f"Appeal {outcome.upper()}"

        # generic fallback
        return action.replace("_", " ").title()[:30]

    @staticmethod
    def save_from_state(state: EncounterState, filepath: str):
        """generate and save mermaid diagram from encounter state"""
        diagram = MermaidAuditGenerator.generate_from_encounter_state(state)
        with open(filepath, 'w') as f:
            f.write(diagram)
