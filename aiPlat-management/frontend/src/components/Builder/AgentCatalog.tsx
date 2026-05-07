import React, { useEffect, useState } from 'react';
import { Plus, Wrench, Palette, Shield, Briefcase, BarChart3, Headphones, ShoppingCart, Search, ChevronDown, ChevronRight } from 'lucide-react';
import { builderTeamApi, type AgentCatalogItem } from '../../services';
import { Card, CardHeader, CardContent, toast, Button } from '../../components/ui';

const CATEGORY_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  product:    { icon: <Palette className="w-3.5 h-3.5" />, label: '产品'  , color: 'text-purple-400 bg-purple-400/10' },
  engineering:{ icon: <Wrench className="w-3.5 h-3.5" />,   label: '研发'  , color: 'text-blue-400 bg-blue-400/10' },
  quality:    { icon: <Shield className="w-3.5 h-3.5" />,   label: '质量'  , color: 'text-green-400 bg-green-400/10' },
  management: { icon: <Briefcase className="w-3.5 h-3.5" />, label: '管理'  , color: 'text-amber-400 bg-amber-400/10' },
  design:     { icon: <Palette className="w-3.5 h-3.5" />,   label: '设计'  , color: 'text-pink-400 bg-pink-400/10' },
  sales:      { icon: <ShoppingCart className="w-3.5 h-3.5" />, label: '销售', color: 'text-orange-400 bg-orange-400/10' },
  support:    { icon: <Headphones className="w-3.5 h-3.5" />, label: '支持'  , color: 'text-cyan-400 bg-cyan-400/10' },
  other:      { icon: <BarChart3 className="w-3.5 h-3.5" />, label: '其他'  , color: 'text-gray-400 bg-gray-400/10' },
};

interface Props {
  onAdd: (agent: AgentCatalogItem) => void;
}

const AgentItem: React.FC<{ agent: AgentCatalogItem; onAdd: (a: AgentCatalogItem) => void }> = ({ agent, onAdd }) => {
  const displayName = agent.display_name || (agent as Record<string, unknown>).name as string || agent.agent_id;
  const desc = (agent.description || '') as string;
  const tags = agent.tags || [];

  return (
    <div className="group relative">
      <div className="flex items-center justify-between py-2 px-3 hover:bg-dark-hover/40 rounded transition-colors cursor-default">
        <div className="flex-1 min-w-0 mr-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] font-medium text-gray-200 truncate">{displayName}</span>
            <span className="text-[9px] px-1 py-0 rounded bg-dark-border text-gray-500 font-mono flex-shrink-0">
              {agent.agent_type || '-'}
            </span>
          </div>
          {desc && (
            <div className="text-[11px] text-gray-500 truncate mt-0.5">{desc}</div>
          )}
        </div>
        <Button size="sm" variant="ghost" className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity ml-1" onClick={() => onAdd(agent)}>
          <Plus className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* Hover popover — shows full description & tags */}
      <div className="absolute left-0 right-0 top-full z-50 mt-1 hidden group-hover:block">
        <div className="bg-dark-card border border-dark-border rounded-lg shadow-xl p-3 mx-2">
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-sm font-semibold text-gray-100">{displayName}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-mono">
              {agent.agent_type || 'agent'}
            </span>
            <span className="text-[10px] text-gray-500">· {agent.category || 'other'}</span>
          </div>
          <div className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
            {desc || '暂无描述'}
          </div>
          {tags.length > 0 && (
            <div className="flex gap-1 mt-2 flex-wrap">
              {tags.map((t: string) => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full bg-dark-hover text-gray-400 border border-dark-border">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const AgentCatalog: React.FC<Props> = ({ onAdd }) => {
  const [agents, setAgents] = useState<AgentCatalogItem[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      try {
        const resp = await builderTeamApi.listAgents();
        const list = resp.agents || [];
        setAgents(list);
        // Default: expand all categories so the pool isn't blank on first load
        const allCats: Record<string, boolean> = {};
        for (const a of list) {
          allCats[a.category || 'other'] = true;
        }
        setExpanded(allCats);
      } catch {
        toast.error('加载角色列表失败');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const grouped: Record<string, AgentCatalogItem[]> = {};
  for (const a of agents) {
    const cat = a.category || 'other';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(a);
  }

  const catOrder = Object.entries(grouped).sort((a, b) => b[1].length - a[1].length);

  const toggleCat = (cat: string) => {
    setExpanded((prev) => {
      const next = { ...prev };
      if (next[cat]) {
        delete next[cat];
      } else {
        for (const k of Object.keys(next)) delete next[k];
        next[cat] = true;
      }
      return next;
    });
  };

  const filtered = search.trim()
    ? agents.filter((a) => {
        const name = (a.display_name || (a as Record<string, unknown>).name || a.agent_id) as string;
        return name.includes(search) ||
          (a.tags || []).some((t: string) => t.includes(search)) ||
          ((a.description || '') as string).includes(search);
      })
    : null;

  return (
    <Card className="sticky top-4">
      <CardHeader title="角色池" extra={<span className="text-xs text-gray-500">{agents.length}</span>} />
      <CardContent className="p-0">
        {/* Search */}
        <div className="px-3 py-2">
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2.5 top-2 text-gray-500" />
            <input
              className="w-full pl-7 pr-3 py-1.5 text-[11px] bg-dark-hover border border-dark-border rounded-lg text-gray-200 placeholder-gray-600 focus:outline-none focus:border-primary/50"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索角色名、标签..."
            />
          </div>
        </div>

        {/* Category quick filter pills */}
        {!search.trim() && (
          <div className="flex gap-1 px-3 pb-2 overflow-x-auto">
            {catOrder.map(([cat, items]) => {
              const meta = CATEGORY_META[cat] || CATEGORY_META.other;
                const isOpen = expanded[cat] === true;
              return (
                <button
                  key={cat}
                  onClick={() => toggleCat(cat)}
                  className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border transition-colors flex-shrink-0 ${
                    isOpen ? `${meta.color.split(' ')[1]} ${meta.color.split(' ')[0]} border-current` : 'text-gray-500 border-dark-border'
                  }`}
                >
                  {items.length} {meta.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Agent list */}
        <div className="max-h-[calc(100vh-300px)] overflow-y-auto">
          {loading ? (
            <div className="p-4 text-xs text-gray-500">加载中...</div>
          ) : filtered ? (
            <div className="py-1">
              <div className="text-[10px] text-gray-500 px-3 py-1">{filtered.length} 个结果</div>
              {filtered.map((a) => (
                <AgentItem key={a.agent_id} agent={a} onAdd={onAdd} />
              ))}
            </div>
          ) : (
            catOrder
              .filter(([cat]) => expanded[cat] === true)
              .map(([cat, items]) => {
                const meta = CATEGORY_META[cat] || CATEGORY_META.other;
                return (
                  <div key={cat}>
                    <button
                      onClick={() => toggleCat(cat)}
                      className="flex items-center gap-1.5 w-full px-3 py-1.5 hover:bg-dark-hover/30 sticky top-0 bg-dark-card z-10 transition-colors"
                    >
                      <span className="text-gray-500"><ChevronDown className="w-3 h-3" /></span>
                      <span className={meta.color.split(' ')[0]}>{meta.icon}</span>
                      <span className="text-[12px] font-semibold text-gray-300">{meta.label}</span>
                      <span className="text-[10px] text-gray-600 ml-auto">{items.length}</span>
                    </button>
                    {items.map((a) => (
                      <AgentItem key={a.agent_id} agent={a} onAdd={onAdd} />
                    ))}
                  </div>
                );
              })
          )}
        </div>
      </CardContent>
    </Card>
  );
};
