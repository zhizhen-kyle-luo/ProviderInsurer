import { useState } from 'react';
import { ChevronDown, ChevronRight, FileText, MessageSquare, Leaf, Cpu, Eye, Edit3, Zap } from 'lucide-react';
import { GroupedTurn, OversightMeta } from '../types/audit';
import { getStatusColor } from '../utils/dataLoader';

interface TurnCardProps {
  readonly turn: GroupedTurn;
  readonly expanded: boolean;
  readonly onToggle: () => void;
}

interface LLMCallProps {
  readonly label: string;
  readonly icon: React.ReactNode;
  readonly color: string;
  readonly systemPrompt?: string;
  readonly userPrompt?: string;
  readonly output?: string;
  readonly defaultOpen?: boolean;
}

function LLMCallBlock({ label, icon, color, systemPrompt, userPrompt, output, defaultOpen = false }: LLMCallProps) {
  const [open, setOpen] = useState(defaultOpen);
  if (!systemPrompt && !userPrompt && !output) return null;

  return (
    <div className={`border-l-4 ${color} pl-3 py-2`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm font-semibold hover:opacity-80 w-full text-left"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        {icon}
        <span>{label}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-xs">
          {systemPrompt && (
            <details className="bg-slate-50 rounded border">
              <summary className="px-2 py-1 cursor-pointer font-medium text-slate-600 hover:bg-slate-100">
                System Prompt ({systemPrompt.length} chars)
              </summary>
              <pre className="px-2 py-1 whitespace-pre-wrap max-h-48 overflow-auto bg-white border-t text-slate-700">
                {systemPrompt}
              </pre>
            </details>
          )}
          {userPrompt && (
            <details className="bg-slate-50 rounded border">
              <summary className="px-2 py-1 cursor-pointer font-medium text-slate-600 hover:bg-slate-100">
                User Prompt ({userPrompt.length} chars)
              </summary>
              <pre className="px-2 py-1 whitespace-pre-wrap max-h-64 overflow-auto bg-white border-t text-slate-700">
                {userPrompt}
              </pre>
            </details>
          )}
          {output && (
            <details open className="bg-green-50 rounded border border-green-200">
              <summary className="px-2 py-1 cursor-pointer font-medium text-green-700 hover:bg-green-100">
                Output ({output.length} chars)
              </summary>
              <pre className="px-2 py-1 whitespace-pre-wrap max-h-64 overflow-auto bg-white border-t text-slate-700">
                {output}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function LineStatusBadges({ lines }: { readonly lines: Array<{ line_number: number; status: string }> }) {
  return (
    <div className="flex flex-wrap gap-1">
      {lines.map((l) => (
        <span key={l.line_number} className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(l.status)}`}>
          L{l.line_number}: {l.status}
        </span>
      ))}
    </div>
  );
}

function OversightCallsBlock({ oversight, actorLabel }: { readonly oversight: OversightMeta; readonly actorLabel: string }) {
  const selectorPrompts = oversight.review?.selector?.prompts;
  const editorPrompts = oversight.prompts;
  const patchCount = oversight.edit?.patch_ops?.length || 0;

  return (
    <div className="space-y-1">
      {oversight.review?.selector?.selector_used && (
        <LLMCallBlock
          label={`${actorLabel} Selector (picked: ${oversight.review.selector.picked_lines?.join(', ') || 'none'})`}
          icon={<Eye className="w-4 h-4 text-indigo-600" />}
          color="border-indigo-400"
          systemPrompt={selectorPrompts?.system_prompt}
          userPrompt={selectorPrompts?.user_prompt}
          output={oversight.review.selector.raw_selector_output}
        />
      )}
      <LLMCallBlock
        label={`${actorLabel} Editor (${patchCount} patches)`}
        icon={<Edit3 className="w-4 h-4 text-purple-600" />}
        color="border-purple-400"
        systemPrompt={editorPrompts?.system_prompt}
        userPrompt={editorPrompts?.user_prompt}
        output={oversight.edit?.raw_patch_text || '[]'}
      />
      {patchCount > 0 && (
        <div className="ml-4 mt-1 space-y-1">
          {oversight.edit.patch_ops!.map((p, i) => (
            <div key={i} className="bg-purple-50 rounded px-2 py-1 text-xs font-mono border border-purple-200">
              <span className="text-purple-700 font-semibold">{p.op}</span>{' '}
              <span className="text-slate-600">{p.path}</span>
              {p.value !== undefined && (
                <span className="text-slate-500"> = {JSON.stringify(p.value).slice(0, 100)}</span>
              )}
            </div>
          ))}
        </div>
      )}
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
    <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
      {/* header */}
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-slate-50 text-left bg-gradient-to-r from-slate-50 to-white"
      >
        {expanded ? <ChevronDown className="w-5 h-5 text-slate-400" /> : <ChevronRight className="w-5 h-5 text-slate-400" />}
        <span className="font-bold text-lg text-slate-800">Turn {turn.turn}</span>
        <span className="text-sm text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
          {submissionLines.length} lines
        </span>
        <div className="ml-auto">
          <LineStatusBadges lines={responseStatuses} />
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-100">
          {/* step 1: provider copilot (or agent if no oversight) */}
          {turn.submission && (
            <div className="pt-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-700">1</div>
                <FileText className="w-4 h-4 text-blue-600" />
                <span className="font-semibold text-blue-800">{subOversight ? 'Provider Copilot' : 'Provider Agent'}</span>
              </div>
              <LLMCallBlock
                label="Draft Submission"
                icon={<Cpu className="w-4 h-4 text-blue-600" />}
                color="border-blue-400"
                systemPrompt={sub?.prompts?.system_prompt}
                userPrompt={sub?.prompts?.user_prompt}
                output={sub?.raw}
                defaultOpen={false}
              />
            </div>
          )}

          {/* step 2: provider oversight (if present) */}
          {subOversight && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-700">2</div>
                <Eye className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-indigo-800">Provider Oversight ({subOversight.oversight_level})</span>
              </div>
              <OversightCallsBlock oversight={subOversight} actorLabel="Provider" />
            </div>
          )}

          {/* step 3: payor copilot (or agent if no oversight) */}
          {turn.response && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-full bg-amber-100 flex items-center justify-center text-xs font-bold text-amber-700">{subOversight ? 3 : 2}</div>
                <MessageSquare className="w-4 h-4 text-amber-600" />
                <span className="font-semibold text-amber-800">{respOversight ? 'Payor Copilot' : 'Payor Agent'}</span>
              </div>
              <LLMCallBlock
                label="Draft Response"
                icon={<Cpu className="w-4 h-4 text-amber-600" />}
                color="border-amber-400"
                systemPrompt={resp?.prompts?.system_prompt}
                userPrompt={resp?.prompts?.user_prompt}
                output={resp?.raw}
                defaultOpen={false}
              />
            </div>
          )}

          {/* step 4: payor oversight (if present) */}
          {respOversight && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center text-xs font-bold text-purple-700">{subOversight ? 4 : 3}</div>
                <Eye className="w-4 h-4 text-purple-600" />
                <span className="font-semibold text-purple-800">Payor Oversight ({respOversight.oversight_level})</span>
              </div>
              <OversightCallsBlock oversight={respOversight} actorLabel="Payor" />
            </div>
          )}

          {/* step 5: environment updates */}
          {turn.envUpdates.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center text-xs font-bold text-green-700">
                  {(subOversight ? 2 : 1) + (respOversight ? 2 : 1) + 1}
                </div>
                <Leaf className="w-4 h-4 text-green-600" />
                <span className="font-semibold text-green-800">Environment ({turn.envUpdates.length} updates)</span>
              </div>
              <div className="space-y-1 ml-8">
                {turn.envUpdates.map((e, i) => {
                  const isSynthesized = e.payload?.fabricated === true || e.payload?.source === 'llm_synthesized';
                  const isGroundTruth = e.payload?.fabricated === false || e.payload?.source === 'ground_truth';
                  return (
                    <details key={i} className="bg-green-50 rounded border border-green-200">
                      <summary className="px-2 py-1 cursor-pointer text-xs font-medium text-green-700 hover:bg-green-100 flex items-center gap-2">
                        <span>
                          {e.kind} {e.payload?.line_number ? `(line ${e.payload.line_number})` : ''}
                        </span>
                        {isSynthesized && (
                          <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-semibold">
                            LLM Synthesized
                          </span>
                        )}
                        {isGroundTruth && (
                          <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-semibold">
                            Ground Truth
                          </span>
                        )}
                      </summary>
                      <pre className="px-2 py-1 text-xs whitespace-pre-wrap max-h-32 overflow-auto bg-white border-t">
                        {JSON.stringify(e.payload, null, 2)}
                      </pre>
                    </details>
                  );
                })}
              </div>
            </div>
          )}

          {/* provider action LLM call */}
          {turn.providerActionLLMCall && (
            <div className="pt-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center text-xs font-bold text-slate-700">
                  {(subOversight ? 2 : 1) + (respOversight ? 2 : 1) + (turn.envUpdates.length > 0 ? 1 : 0) + 1}
                </div>
                <Zap className="w-4 h-4 text-slate-600" />
                <span className="font-semibold text-slate-800">Provider Action Decision</span>
              </div>
              <LLMCallBlock
                label="Choose Next Action"
                icon={<Cpu className="w-4 h-4 text-slate-600" />}
                color="border-slate-400"
                systemPrompt={turn.providerActionLLMCall.payload?.prompts?.system_prompt}
                userPrompt={turn.providerActionLLMCall.payload?.prompts?.user_prompt}
                output={turn.providerActionLLMCall.payload?.raw_response}
                defaultOpen={false}
              />
            </div>
          )}

          {/* provider action summary */}
          {providerAction && (
            <div className="bg-slate-50 rounded-lg p-3 border">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-slate-600" />
                <span className="font-semibold text-slate-700">Provider Action:</span>
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                  providerAction.action === 'LINE_ACTIONS' ? 'bg-blue-100 text-blue-800' :
                  providerAction.action === 'RESUBMIT' ? 'bg-amber-100 text-amber-800' :
                  providerAction.action === 'CONTINUE' ? 'bg-green-100 text-green-800' :
                  providerAction.action === 'APPEAL' ? 'bg-amber-100 text-amber-800' :
                  'bg-red-100 text-red-800'
                }`}>
                  {providerAction.action}
                </span>
              </div>
              {providerAction.line_actions?.length > 0 && (
                <div className="mt-2 space-y-1 text-xs">
                  {providerAction.line_actions.map((la: Record<string, unknown>) => (
                    <div key={la.line_number as number} className="flex items-center gap-2">
                      <span className="font-mono text-slate-500">L{la.line_number}</span>
                      <span className={`px-1.5 py-0.5 rounded font-medium ${
                        la.action === 'ACCEPT_MODIFY' ? 'bg-green-100 text-green-700' :
                        la.action === 'PROVIDE_DOCS' ? 'bg-blue-100 text-blue-700' :
                        la.action === 'APPEAL' ? 'bg-amber-100 text-amber-700' :
                        la.action === 'ABANDON' ? 'bg-red-100 text-red-700' :
                        'bg-slate-100 text-slate-700'
                      }`}>
                        {la.action as string}
                      </span>
                      {la.to_level && <span className="text-slate-500">→ level {la.to_level as number}</span>}
                      {la.mode && <span className="text-slate-500">({la.mode as string})</span>}
                    </div>
                  ))}
                </div>
              )}
              {providerAction.reasoning && (
                <div className="mt-2 text-xs text-slate-600 italic">
                  {providerAction.reasoning as string}
                </div>
              )}
            </div>
          )}

          {/* final results summary */}
          <div className="bg-gradient-to-r from-slate-50 to-slate-100 rounded-lg p-3 border">
            <div className="text-xs font-semibold text-slate-600 mb-2">Final Line Statuses:</div>
            <LineStatusBadges lines={responseStatuses} />
          </div>
        </div>
      )}
    </div>
  );
}
