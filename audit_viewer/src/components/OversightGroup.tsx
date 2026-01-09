import { LLMInteraction } from '../types/audit';
import { InteractionCard } from './InteractionCard';
import { ArrowDown } from 'lucide-react';

interface OversightGroupProps {
  interactions: LLMInteraction[];
  startIndex: number;
}

export function OversightGroup({ interactions, startIndex }: OversightGroupProps) {
  return (
    <div className="relative">
      {/* visual grouping container */}
      <div className="space-y-3">
        {interactions.map((interaction, idx) => (
          <div key={interaction.interaction_id}>
            <InteractionCard interaction={interaction} index={startIndex + idx} />
            {idx < interactions.length - 1 && (
              <div className="flex justify-center my-2">
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <div className="h-6 w-px bg-gray-300"></div>
                  <ArrowDown className="w-4 h-4" />
                  <div className="h-6 w-px bg-gray-300"></div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* group label */}
      <div className="absolute -left-24 top-8 text-xs text-gray-500 font-medium transform -rotate-90 origin-center whitespace-nowrap">
        Draft → Oversight → Final
      </div>
    </div>
  );
}