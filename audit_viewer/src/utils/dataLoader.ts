import { AuditLog, AuditEvent, GroupedTurn } from '../types/audit';

export async function loadAuditLog(file: File): Promise<AuditLog> {
  const text = await file.text();
  const data = JSON.parse(text);
  if (!data.case_id || !data.events) {
    throw new Error('Invalid audit log format: missing case_id or events');
  }
  return data as AuditLog;
}

export function groupEventsByTurn(events: AuditEvent[]): GroupedTurn[] {
  const turnMap = new Map<string, GroupedTurn>();
  for (const e of events) {
    if (e.kind === 'phase_start' || e.kind === 'phase_end' || e.kind === 'metrics_calculated') continue;
    const key = `${e.phase}_${e.turn}`;
    if (!turnMap.has(key)) {
      turnMap.set(key, {
        phase: e.phase,
        turn: e.turn,
        envUpdates: [],
        lineAdjudications: [],
        providerContinues: [],
      });
    }
    const group = turnMap.get(key)!;
    if (e.kind === 'submission_built') group.submission = e;
    else if (e.kind === 'response_built') group.response = e;
    else if (e.kind === 'provider_action_chosen') group.providerAction = e;
    else if (e.kind.includes('env_') || e.kind === 'patient_visible_update') group.envUpdates.push(e);
    else if (e.kind.includes('line_adjudicated')) group.lineAdjudications.push(e);
    else if (e.kind.includes('provider_continue')) group.providerContinues.push(e);
  }
  return Array.from(turnMap.values()).sort((a, b) => {
    if (a.phase !== b.phase) return a.phase.localeCompare(b.phase);
    return a.turn - b.turn;
  });
}

export function getPhaseColor(phase: string): { bg: string; border: string; text: string } {
  if (phase.includes('phase_2')) return { bg: 'bg-blue-50', border: 'border-blue-300', text: 'text-blue-800' };
  if (phase.includes('phase_3')) return { bg: 'bg-amber-50', border: 'border-amber-300', text: 'text-amber-800' };
  if (phase.includes('phase_4')) return { bg: 'bg-green-50', border: 'border-green-300', text: 'text-green-800' };
  return { bg: 'bg-slate-50', border: 'border-slate-300', text: 'text-slate-800' };
}

export function formatPhase(phase: string): string {
  const map: Record<string, string> = {
    'phase_2_utilization_review': 'Phase 2: Utilization Review',
    'phase_3_claims': 'Phase 3: Claims Adjudication',
    'phase_4_financial': 'Phase 4: Financial Settlement',
  };
  return map[phase] || phase.replaceAll('_', ' ');
}

export function getStatusColor(status: string): string {
  const s = (status || '').toLowerCase();
  if (s === 'approved') return 'bg-green-100 text-green-800';
  if (s === 'denied') return 'bg-red-100 text-red-800';
  if (s === 'pending_info') return 'bg-yellow-100 text-yellow-800';
  if (s === 'modified') return 'bg-purple-100 text-purple-800';
  return 'bg-slate-100 text-slate-800';
}

