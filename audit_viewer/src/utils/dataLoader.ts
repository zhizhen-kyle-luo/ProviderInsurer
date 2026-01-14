import { AuditLog } from '../types/audit';

export async function loadAuditLog(file: File): Promise<AuditLog> {
  const text = await file.text();
  const data = JSON.parse(text);

  // validate required fields
  if (!data.case_id || !data.interactions) {
    throw new Error('Invalid audit log format: missing case_id or interactions');
  }

  return data as AuditLog;
}

export function hasParseError(interaction: any): boolean {
  const parsed = interaction.parsed_output || {};
  const hasError = parsed.error === 'json_parse_failed' ||
                   parsed.parse_error === true ||
                   interaction.metadata?.error_type?.includes('parse_error');

  const hasResponse = interaction.llm_response && interaction.llm_response.length > 0;
  const parsedIsEmpty = !parsed || Object.keys(parsed).length === 0 ||
                       (Object.keys(parsed).length === 1 && parsed.error);

  return hasError || (hasResponse && parsedIsEmpty);
}

export function getAgentColor(agent: string): { gradient: string; bg: string; text: string } {
  switch (agent.toLowerCase()) {
    case 'provider':
      return {
        gradient: 'from-blue-500 to-cyan-400',
        bg: 'bg-blue-50',
        text: 'text-blue-700'
      };
    case 'payor':
      return {
        gradient: 'from-amber-500 to-orange-400',
        bg: 'bg-orange-50',
        text: 'text-orange-700'
      };
    default:
      return {
        gradient: 'from-slate-500 to-gray-400',
        bg: 'bg-slate-50',
        text: 'text-slate-700'
      };
  }
}

export function formatPhase(phase: string): string {
  const phaseMap: Record<string, string> = {
    'phase_1_presentation': 'Phase 1: Patient Presentation',
    'phase_2_pa': 'Phase 2: Prior Authorization',
    'phase_2_utilization_review': 'Phase 2: Utilization Review',
    'phase_2_pa_appeal': 'Phase 2: PA Appeal',
    'phase_3_claims': 'Phase 3: Claims Adjudication',
    'phase_4_financial': 'Phase 4: Financial Settlement'
  };

  return phaseMap[phase] || phase.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
}