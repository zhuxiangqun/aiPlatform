import { SkillBoundToolsPicker } from './SkillBoundToolsPicker';
import { SkillBoundMcpsPicker } from './SkillBoundMcpsPicker';

export function SkillBoundCapabilitiesPicker({
  tools,
  onToolsChange,
  mcps,
  onMcpsChange,
  requiredHint,
  intentText,
  returnSkillId,
}: {
  tools: string[];
  onToolsChange: (next: string[]) => void;
  mcps: string[];
  onMcpsChange: (next: string[]) => void;
  requiredHint?: boolean;
  intentText?: string;
  returnSkillId?: string;
}) {
  const missing = requiredHint && tools.length === 0 && mcps.length === 0;
  return (
    <div className="space-y-3">
      <SkillBoundToolsPicker
        selected={tools}
        onChange={onToolsChange}
        requiredHint={missing}
        intentText={intentText}
        returnSkillId={returnSkillId}
      />
      <SkillBoundMcpsPicker
        selected={mcps}
        onChange={onMcpsChange}
        requiredHint={missing}
        intentText={intentText}
        returnSkillId={returnSkillId}
      />
    </div>
  );
}
