import { useEffect, useState } from 'react';
import { BarChart3, ChevronDown, ChevronRight, AlertTriangle, CheckCircle, X, Circle, Zap, BookOpen, Database } from 'lucide-react';

type Maturity = 'seeding' | 'building' | 'stable' | 'production-ready';

interface DomainMetrics {
  wiki_entities: number;
  wiki_relations: number;
  skills_available: number;
  skills_enabled: number;
  golden_queries: number;
  golden_query_pass_rate: number;
  adopted_count: number;
  last_ingest_at: string | null;
  domain_prompt_ready: boolean;
  seed_data_ready: boolean;
  graph_traversal_depth: number;
  cross_domain_links: number;
}

interface DomainSkill {
  name: string;
  execution_type: string;
  triggers: string[];
  pass_rate: number;
  total_executions: number;
  last_executed_at: string | null;
}

interface KnownGap {
  severity: 'critical' | 'high' | 'medium' | 'low';
  gap: string;
  mitigation: string;
}

interface DomainData {
  name: string;
  maturity: Maturity;
  metrics: DomainMetrics;
  skills: DomainSkill[];
  known_gaps: KnownGap[];
  recommend_next: string[];
}

interface CapabilityBoundaryData {
  version: string;
  generated_at: string;
  overall_maturity: string;
  summary: {
    total_domains: number;
    seeding_domains: number;
    building_domains: number;
    stable_domains: number;
    production_ready_domains: number;
    domains_with_no_data: number;
    total_unwired_skills: number;
    total_domain_skills: number;
  };
  domains: Record<string, DomainData>;
}

const MATURITY_CONFIG: Record<Maturity, { label: string; color: string; bg: string; order: number }> = {
  'production-ready': { label: '生产就绪', color: 'text-green-400', bg: 'bg-green-500/20', order: 0 },
  stable: { label: '稳定', color: 'text-blue-400', bg: 'bg-blue-500/20', order: 1 },
  building: { label: '构建中', color: 'text-yellow-400', bg: 'bg-yellow-500/20', order: 2 },
  seeding: { label: '播种中', color: 'text-gray-400', bg: 'bg-gray-500/20', order: 3 },
};

const SEVERITY_CONFIG: Record<string, { icon: any; color: string }> = {
  critical: { icon: X, color: 'text-red-400 bg-red-500/10' },
  high: { icon: AlertTriangle, color: 'text-orange-400 bg-orange-500/10' },
  medium: { icon: Circle, color: 'text-yellow-400 bg-yellow-500/10' },
  low: { icon: Circle, color: 'text-blue-400 bg-blue-500/10' },
};

const INDUSTRY_RECOMMENDED: Record<string, string[]> = {
  'manufacturing': ['supply-chain', 'ship-design', 'it-ops'],
  'finance': ['finance', 'procurement-mvo'],
  'retail': ['supply-chain', 'procurement-mvo'],
  'general': ['ai-knowledge', 'default'],
};

interface CapabilityBoundaryProps {
  readonly industry?: string | null;
  readonly onSelect?: ((domain: { id: string; maturity: string; skillsAvailable: number }) => void) | null;
}

const CapabilityBoundary: React.FC<CapabilityBoundaryProps> = ({ industry, onSelect }) => {
  const [data, setData] = useState<CapabilityBoundaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch('/api/core/diagnostics/capability-boundary')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const toggleExpand = (id: string) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (error || !data || !data.domains) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400">
        <AlertTriangle className="w-5 h-5 mr-2" />
        {error || '无法加载能力边界数据（API 未就绪）'}
      </div>
    );
  }

  const sortedDomains = Object.entries(data.domains || {}).sort(
    ([, a], [, b]) => (MATURITY_CONFIG[a.maturity]?.order ?? 99) - (MATURITY_CONFIG[b.maturity]?.order ?? 99)
  );

  const allSeeding = sortedDomains.length > 0 && sortedDomains.every(
    ([, d]) => d.maturity === 'seeding'
  );

  if (allSeeding) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center space-y-4">
        <Database className="w-10 h-10 text-gray-600" />
        <div className="text-sm text-gray-400 max-w-md">
          系统中还没有业务域数据。首次进场时所有域都处于播种阶段——这是正常状态。
        </div>
        <div className="text-xs text-gray-500 max-w-md">
          下一步：选择与客户行业最接近的域，运行
          <code className="text-blue-400 mx-1 bg-gray-800 px-1 rounded">python scripts/seed_wiki.py --domain 域ID</code>
          和
          <code className="text-blue-400 mx-1 bg-gray-800 px-1 rounded">python scripts/ingest_seed.py --domain 域ID</code>
          注入种子数据。创建域 Skill 后，这里会显示"构建中"状态。
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary bar */}
      <div className="grid grid-cols-4 gap-3">
        {(['production-ready', 'stable', 'building', 'seeding'] as Maturity[]).map(m => (
          <div key={m} className={`rounded-lg p-3 ${MATURITY_CONFIG[m].bg} border border-white/10`}>
            <div className={`text-lg font-bold ${MATURITY_CONFIG[m].color}`}>
              {data.summary[`${m.replace('-', '_')}_domains` as keyof typeof data.summary] || 0}
            </div>
            <div className="text-xs text-gray-400 mt-1">{MATURITY_CONFIG[m].label}</div>
          </div>
        ))}
      </div>

      {/* Domain cards */}
      <div className="space-y-3">
         {sortedDomains.map(([id, domain]) => {
           const mc = MATURITY_CONFIG[domain.maturity];
           const isExpanded = expanded[id] ?? false;
           const isRecommended = !!industry && INDUSTRY_RECOMMENDED[industry.toLowerCase()]?.includes(id);

           return (
             <div key={id} className={`rounded-lg bg-gray-800/50 border overflow-hidden ${isRecommended ? 'border-green-500/50' : 'border-gray-700/50'}`}>
               {/* Header — clickable */}
               <div
                 className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-800/70"
                 onClick={() => { toggleExpand(id); onSelect?.({ id, maturity: domain.maturity, skillsAvailable: domain.metrics.skills_available }); }}
               >
                 <div className="flex items-center gap-3">
                   {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
                   <span className="font-medium text-gray-200">{domain.name}</span>
                   {isRecommended && <span className="text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full">推荐</span>}
                   <span className={`text-xs px-2 py-0.5 rounded-full ${mc.bg} ${mc.color}`}>
                    {mc.label}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-400">
                  <span className="flex items-center gap-1"><Database className="w-3 h-3" />{domain.metrics.wiki_entities}</span>
                  <span className="flex items-center gap-1"><Zap className="w-3 h-3" />{domain.metrics.skills_available}/{domain.metrics.skills_available}</span>
                  <span className="flex items-center gap-1"><BookOpen className="w-3 h-3" />{domain.metrics.golden_queries}</span>
                </div>
              </div>

              {/* Expanded panel */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-4 border-t border-gray-700/50 pt-3">
                  {/* Metrics grid */}
                  <div className="grid grid-cols-4 gap-2">
                    <MetricBox label="wiki实体" value={domain.metrics.wiki_entities} />
                    <MetricBox label="图谱关系" value={domain.metrics.wiki_relations} />
                    <MetricBox label="可用SKILL" value={`${domain.metrics.skills_available}`} />
                    <MetricBox label="通过率" value={`${(domain.metrics.golden_query_pass_rate * 100).toFixed(0)}%`} />
                    <MetricBox label="Gold Qs" value={domain.metrics.golden_queries} />
                    <MetricBox label="采纳数" value={domain.metrics.adopted_count} />
                    <MetricBox label="遍历深度" value={domain.metrics.graph_traversal_depth} />
                    <MetricBox label="跨域链接" value={domain.metrics.cross_domain_links} />
                  </div>

                  {/* Skills */}
                  {domain.skills.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-400 mb-2">领域SKILL</div>
                      {domain.skills.map(s => (
                        <div key={s.name} className="flex items-center justify-between py-1.5 px-2 rounded bg-gray-700/30 text-xs">
                          <span className="text-gray-300">{s.name}</span>
                          <span className="text-gray-500">{s.execution_type} | {s.triggers.slice(0, 2).join(', ')}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Known gaps */}
                  {domain.known_gaps.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-400 mb-2">已知缺口</div>
                      <div className="space-y-1.5">
                        {domain.known_gaps.map((g, i) => {
                          const sc = SEVERITY_CONFIG[g.severity] || SEVERITY_CONFIG.low;
                          const Icon = sc.icon;
                          return (
                            <div key={i} className={`flex items-start gap-2 p-2 rounded text-xs ${sc.color}`}>
                              <Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                              <div>
                                <div>{g.gap}</div>
                                <div className="text-gray-500 mt-0.5">{g.mitigation}</div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Recommendations */}
                  {domain.recommend_next.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-400 mb-2">建议下一步</div>
                      <ul className="space-y-1">
                        {domain.recommend_next.map((rec, i) => (
                          <li key={i} className="text-xs text-blue-300 flex items-start gap-1">
                            <span className="text-blue-500 mt-0.5">→</span>
                            {rec}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const MetricBox: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="bg-gray-700/30 rounded p-2 text-center">
    <div className="text-lg font-bold text-gray-200">{value}</div>
    <div className="text-[10px] text-gray-500">{label}</div>
  </div>
);

export default CapabilityBoundary;
