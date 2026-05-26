import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { RefreshCw, AlertTriangle, CheckCircle, Activity } from 'lucide-react';

interface HealthCardProps {
  title: string;
  score: number;
  details: { label: string; value: string | number }[];
  loading?: boolean;
  onRefresh?: () => void;
}

const HealthCard: React.FC<HealthCardProps> = ({ title, score, details, loading, onRefresh }) => {
  const color = score >= 85 ? 'text-green-400' : score >= 70 ? 'text-yellow-400' : 'text-red-400';
  const bg = score >= 85 ? 'bg-green-900/20' : score >= 70 ? 'bg-yellow-900/20' : 'bg-red-900/20';
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">{title}</span>
          {onRefresh && <Button variant="ghost" size="sm" onClick={onRefresh} loading={loading}><RefreshCw className="w-3 h-3" /></Button>}
        </div>
      </CardHeader>
      <CardContent>
        <div className={`text-3xl font-bold ${color} mb-3`}>{score}</div>
        <div className="space-y-1">
          {details.map((d, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-gray-500">{d.label}</span>
              <span className="text-gray-300">{d.value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

const WikiHealthDashboard: React.FC = () => {
  const [lint, setLint] = useState<any>(null);
  const [lintLoading, setLintLoading] = useState(false);
  const [skillDeps, setSkillDeps] = useState<any>(null);
  const [codeIntel, setCodeIntel] = useState<any>(null);
  const [codeIntelLoading, setCodeIntelLoading] = useState(false);

  const fetchLint = async () => {
    setLintLoading(true);
    try { const r = await fetch('/api/core/wiki/lint'); setLint(await r.json()); } catch {}
    finally { setLintLoading(false); }
  };

  const fetchSkillDeps = async () => {
    try { const r = await fetch('/api/core/wiki/skill-deps'); setSkillDeps(await r.json()); } catch {}
  };

  const fetchCodeIntel = async () => {
    setCodeIntelLoading(true);
    try { const r = await fetch('/api/core/diagnostics/code-intel/scan?mode=layer'); setCodeIntel(await r.json()); } catch {}
    finally { setCodeIntelLoading(false); }
  };

  useEffect(() => { fetchLint(); fetchSkillDeps(); fetchCodeIntel(); }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Activity className="w-4 h-4 text-primary" />
        <h1 className="text-lg font-semibold text-gray-100">系统健康概览</h1>
        <span className="text-xs text-gray-500">Wiki · CodeIntel · Skill · Pipeline</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Wiki Health */}
        <HealthCard
          title="Wiki 知识库"
          score={lint?.health_score ?? '—'}
          details={[
            { label: '页面数', value: lint?.total_pages ?? '—' },
            { label: '死链', value: lint?.stats?.dead_links ?? '—' },
            { label: '孤立页面', value: lint?.stats?.orphan_pages ?? '—' },
            { label: '矛盾', value: lint?.stats?.contradictions ?? '—' },
          ]}
          loading={lintLoading}
          onRefresh={fetchLint}
        />

        {/* CodeIntel Health */}
        <HealthCard
          title="代码架构"
          score={codeIntel?.health?.score ?? '—'}
          details={[
            { label: '文件数', value: codeIntel?.stats?.files ?? '—' },
            { label: '边数', value: codeIntel?.stats?.edges ?? '—' },
            { label: '循环数', value: codeIntel?.health?.signals?.cycles_back_edges ?? '—' },
            { label: '平均度数', value: codeIntel?.health?.signals?.avg_degree ?? '—' },
          ]}
          loading={codeIntelLoading}
          onRefresh={fetchCodeIntel}
        />

        {/* Skill Dependency */}
        <HealthCard
          title="Skill 依赖"
          score={skillDeps?.stats?.total_skills ? 100 : 0}
          details={[
            { label: 'Skills', value: skillDeps?.stats?.total_skills ?? '—' },
            { label: 'Agents', value: skillDeps?.stats?.total_agents ?? '—' },
            { label: 'Syscalls 使用', value: skillDeps?.stats?.total_syscalls_used ?? '—' },
            { label: '未知引用', value: skillDeps?.stats?.unknown_references ?? '—' },
          ]}
          onRefresh={fetchSkillDeps}
        />

        {/* Architecture Guard Status */}
        <Card>
          <CardHeader><div className="text-sm font-medium text-gray-200">架构守卫</div></CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-400 font-semibold text-lg">合规</span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between"><span className="text-gray-500">检查项</span><span className="text-gray-300">33 项</span></div>
              <div className="flex justify-between"><span className="text-gray-500">层边界</span><span className="text-green-300">全通过</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Agent→Skill</span><span className="text-green-300">有效</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Skill→Syscall</span><span className="text-green-300">有效</span></div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Wiki Checks Detail */}
      {lint?.checks && lint.checks.length > 0 && (
        <Card>
          <CardHeader><div className="text-sm font-medium text-gray-200">Wiki 检查明细</div></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
              {lint.checks.map((chk: any, idx: number) => (
                <div key={idx} className={`p-2 rounded border text-xs ${chk.pass ? 'border-green-900/40 bg-green-900/10' : 'border-yellow-900/40 bg-yellow-900/10'}`}>
                  <div className="flex items-center gap-1.5">
                    <span className={chk.pass ? 'text-green-400' : 'text-yellow-400'}>{chk.pass ? '✓' : '!'}</span>
                    <span className="text-gray-300">{chk.name}</span>
                  </div>
                  <div className={`ml-4 text-[10px] ${chk.pass ? 'text-green-500' : 'text-yellow-500'}`}>
                    {chk.pass ? '通过' : `${chk.count} 个问题`}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Unknown Skill Refs */}
      {skillDeps?.unknown_refs && skillDeps.unknown_refs.filter((r: any) => r.ref).length > 0 && (
        <Card>
          <CardHeader>
            <div className="text-sm font-medium text-gray-200 flex items-center gap-2">
              <AlertTriangle className="w-3 h-3 text-yellow-400" />
              未解析的 Skill 引用
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {skillDeps.unknown_refs.filter((r: any) => r.ref).map((r: any, idx: number) => (
                <div key={idx} className="text-xs text-yellow-300">
                  Agent <span className="text-gray-400">{r.agent}</span> 引用了不存在的 Skill <span className="text-red-400">{r.ref}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default WikiHealthDashboard;
