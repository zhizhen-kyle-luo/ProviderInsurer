export interface AuditEvent {
  ts: string;
  phase: string;
  turn: number;
  kind: string;
  actor: string | null;
  payload: Record<string, any>;
}

export interface OversightMeta {
  role: string;
  oversight_level: string;
  review: {
    selector: {
      selector_used: boolean;
      requested_k: number;
      picked_lines: number[];
      raw_selector_output: string;
    };
    view: {
      draft_mode: string;
      expanded_line_numbers: number[];
      expanded_line_count: number;
      view_packet_tokens_proxy: number;
      view_packet_chars: number;
    };
  };
  edit: {
    budget?: {
      patch_ops: number;
      paths_touched: number;
      max_patch_ops: number;
      max_paths_touched: number;
      truncated: boolean;
    };
    patch_ops?: Array<{ op: string; path: string; value: any }>;
    raw_patch_text?: string;
    error?: string;
  };
}

export interface AuditLog {
  case_id: string;
  run_id: string;
  simulation_start: string;
  simulation_end: string | null;
  events: AuditEvent[];
  agent_configs: Record<string, any>;
  summary: Record<string, any>;
}

export interface GroupedTurn {
  phase: string;
  turn: number;
  submission?: AuditEvent;
  response?: AuditEvent;
  providerAction?: AuditEvent;
  envUpdates: AuditEvent[];
  lineAdjudications: AuditEvent[];
  providerContinues: AuditEvent[];
}
