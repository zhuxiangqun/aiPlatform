import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Save, Trash2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Select, Table, toast } from '../../../../components/ui';
import { learningApi } from '../../../../services';
import { toastGateError } from '../../../../utils/governanceError';

type RolloutRecord = {
  tenant_id?: string | null;
  target_type: string;
  target_id: string;
  candidate_id: string;
  mode?: string;
  percentage?: number | null;
  include_actor_ids?: string[] | null;
  exclude_actor_ids?: string[] | null;
  enabled?: number | boolean;
  updated_at?: number;
  metadata?: Record<string, unknown>;
};

type MetricSnapshot = {
  id?: string;
  tenant_id?: string | null;
  candidate_id: string;
  metric_key: string;
  value: number;
  window_start?: number | null;
  window_end?: number | null;
  created_at?: number;
  metadata?: Record<string, unknown>;
};

const modeOptions = [
  { label: 'percentage', value: 'percentage' },
  { label: 'all', value: 'all' },
];

const targetTypeOptions = [
  { label: 'agent', value: 'agent' },
  { label: 'skill', value: 'skill' },
];

const Rollouts: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<RolloutRecord[]>([]);

  const [targetType, setTargetType] = useState('agent');
  const [targetId, setTargetId] = useState('');

  const [form, setForm] = useState<RolloutRecord>({
    target_type: 'agent',
    target_id: '',
    candidate_id: '',
    mode: 'percentage',
    percentage: 10,
    include_actor_ids: [],
    exclude_actor_ids: [],
    enabled: true,
  });

  const [candidateId, setCandidateId] = useState('');
  const [metricKey, setMetricKey] = useState('');
  const [snapshots, setSnapshots] = useState<MetricSnapshot[]>([]);
  const [metricValue, setMetricValue] = useState('');

  const fetchRollouts = async () => {
    setLoading(true);
    try {
      const res: any = await learningApi.listRollouts({
        target_type: targetType || undefined,
        target_id: targetId || undefined,
        limit: 200,
        offset: 0,
      });
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      toast.error(e?.message || '加载 rollouts 失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchSnapshots = async () => {
    const cid = candidateId.trim();
    if (!cid) {
      setSnapshots([]);
      return;
    }
    setLoading(true);
    try {
      const res: any = await learningApi.listMetricSnapshots(cid, { metric_key: metricKey.trim() || undefined, limit: 200, offset: 0 });
      setSnapshots(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      toast.error(e?.message || '加载 metrics snapshots 失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRollouts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveRollout = async () => {
    const payload: any = {
      target_type: String(form.target_type || '').trim(),
      target_id: String(form.target_id || '').trim(),
      candidate_id: String(form.candidate_id || '').trim(),
      mode: String(form.mode || 'percentage'),
      enabled: !!form.enabled,
    };
    if (!payload.target_type || !payload.target_id || !payload.candidate_id) {
      toast.error('target_type/target_id/candidate_id 必填');
      return;
    }
    if (payload.mode === 'percentage') {
      const p = Number(form.percentage ?? 0);
      if (!Number.isFinite(p) || p < 0 || p > 100) {
        toast.error('percentage 必须是 0-100');
        return;
      }
      payload.percentage = Math.floor(p);
    }
    const inc = (form.include_actor_ids || []).map((x) => String(x).trim()).filter(Boolean);
    const exc = (form.exclude_actor_ids || []).map((x) => String(x).trim()).filter(Boolean);
    if (inc.length) payload.include_actor_ids = inc;
    if (exc.length) payload.exclude_actor_ids = exc;

    setLoading(true);
    try {
      await learningApi.upsertRollout(payload);
      toast.success('已保存 rollout');
      setTargetType(payload.target_type);
      setTargetId(payload.target_id);
      await fetchRollouts();
    } catch (e: any) {
      toastGateError(e, '保存 rollout 失败');
    } finally {
      setLoading(false);
    }
  };

  const deleteRollout = async (r: RolloutRecord) => {
    setLoading(true);
    try {
      await learningApi.deleteRollout({ target_type: String(r.target_type), target_id: String(r.target_id) });
      toast.success('已删除 rollout');
      await fetchRollouts();
    } catch (e: any) {
      toastGateError(e, '删除 rollout 失败');
    } finally {
      setLoading(false);
    }
  };

  const addSnapshot = async () => {
    const cid = candidateId.trim();
    const mk = metricKey.trim();
    const v = Number(metricValue);
    if (!cid || !mk) {
      toast.error('candidate_id 与 metric_key 必填');
      return;
    }
    if (!Number.isFinite(v)) {
      toast.error('value 必须是数字');
      return;
    }
    setLoading(true);
    try {
      await learningApi.addMetricSnapshot(cid, { metric_key: mk, value: v });
      toast.success('已写入 snapshot');
      setMetricValue('');
      await fetchSnapshots();
    } catch (e: any) {
      toastGateError(e, '写入 snapshot 失败');
    } finally {
      setLoading(false);
    }
  };

  const columns = useMemo(
    () => [
      { title: 'target', key: 'target', render: (_: any, r: RolloutRecord) => `${r.target_type}:${r.target_id}` },
      { title: 'candidate_id', dataIndex: 'candidate_id', key: 'candidate_id', width: 320 },
      { title: 'mode', dataIndex: 'mode', key: 'mode', width: 120 },
      { title: 'percentage', dataIndex: 'percentage', key: 'percentage', width: 120, render: (v: any) => (v == null ? '-' : String(v)) },
      {
        title: 'enabled',
        key: 'enabled',
        width: 120,
        render: (_: any, r: RolloutRecord) => <Badge variant={r.enabled ? 'success' : 'default'}>{r.enabled ? 'true' : 'false'}</Badge>,
      },
      {
        title: 'actions',
        key: 'actions',
        width: 140,
        render: (_: any, r: RolloutRecord) => (
          <Button variant="danger" icon={<Trash2 size={14} />} onClick={() => deleteRollout(r)} loading={loading}>
            删除
          </Button>
        ),
      },
    ],
    [loading]
  );

  const snapColumns = useMemo(
    () => [
      { title: 'metric_key', dataIndex: 'metric_key', key: 'metric_key', width: 180 },
      { title: 'value', dataIndex: 'value', key: 'value', width: 120 },
      { title: 'created_at', dataIndex: 'created_at', key: 'created_at', width: 180, render: (v: any) => (v ? new Date(Number(v) * 1000).toISOString() : '-') },
      { title: 'window', key: 'window', render: (_: any, r: MetricSnapshot) => `${r.window_start || '-'} ~ ${r.window_end || '-'}` },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Learning Rollouts & Metrics</h1>
          <div className="text-sm text-gray-500 mt-1">灰度配置（tenant-scoped）与候选指标快照</div>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => { fetchRollouts(); fetchSnapshots(); }} loading={loading}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">Rollouts（灰度配置）</div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <Select
              value={targetType}
              onChange={(v) => setTargetType(String(v))}
              options={targetTypeOptions}
              className="w-36"
            />
            <Input value={targetId} onChange={(e: any) => setTargetId(e.target.value)} placeholder="target_id（可选过滤）" className="w-72" />
            <Button onClick={fetchRollouts} loading={loading}>
              查询
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-gray-200">新增/更新 Rollout</div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2 items-center">
                    <Select
                      value={form.target_type}
                      onChange={(v) => setForm((p) => ({ ...p, target_type: String(v) }))}
                      options={targetTypeOptions}
                      className="w-36"
                    />
                    <Input
                      value={form.target_id}
                      onChange={(e: any) => setForm((p) => ({ ...p, target_id: e.target.value }))}
                      placeholder="target_id"
                      className="w-72"
                    />
                  </div>
                  <Input
                    value={form.candidate_id}
                    onChange={(e: any) => setForm((p) => ({ ...p, candidate_id: e.target.value }))}
                    placeholder="candidate_id"
                  />
                  <div className="flex flex-wrap gap-2 items-center">
                    <Select value={form.mode} onChange={(v) => setForm((p) => ({ ...p, mode: String(v) }))} options={modeOptions} className="w-40" />
                    <Input
                      value={String(form.percentage ?? '')}
                      onChange={(e: any) => setForm((p) => ({ ...p, percentage: Number(e.target.value || 0) }))}
                      placeholder="percentage(0-100)"
                      className="w-40"
                    />
                    <label className="text-xs text-gray-400 flex items-center gap-2">
                      <input type="checkbox" checked={!!form.enabled} onChange={(e) => setForm((p) => ({ ...p, enabled: e.target.checked }))} />
                      enabled
                    </label>
                  </div>
                  <Input
                    value={(form.include_actor_ids || []).join(',')}
                    onChange={(e: any) => setForm((p) => ({ ...p, include_actor_ids: e.target.value.split(',') }))}
                    placeholder="include_actor_ids（逗号分隔，可选）"
                  />
                  <Input
                    value={(form.exclude_actor_ids || []).join(',')}
                    onChange={(e: any) => setForm((p) => ({ ...p, exclude_actor_ids: e.target.value.split(',') }))}
                    placeholder="exclude_actor_ids（逗号分隔，可选）"
                  />
                  <div className="flex justify-end">
                    <Button icon={<Save size={16} />} onClick={saveRollout} loading={loading}>
                      保存
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-gray-200">列表</div>
              </CardHeader>
              <CardContent>
                <Table columns={columns as any} data={items} rowKey={(r: any) => `${r.target_type}:${r.target_id}`} />
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">Metrics Snapshots（候选指标快照）</div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <Input value={candidateId} onChange={(e: any) => setCandidateId(e.target.value)} placeholder="candidate_id" className="w-[420px]" />
            <Input value={metricKey} onChange={(e: any) => setMetricKey(e.target.value)} placeholder="metric_key（例如 error_rate）" className="w-56" />
            <Button variant="secondary" onClick={fetchSnapshots} loading={loading}>
              查询
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-3 mt-3">
            <Input value={metricValue} onChange={(e: any) => setMetricValue(e.target.value)} placeholder="value（数字）" className="w-56" />
            <Button onClick={addSnapshot} loading={loading} disabled={!candidateId.trim() || !metricKey.trim()}>
              写入 snapshot
            </Button>
          </div>

          <div className="mt-3">
            <Table columns={snapColumns as any} data={snapshots} rowKey={(r: any) => String(r.id || `${r.metric_key}:${r.created_at || Math.random()}`)} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Rollouts;

