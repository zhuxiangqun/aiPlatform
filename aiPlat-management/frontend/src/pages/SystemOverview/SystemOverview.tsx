import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { RefreshCw, Server, Cpu, Bot, Sparkles, Shield, Database, Activity } from 'lucide-react';

interface HealthCardData {
  title: string;
  icon: React.ReactNode;
  score: number;
  scoreLabel: string;
  items: { label: string; value: string | number; ok?: boolean }[];
  loading?: boolean;
  to?: string;
}

const HealthCard: React.FC<HealthCardData> = ({ title, icon, score, scoreLabel, items, to }) => {
  const navigate = useNavigate();
  const color = score >= 85 ? 'text-green-400' : score >= 70 ? 'text-yellow-400' : 'text-red-400';
  return (
    <Card className={`hover:border-gray-600 transition-colors ${to ? 'cursor-pointer hover:border-primary/50' : ''}`}
      onClick={() => to && navigate(to)}>
      <CardHeader>
        <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
          {icon}
          {title}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-2 mb-3">
          <span className={`text-2xl font-bold ${color}`}>{score}</span>
          <span className="text-xs text-gray-500 mb-1">{scoreLabel}</span>
        </div>
        <div className="border-t border-dark-border pt-2 space-y-1">
          {items.map((it, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-gray-500">{it.label}</span>
              <span className={it.ok === false ? 'text-red-400' : 'text-gray-300'}>{it.value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

const SystemOverview: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/core/overview');
      setData(await r.json());
    } catch { }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); const t = setInterval(fetchData, 30000); return () => clearInterval(t); }, []);

  const ch = data?.code_health || {};
  const wh = data?.wiki_health || {};
  const sd = data?.skill_deps || {};
  const ag = data?.arch_guard || {};
  const models = data?.models || {};
  const agents = data?.agents || {};
  const servers = data?.servers || {};
  const pipeline = data?.pipeline || {};

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-semibold text-gray-100">系统概览</h1>
        </div>
        <Button variant="ghost" size="sm" onClick={fetchData} loading={loading}>
          <RefreshCw className="w-3 h-3 mr-1" />刷新
        </Button>
      </div>

      {/* Row 1: 3 knowledge graphs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <HealthCard
          title="代码图谱" icon={<Cpu className="w-4 h-4 text-blue-400" />}
          score={ch.score ?? 0} scoreLabel="分 · 架构健康"
          to="/diagnostics/code-intel"
          items={[
            { label: '文件数', value: ch.files ?? '—' },
            { label: '导入边', value: ch.edges ?? '—' },
            { label: '循环依赖', value: ch.cycles ?? '—', ok: (ch.cycles ?? 0) === 0 },
            { label: '孤立文件', value: ch.orphan_files ?? '—', ok: (ch.orphan_files ?? 0) === 0 },
          ]}
        />
        <HealthCard
          title="知识图谱" icon={<Database className="w-4 h-4 text-purple-400" />}
          score={wh.score ?? 0} scoreLabel="分 · Wiki 健康"
          to="/platform/kb"
          items={[
            { label: '页面数', value: wh.pages ?? '—' },
            { label: '死链', value: wh.dead_links ?? '—', ok: (wh.dead_links ?? 0) === 0 },
            { label: '孤立页面', value: wh.orphans ?? '—', ok: (wh.orphans ?? 0) === 0 },
            { label: '矛盾标记', value: wh.contradictions ?? '—' },
          ]}
        />
        <HealthCard
          title="技能图谱" icon={<Sparkles className="w-4 h-4 text-amber-400" />}
          score={sd.unknown_refs === 0 ? 100 : 75} scoreLabel="分 · 依赖完整"
          items={[
            { label: 'Skills', value: sd.skills ?? '—' },
            { label: 'Agents', value: sd.agents ?? '—' },
            { label: '未使用 Skill', value: sd.unused_skills ?? '—', ok: (sd.unused_skills ?? 0) === 0 },
            { label: '未解析引用', value: sd.unknown_refs ?? '—', ok: (sd.unknown_refs ?? 0) === 0 },
          ]}
        />
      </div>

      {/* Row 2: Arch guard + servers */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
              <Shield className="w-4 h-4 text-green-400" />
              架构守卫
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-green-400 text-lg font-bold">{ag.compliant ? '合规 ✓' : '违规 ✗'}</span>
            </div>
            <div className="text-xs text-gray-500">{ag.checks} 项检查 · {ag.violations} 项违规</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
              <Server className="w-4 h-4 text-cyan-400" />
              服务器状态
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(servers).map(([name, status]) => (
                <div key={name} className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${status === 'up' ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-gray-400">{name}</span>
                  <span className={status === 'up' ? 'text-green-400' : 'text-red-400'}>{status}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Row 3: Models + Agents + Pipeline */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
              <Cpu className="w-4 h-4 text-violet-400" />
              模型状态
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-xs space-y-1">
              <div className="text-gray-500">{models.available}/{models.total} 可用</div>
              {(models.list || []).slice(0, 5).map((m: any) => (
                <div key={m.name} className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${m.status === 'available' ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-gray-400 truncate">{m.name}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
              <Bot className="w-4 h-4 text-emerald-400" />
              Agent 注册
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-xs space-y-1">
              <div className="text-gray-500">{agents.ready}/{agents.total} 就绪</div>
              {(agents.list || []).slice(0, 6).map((a: any) => (
                <div key={a.id} className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  <span className="text-gray-400 truncate">{a.id}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
              <Activity className="w-4 h-4 text-orange-400" />
              Pipeline 引擎
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div><div className="text-lg font-semibold text-blue-400">{pipeline.active}</div><div className="text-gray-500">活跃</div></div>
              <div><div className="text-lg font-semibold text-green-400">{pipeline.completed}</div><div className="text-gray-500">完成</div></div>
              <div><div className="text-lg font-semibold text-red-400">{pipeline.failed}</div><div className="text-gray-500">失败</div></div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SystemOverview;
