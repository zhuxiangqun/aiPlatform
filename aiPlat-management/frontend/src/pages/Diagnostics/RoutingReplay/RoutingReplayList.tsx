import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PageHeader from '../../../components/common/PageHeader';
import { Button, Card, CardContent, CardHeader, Input, Select, Table, toast } from '../../../components/ui';
import { skillApi, workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

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
          <Table
            rowKey={(r: any) => String(r?.routing_decision_id || r?.created_at || Math.random())}
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

