import { LLMInteraction } from '../types/audit';
import { InteractionCard } from './InteractionCard';
import { OversightGroup } from './OversightGroup';
import { formatPhase } from '../utils/dataLoader';

interface TimelineProps {
  interactions: LLMInteraction[];
}

export function Timeline({ interactions }: TimelineProps) {
  // group interactions by oversight workflow (copilot_draft -> oversight_edit -> final)
  const groupedInteractions: Array<{ type: 'single' | 'group'; items: LLMInteraction[]; startIndex: number }> = [];
  let i = 0;

  while (i < interactions.length) {
    const current = interactions[i];

    // check if this starts an oversight sequence
    if (
      current.action === 'copilot_draft' &&
      i + 2 < interactions.length &&
      interactions[i + 1].action === 'oversight_edit' &&
      interactions[i + 1].agent === current.agent
    ) {
      // find the final action (next action by same agent that's not oversight_edit)
      let groupEnd = i + 2;
      while (
        groupEnd < interactions.length &&
        interactions[groupEnd].agent === current.agent &&
        interactions[groupEnd].action === 'oversight_edit'
      ) {
        groupEnd++;
      }

      if (groupEnd < interactions.length && interactions[groupEnd].agent === current.agent) {
        groupedInteractions.push({
          type: 'group',
          items: interactions.slice(i, groupEnd + 1),
          startIndex: i,
        });
        i = groupEnd + 1;
        continue;
      }
    }

    // single interaction
    groupedInteractions.push({
      type: 'single',
      items: [current],
      startIndex: i,
    });
    i++;
  }

  // group by phase for section headers
  const phaseGroups: Map<string, typeof groupedInteractions> = new Map();
  groupedInteractions.forEach(group => {
    const phase = group.items[0].phase;
    if (!phaseGroups.has(phase)) {
      phaseGroups.set(phase, []);
    }
    phaseGroups.get(phase)!.push(group);
  });

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      {Array.from(phaseGroups.entries()).map(([phase, groups]) => (
        <div key={phase} className="mb-12">
          {/* phase header */}
          <div className="mb-6">
            <h2 className="text-2xl font-bold text-gray-900">{formatPhase(phase)}</h2>
            <div className="h-1 w-24 bg-gradient-to-r from-blue-500 to-cyan-400 rounded mt-2"></div>
          </div>

          {/* timeline */}
          <div className="relative pl-8">
            {/* vertical line */}
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-gray-300 to-gray-200"></div>

            {/* interactions */}
            <div className="space-y-6">
              {groups.map((group, idx) => (
                <div key={idx} className="relative">
                  {/* timeline dot */}
                  <div className="absolute -left-9 top-6 w-4 h-4 rounded-full bg-white border-4 border-blue-500"></div>

                  {group.type === 'group' ? (
                    <OversightGroup interactions={group.items} startIndex={group.startIndex} />
                  ) : (
                    <InteractionCard interaction={group.items[0]} index={group.startIndex} />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}