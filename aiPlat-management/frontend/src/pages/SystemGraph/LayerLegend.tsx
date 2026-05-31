import React from 'react';

interface Props {
  tab: 'code' | 'capability' | 'wiki' | 'architecture';
  categories: { name: string; itemStyle: { color: string } }[];
}

const LABELS: Record<string, string> = {
  infra: 'infra', core: 'core', platform: 'platform', app: 'app',
  management: 'management',
  agent: 'Agent', skill: 'Skill', tool: 'Tool',
  mcp_server: 'MCP', workflow: 'Workflow', entry_point: '入口',
  entities: '实体', topics: '主题', contradictions: '矛盾',
};

const LayerLegend: React.FC<Props> = ({ categories }) => {
  return (
    <div className="absolute bottom-3 left-3 bg-dark-card/90 border border-dark-border rounded-lg px-2 py-1.5 flex flex-wrap gap-2">
      {categories.map((cat) => (
        <div key={cat.name} className="flex items-center gap-1 text-[10px] text-gray-400">
          <span className="w-2 h-2 rounded-full" style={{ background: cat.itemStyle.color }} />
          {LABELS[cat.name] || cat.name}
        </div>
      ))}
    </div>
  );
};

export default LayerLegend;
