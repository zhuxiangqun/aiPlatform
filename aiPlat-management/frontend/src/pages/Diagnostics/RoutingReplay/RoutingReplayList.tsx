import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PageHeader from '../../../components/common/PageHeader';
import { Button, Card, CardContent, CardHeader, Input, Select, Table, toast } from '../../../components/ui';
import { skillApi, workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../components/ui';

const fmtTs = (ts?: number | null) => {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
};

const RoutingReplayList: React.FC = () => {
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();

  const [scope, setScope] = useState<'workspace' | 'engine'>((sp.get('scope') as any) || 'workspace');
  const [sinceHours, setSinceHours] = useState<number>(Number(sp.get('since_hours') || 24));
  const [limit, setLimit] = useState<number>(Number(sp.get('limit') || 100));
  const [skillId, setSkillId] = useState<string>(String(sp.get('skill_id') || ''));
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<any[]>([]);

  const api = scope === 'engine' ? skillApi : workspaceSkillApi;

  const query = useMemo(() => {
    const q: any = { since_hours: sinceHours, limit, selected_kind: 'skill' };
    if (skillId.trim()) q.skill_id = skillId.trim();
    return q;
  }, [sinceHours, limit, skillId]);

  const refresh = async () => {
    setLoading(true);
    try {
      const res: any = await (api as any).routingExplain(query);
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      toastGateError(e, '加载 routing_explain 失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // persist params
    const next = new URLSearchParams(sp);
    next.set('scope', scope);
    next.set('since_hours', String(sinceHours));
    next.set('limit', String(limit));
    if (skillId.trim()) next.set('skill_id', skillId.trim());
    else next.delete('skill_id');
    setSp(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, sinceHours, limit, skillId]);

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Routing Replay" description="逐条回放路由决策：候选、分差、门控原因、严格未命中（避免黑盒）。" />

      <Card>
        <CardHeader title="筛选" />
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
            <Select
              value={scope}
              onChange={(v: any) => setScope(v === 'engine' ? 'engine' : 'workspace')}
              options={[
                { label: 'workspace', value: 'workspace' },
                { label: 'engine', value: 'engine' },
              ]}
            />
            <Input value={String(sinceHours)} onChange={(e: any) => setSinceHours(Number(e.target.value || 24))} placeholder="since_hours" />
            <Input value={String(limit)} onChange={(e: any) => setLimit(Number(e.target.value || 100))} placeholder="limit" />
            <Input value={skillId} onChange={(e: any) => setSkillId(String(e.target.value || ''))} placeholder="skill_id（可选）" />
          </div>
          <div className="mt-2">
            <Button variant="secondary" onClick={refresh} loading={loading}>
              刷新
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title={`routing_explain（${scope}）`} />
        <CardContent>
          <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
            <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
              <div><span className="text-gray-300">time</span><span className="ml-2 text-gray-600">路由决策发生时间</span></div>
              <div><span className="text-gray-300">decision</span><span className="ml-2 text-gray-600">路由决策 ID</span></div>
              <div><span className="text-gray-300">top1</span><span className="ml-2 text-gray-600">排名第一的 Skill ID</span></div>
              <div><span className="text-gray-300">gap</span><span className="ml-2 text-gray-600">top1 与 top2 的得分差值</span></div>
              <div><span className="text-gray-300">gate</span><span className="ml-2 text-gray-600">门控提示（approval/gate/deny等）</span></div>
              <div><span className="text-gray-300">result</span><span className="ml-2 text-gray-600">路由结果状态</span></div>
              <div><span className="text-gray-300">query</span><span className="ml-2 text-gray-600">用户查询内容摘要</span></div>
              <div><span className="text-gray-300">op</span><span className="ml-2 text-gray-600">回放该路由决策</span></div>
            </div>
          </details>
          <Table
            rowKey={(r: any) => String(r.routing_decision_id || r.id || '')}
            loading={loading}
            data={items}
            columns={[
              { title: 'time', key: 'time', width: 190, render: (_: any, r: any) => fmtTs(r?.created_at) },
              { title: 'decision', dataIndex: 'routing_decision_id', key: 'routing_decision_id', width: 220 },
              { title: 'top1', dataIndex: 'top1_skill_id', key: 'top1_skill_id', width: 160 },
              { title: 'gap', key: 'gap', width: 80, render: (_: any, r: any) => (r?.score_gap == null ? '-' : Number(r.score_gap).toFixed(1)) },
              { title: 'gate', dataIndex: 'top1_gate_hint', key: 'top1_gate_hint', width: 140 },
              { title: 'result', dataIndex: 'result_status', key: 'result_status', width: 120 },
              { title: 'query', dataIndex: 'query_excerpt', key: 'query_excerpt' },
              {
                title: 'op',
                key: 'op',
                width: 100,
                render: (_: any, r: any) => (
                  <Button
                    variant="primary"
                    onClick={() => {
                      const did = String(r?.routing_decision_id || '');
                      if (!did) {
                        toast.error('缺少 routing_decision_id');
                        return;
                      }
                      navigate(`/diagnostics/routing-replay/${did}?scope=${scope}&since_hours=${sinceHours}`);
                    }}
                  >
                    回放
                  </Button>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
};

export default RoutingReplayList;
