export interface LLMInteraction {
  interaction_id: string;
  timestamp: string;
  phase: string;
  agent: "provider" | "payor" | "environment";
  action: string;
  system_prompt: string;
  user_prompt: string;
  llm_response: string;
  parsed_output: Record<string, any>;
  metadata: Record<string, any>;
}

export interface EnvironmentAction {
  action_id: string;
  timestamp: string;
  phase: string;
  action_type: string;
  description: string;
  outcome: Record<string, any>;
  metadata: Record<string, any>;
}

export interface AuditLog {
  case_id: string;
  simulation_start: string;
  simulation_end: string | null;
  interactions: LLMInteraction[];
  environment_actions?: EnvironmentAction[];
  agent_configurations?: any[];
  summary: Record<string, any>;
}