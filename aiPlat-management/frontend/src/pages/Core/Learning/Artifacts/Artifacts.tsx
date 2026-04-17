import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, RefreshCw } from 'lucide-react';

import { Button, Card, CardContent, CardHeader, Select, Table, toast } from '../../../../components/ui';
import { learningApi, type LearningArtifact } from '../../../../services';

const statusOptions = [
  { label: '全部', value: '' },
  { label: 'draft', value: 'draft' },
  { label: 'published', value: 'published' },
  { label: 'rolled_back', value: 'rolled_back' },
];

const kindOptions = [
  { label: '全部', value: '' },
  { label: 'release_candidate', value: 'release_candidate' },
  { label: 'prompt_revision', value: 'prompt_revision' },
  { label: 'regression_report', value: 'regression_report' },
  { label: 'evaluation_report', value: 'evaluation_report' },
  { label: 'feedback_summary', value: 'feedback_summary' },
  { label: 'skill_evolution', value: 'skill_evolution' },
  { label: 'skill_rollback', value: 'skill_rollback' },
];

const Artifacts: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<LearningArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('');
  const [targetId, setTargetId] = useState('');

  const fetchList = async () => {
    setLoading(true);
    try {
      const res = await learningApi.listArtifacts({
        target_type: 'agent',
        target_id: targetId || undefined,
        kind: kind || undefined,
        status: status || undefined,
        limit: 200,
        offset: 0,
      });
      setItems(res.items || []);
    } catch (e: any) {
      toast.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns = useMemo(
    () => [
      {
        title: 'artifact_id',
        dataIndex: 'artifact_id',
        key: 'artifact_id',
        render: (v: string) => (
          <button
            className="text-left"
            onClick={() => navigate(`/core/learning/artifacts/${String(v)}`)}
            title="打开详情页"
          >
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '').slice(0, 12)}</code>
          </button>
        ),
      },
      { title: 'kind', dataIndex: 'kind', key: 'kind' },
      { title: 'status', dataIndex: 'status', key: 'status' },
      { title: 'target', key: 'target', render: (_: any, r: LearningArtifact) => `${r.target_type}:${r.target_id}` },
      { title: 'version', dataIndex: 'version', key: 'version' },
      {
        title: 'actions',
        key: 'actions',
        render: (_: any, r: LearningArtifact) => (
          <Button
            variant="ghost"
            icon={<Eye size={14} />}
            onClick={() => navigate(`/core/learning/artifacts/${r.artifact_id}`)}
          >
            查看
          </Button>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Learning Artifacts</h1>
          <div className="text-sm text-gray-500 mt-1">learning_artifacts 列表（来自 core ExecutionStore）</div>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchList} loading={loading}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={kind}
              onChange={(v) => setKind(String(v))}
              options={kindOptions}
              placeholder="kind"
              className="w-56"
            />
            <Select
              value={status}
              onChange={(v) => setStatus(String(v))}
              options={statusOptions}
              placeholder="status"
              className="w-40"
            />
            <input
              className="h-10 px-3 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-sm w-64"
              placeholder="target_id（可选，例如 agent_id）"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
            />
            <Button variant="primary" onClick={fetchList}>
              查询
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table columns={columns as any} data={items} rowKey={(r: any) => String(r.artifact_id)} />
        </CardContent>
      </Card>

    </div>
  );
};

export default Artifacts;
