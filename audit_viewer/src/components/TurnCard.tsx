import { useState } from 'react';
import { ChevronDown, ChevronRight, FileText, MessageSquare, Bot, Leaf } from 'lucide-react';
import { GroupedTurn, OversightMeta } from '../types/audit';
import { getStatusColor } from '../utils/dataLoader';

interface TurnCardProps {
  readonly turn: GroupedTurn;
  readonly expanded: boolean;
  readonly onToggle: () => void;
}

function JsonBlock({ data, title }: { readonly data: unknown; readonly title: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3 py-2 text-left text-sm font-medium bg-slate-50 hover:bg-slate-100 flex items-center gap-2"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        {title}
      </button>
      {open && (
        <pre className="p-3 text-xs overflow-auto max-h-96 bg-white">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function OversightPanel({ oversight }: { readonly oversight: OversightMeta }) {
  const [open, setOpen] = useState(false);
  const patchCount = oversight.edit?.patch_ops?.length || 0;
  return (
    <div className="mt-2 border border-purple-200 rounded bg-purple-50">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-purple-100"
      >
        <Bot className="w-4 h-4 text-purple-600" />
        <span className="font-medium text-purple-800">
          Copilot ({oversight.oversight_level}) - {patchCount} edits
        </span>
        {open ? <ChevronDown className="w-4 h-4 ml-auto" /> : <ChevronRight className="w-4 h-4 ml-auto" />}
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs space-y-2">
          <div className="flex gap-4 text-slate-600">
            <span>Lines expanded: {oversight.review?.view?.expanded_line_numbers?.join(', ') || 'none'}</span>
            <span>Tokens: ~{oversight.review?.view?.view_packet_tokens_proxy}</span>
          </div>
          {patchCount > 0 && (
            <div>
              <div className="font-medium text-purple-700 mb-1">Patches applied:</div>
              {oversight.edit.patch_ops!.map((p, i) => (
                <div key={i} className="bg-white rounded px-2 py-1 mb-1 font-mono text-xs">
                  <span className="text-purple-600">{p.op}</span> {p.path}
                  {p.value !== undefined && (
                    <span className="text-slate-500"> = {JSON.stringify(p.value).slice(0, 80)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {oversight.edit?.error && (
            <div className="text-red-600">Error: {oversight.edit.error}</div>
          )}
        </div>
      )}
    </div>
  );
}

function LineStatusBadges({ lines }: { readonly lines: Array<{ line_number: number; status: string }> }) {
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {lines.map((l) => (
        <span key={l.line_number} className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(l.status)}`}>
          L{l.line_number}: {l.status}
        </span>
      ))}
    </div>
  );
}

export function TurnCard({ turn, expanded, onToggle }: TurnCardProps) {
  const sub = turn.submission?.payload?.submission;
  const resp = turn.response?.payload?.response;
  const subOversight = sub?.oversight as OversightMeta | undefined;
  const respOversight = resp?.oversight as OversightMeta | undefined;
  const getSubmissionLines = () => {
    if (sub?.insurer_request?.requested_services) return sub.insurer_request.requested_services;
    if (sub?.claim_submission?.billed_lines) return sub.claim_submission.billed_lines;
    return [];
  };
  const getResponseStatuses = () => {
    const adjs = resp?.payor_response?.line_adjudications || [];
    return adjs.map((a: Record<string, unknown>) => ({
      line_number: a.line_number as number,
      status: (a.authorization_status || a.adjudication_status || 'unknown') as string,
    }));
  };
  const submissionLines = getSubmissionLines();
  const responseStatuses = getResponseStatuses();
  const providerAction = turn.providerAction?.payload?.provider_action;

  return (
    <div className="bg-white rounded-lg border border-slate-200 shadow-sm">
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-slate-50 text-left"
      >
        {expanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
        <span className="font-bold text-lg">Turn {turn.turn}</span>
        <span className="text-sm text-slate-500">
          {submissionLines.length} lines submitted
        </span>
        <div className="ml-auto flex gap-1">
          {responseStatuses.map((s: { line_number: number; status: string }) => (
            <span key={s.line_number} className={`px-1.5 py-0.5 rounded text-xs ${getStatusColor(s.status)}`}>
              {s.status.slice(0, 3).toUpperCase()}
            </span>
          ))}
        </div>
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-4">
          {turn.submission && (
            <div className="border-l-4 border-blue-400 pl-3">
              <div className="flex items-center gap-2 text-blue-700 font-semibold">
                <FileText className="w-4 h-4" />
                Provider Submission
              </div>
              {subOversight && <OversightPanel oversight={subOversight} />}
              <JsonBlock data={sub?.insurer_request || sub?.claim_submission} title="Final Submission JSON" />
              <JsonBlock data={sub?.raw} title="Raw LLM Output" />
            </div>
          )}
          {turn.response && (
            <div className="border-l-4 border-amber-400 pl-3">
              <div className="flex items-center gap-2 text-amber-700 font-semibold">
                <MessageSquare className="w-4 h-4" />
                Payor Response
              </div>
              <LineStatusBadges lines={responseStatuses} />
              {respOversight && <OversightPanel oversight={respOversight} />}
              <JsonBlock data={resp?.payor_response} title="Final Response JSON" />
              <JsonBlock data={resp?.raw} title="Raw LLM Output" />
            </div>
          )}
          {turn.envUpdates.length > 0 && (
            <div className="border-l-4 border-green-400 pl-3">
              <div className="flex items-center gap-2 text-green-700 font-semibold">
                <Leaf className="w-4 h-4" />
                Environment Updates ({turn.envUpdates.length})
              </div>
              {turn.envUpdates.map((e, i) => (
                <JsonBlock key={i} data={e.payload} title={`${e.kind} (line ${e.payload?.line_number || '?'})`} />
              ))}
            </div>
          )}
          {providerAction && (
            <div className="border-l-4 border-slate-400 pl-3">
              <div className="text-slate-700 font-semibold">Provider Action</div>
              <div className="text-sm mt-1">
                <span className="font-medium">{providerAction.action}</span>
                {providerAction.lines?.length > 0 && (
                  <span className="text-slate-500 ml-2">
                    ({providerAction.lines.length} lines: {providerAction.lines.map((l: Record<string, unknown>) => l.intent || `→L${l.to_level}`).join(', ')})
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
