import { useState } from 'react';
import { GroupedTurn } from '../types/audit';
import { TurnCard } from './TurnCard';
import { formatPhase, getPhaseColor } from '../utils/dataLoader';

interface TimelineProps {
  readonly turns: GroupedTurn[];
}

export function Timeline({ turns }: TimelineProps) {
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(new Set());
  const phaseGroups = new Map<string, GroupedTurn[]>();
  for (const turn of turns) {
    if (!phaseGroups.has(turn.phase)) phaseGroups.set(turn.phase, []);
    phaseGroups.get(turn.phase)!.push(turn);
  }
  const toggleTurn = (key: string) => {
    const next = new Set(expandedTurns);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setExpandedTurns(next);
  };
  const expandAll = () => {
    const all = new Set(turns.map(t => `${t.phase}_${t.turn}`));
    setExpandedTurns(all);
  };
  const collapseAll = () => setExpandedTurns(new Set());

  return (
    <div className="space-y-8">
      <div className="flex gap-2">
        <button onClick={expandAll} className="px-3 py-1 text-sm bg-slate-200 rounded hover:bg-slate-300">
          Expand All
        </button>
        <button onClick={collapseAll} className="px-3 py-1 text-sm bg-slate-200 rounded hover:bg-slate-300">
          Collapse All
        </button>
      </div>
      {Array.from(phaseGroups.entries()).map(([phase, phaseTurns]) => {
        const colors = getPhaseColor(phase);
        return (
          <div key={phase} className="space-y-4">
            <div className={`px-4 py-2 rounded-lg ${colors.bg} border ${colors.border}`}>
              <h2 className={`text-xl font-bold ${colors.text}`}>{formatPhase(phase)}</h2>
              <p className="text-sm text-slate-600">{phaseTurns.length} turns</p>
            </div>
            <div className="space-y-3 pl-4 border-l-4 border-slate-200">
              {phaseTurns.map((turn) => {
                const key = `${turn.phase}_${turn.turn}`;
                return (
                  <TurnCard
                    key={key}
                    turn={turn}
                    expanded={expandedTurns.has(key)}
                    onToggle={() => toggleTurn(key)}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
