import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { LLMInteraction } from '../types/audit';
import { getAgentColor, hasParseError } from '../utils/dataLoader';

interface InteractionCardProps {
  interaction: LLMInteraction;
  index: number;
}

export function InteractionCard({ interaction, index }: InteractionCardProps) {
  const [showPrompts, setShowPrompts] = useState(false);

  const colors = getAgentColor(interaction.agent);
  const isError = hasParseError(interaction);

  const formatAction = (action: string) => {
    return action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  return (
    <div
      className={`rounded-lg border-2 ${
        isError ? 'border-red-500 bg-red-50' : `border-transparent ${colors.bg}`
      } p-6 shadow-sm transition-all hover:shadow-md`}
    >
      {/* header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <span
              className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold bg-gradient-to-r ${colors.gradient} text-white`}
            >
              {interaction.agent.toUpperCase()}
            </span>
            {isError && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-red-100 text-red-700 text-xs font-medium">
                <AlertTriangle className="w-3 h-3" />
                Parsing Failed
              </span>
            )}
            <span className="text-xs text-gray-500">#{index + 1}</span>
          </div>
          <h3 className={`text-lg font-semibold ${colors.text}`}>
            {formatAction(interaction.action)}
          </h3>
          <p className="text-xs text-gray-500 mt-1">{formatTimestamp(interaction.timestamp)}</p>
        </div>
      </div>

      {/* metadata */}
      {interaction.metadata && Object.keys(interaction.metadata).length > 0 && (
        <div className="mb-4 text-xs text-gray-600 flex flex-wrap gap-x-4 gap-y-1">
          {interaction.metadata.level !== undefined && (
            <span>
              <strong>Level:</strong> {interaction.metadata.level}
            </span>
          )}
          {interaction.metadata.stage && (
            <span>
              <strong>Stage:</strong> {interaction.metadata.stage}
            </span>
          )}
          {interaction.metadata.request_type && (
            <span>
              <strong>Type:</strong> {interaction.metadata.request_type}
            </span>
          )}
          {interaction.metadata.oversight_level && (
            <span>
              <strong>Oversight:</strong> {interaction.metadata.oversight_level}
            </span>
          )}
          {interaction.metadata.copilot_model && (
            <span>
              <strong>Copilot:</strong> {interaction.metadata.copilot_model}
            </span>
          )}
          {interaction.metadata.copilot_active === false && (
            <span className="text-amber-600">
              <strong>Direct LLM</strong> (no copilot)
            </span>
          )}
          {interaction.metadata.cache_hit && (
            <span className="text-green-600">
              <strong>Cache Hit</strong>
            </span>
          )}
        </div>
      )}

      {/* prompts (collapsible, FULL - no truncation) */}
      {(interaction.system_prompt || interaction.user_prompt) && (
        <div className="mb-4">
          <button
            onClick={() => setShowPrompts(!showPrompts)}
            className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            {showPrompts ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            {showPrompts ? 'Hide' : 'Show'} Full Prompts
          </button>
          {showPrompts && (
            <div className="mt-2 space-y-3">
              {interaction.system_prompt && (
                <div>
                  <div className="font-medium text-gray-700 mb-1 text-sm">System Prompt:</div>
                  <pre className="bg-gray-100 p-3 rounded overflow-x-auto text-xs whitespace-pre-wrap max-h-96 overflow-y-auto border border-gray-300">
                    {interaction.system_prompt}
                  </pre>
                </div>
              )}
              {interaction.user_prompt && (
                <div>
                  <div className="font-medium text-gray-700 mb-1 text-sm">User Prompt:</div>
                  <pre className="bg-gray-100 p-3 rounded overflow-x-auto text-xs whitespace-pre-wrap max-h-96 overflow-y-auto border border-gray-300">
                    {interaction.user_prompt}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* main content - ALWAYS show both raw and parsed */}
      <div className="mt-4 space-y-4">
        {/* LLM Response (always visible) */}
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">LLM Response (Raw):</h4>
          <pre className="bg-white border border-gray-300 rounded p-4 overflow-x-auto text-sm font-mono whitespace-pre-wrap max-h-96 overflow-y-auto">
            {interaction.llm_response}
          </pre>
        </div>

        {/* Parsed Output (always visible) */}
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Parsed Output (Used by Simulation):</h4>
          {isError && interaction.parsed_output?.exception && (
            <div className="mb-2 p-2 bg-red-100 border border-red-300 rounded text-xs text-red-800">
              <strong>Parse Error:</strong> {interaction.parsed_output.exception}
            </div>
          )}
          <pre className="bg-white border border-gray-300 rounded p-4 overflow-x-auto text-sm font-mono max-h-96 overflow-y-auto">
            {JSON.stringify(interaction.parsed_output, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}