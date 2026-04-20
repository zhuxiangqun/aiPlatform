import { Link } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import { Activity, GitBranch, Share2, Zap, Wrench, FolderSearch } from 'lucide-react';

import { Card, CardContent, CardHeader, Badge } from '../../components/ui';
import { diagnosticsApi } from '../../services';

type Health = {
  layer: string;
  status: 'healthy' | 'degraded' | 'unhealthy' | string;
  timestamp?: string;
};

const toBadgeVariant = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  if (status === 'healthy' || status === 'success') return 'success';
  if (status === 'degraded' || status === 'warn' || status === 'warning') return 'warning';
  if (status === 'unhealthy' || status === 'error' || status === 'failed') return 'error';
  if (status === 'running') return 'info';
  return 'default';
};

const Diagnostics: React.FC = () => {
  const [health, setHealth] = useState<Record<string, Health | null>>({
    infra: null,
    core: null,
    platform: null,
    app: null,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setError(null);
      try {
        const layers: Array<keyof typeof health> = ['infra', 'core', 'platform', 'app'];
        const results = await Promise.allSettled(layers.map((l) => diagnosticsApi.getHealth(l)));
        const next: Record<string, Health | null> = {};
        results.forEach((r, idx) => {
          const layer = layers[idx];
          if (r.status === 'fulfilled') next[layer] = r.value as any;
          else next[layer] = { layer, status: 'error' };
        });
        if (mounted) setHealth(next);
      } catch (e: any) {
        if (mounted) setError(e?.message || '加载失败');
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const items = useMemo(
    () => [
      { title: 'Doctor', desc: '一键聚合诊断报告', href: '/diagnostics/doctor', icon: Activity },
      { title: 'Context', desc: 'Prompt/context 组装诊断（cache/search/注入）', href: '/diagnostics/context', icon: Activity },
      { title: 'Capability→Policy', desc: '从 skill capabilities 生成工具门禁策略', href: '/diagnostics/capability-policy', icon: Activity },
      { title: 'Traces', desc: '链路追踪与 spans 定位', href: '/diagnostics/traces', icon: Activity },
      { title: 'Graph Runs', desc: '执行 runs / checkpoints / 恢复', href: '/diagnostics/graphs', icon: GitBranch },
      { title: 'Links', desc: '输入任意 ID 联动查询', href: '/diagnostics/links', icon: Share2 },
      { title: 'Repo', desc: 'Repo 索引/全文搜索（gitignore-aware）', href: '/diagnostics/repo', icon: FolderSearch },
      { title: 'Runs', desc: 'run_id 维度的摘要与事件流', href: '/diagnostics/runs', icon: Share2 },
      { title: 'Audit Logs', desc: '关键操作审计日志', href: '/diagnostics/audit', icon: Share2 },
      { title: 'Tenant Policies', desc: 'Policy-as-code 策略快照', href: '/diagnostics/policies', icon: Share2 },
      { title: 'Policy Debug', desc: '策略评估调试（RBAC + Policy）', href: '/diagnostics/policy-debug', icon: Activity },
      { title: 'Syscalls', desc: 'syscall_events 检索（tool/llm/skill）', href: '/diagnostics/syscalls', icon: Zap },
      { title: 'Change Control', desc: '变更控制台（change_id / gates / approvals）', href: '/diagnostics/change-control', icon: GitBranch },
      { title: 'E2E Smoke', desc: '生产级全链路冒烟（自动清理）', href: '/diagnostics/smoke', icon: Zap },
      { title: 'Ops', desc: '导出（CSV）/ DLQ / 配额用量', href: '/diagnostics/ops', icon: Wrench },
    ],
    []
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">可观测性</h1>
        <p className="text-sm text-gray-500 mt-1">Trace / Graph Runs / Links 联动定位问题</p>
      </div>

      {error && (
        <div className="text-sm text-error bg-error-light border border-dark-border rounded-lg p-3">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {(['infra', 'core', 'platform', 'app'] as const).map((layer) => {
          const h = health[layer];
          return (
            <Card key={layer}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-200 uppercase">{layer}</div>
                  <Badge variant={toBadgeVariant(h?.status || 'default')}>{h?.status || '...'}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-gray-500">
                  {h?.timestamp ? `更新时间：${h.timestamp}` : '—'}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {items.map((it) => (
          <Link key={it.href} to={it.href} className="block">
            <Card hoverable>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <it.icon className="w-4 h-4 text-primary" />
                  <div className="text-sm font-semibold text-gray-200">{it.title}</div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-gray-500">{it.desc}</div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default Diagnostics;
