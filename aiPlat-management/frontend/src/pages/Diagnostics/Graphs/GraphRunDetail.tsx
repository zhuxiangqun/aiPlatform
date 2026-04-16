import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Copy, Eye, Play, RefreshCw, Share2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Modal, Table, Tabs, notify, toast } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const toBadgeVariant = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  if (status === 'completed' || status === 'success' || status === 'healthy') return 'success';
  if (status === 'degraded' || status === 'warn' || status === 'warning') return 'warning';
  if (status === 'failed' || status === 'error' || status === 'unhealthy') return 'error';
  if (status === 'running') return 'info';
  return 'default';
};

const GraphRunDetail: React.FC = () => {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stateModalOpen, setStateModalOpen] = useState(false);
  const [stateModalTitle, setStateModalTitle] = useState('状态');
  const [stateModalPayload, setStateModalPayload] = useState<any>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmMode, setConfirmMode] = useState<'resume' | 'resume_execute'>('resume');
  const [pendingCheckpointId, setPendingCheckpointId] = useState<string | undefined>(undefined);

  const load = async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await diagnosticsApi.getGraphRun(runId, true);
      setData(res);
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const run = data?.run || null;
  const checkpoints: any[] = Array.isArray(data?.checkpoints?.checkpoints) ? data.checkpoints.checkpoints : [];

  const checkpointColumns = useMemo(
    () => [
      {
        key: 'checkpoint_id',
        title: 'checkpoint_id',
        dataIndex: 'checkpoint_id',
        render: (val: string) => (
          <div className="flex items-center gap-2">
            <code className="text-xs text-gray-200">{val}</code>
            <Button variant="ghost" onClick={() => navigator.clipboard.writeText(val)} icon={<Copy size={14} />} />
          </div>
        ),
      },
      { key: 'step', title: 'step', dataIndex: 'step', align: 'right' as const },
      { key: 'created_at', title: 'created_at', dataIndex: 'created_at' },
      {
        key: 'actions',
        title: 'actions',
        render: (_: any, record: any) => (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              icon={<Eye size={14} />}
              onClick={() => {
                setStateModalTitle(`Checkpoint State: ${record.checkpoint_id}`);
                setStateModalPayload(record.state);
                setStateModalOpen(true);
              }}
            >
              查看 state
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setPendingCheckpointId(record.checkpoint_id);
                setConfirmMode('resume');
                setConfirmOpen(true);
              }}
            >
              Resume
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingCheckpointId(record.checkpoint_id);
                setConfirmMode('resume_execute');
                setConfirmOpen(true);
              }}
            >
              Resume & Execute
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  const resume = async (execute: boolean, checkpointId?: string) => {
    if (!runId) return;
    setActionLoading(true);
    try {
      const payload: Record<string, unknown> = { user_id: 'system' };
      if (checkpointId) payload.checkpoint_id = checkpointId;
      const res: any = execute
        ? await diagnosticsApi.resumeExecuteGraphRun(runId, payload)
        : await diagnosticsApi.resumeGraphRun(runId, payload);
      // best effort: jump to links for new run id if available
      const newRunId = res?.result?.run_id || res?.resumed?.run_id || res?.run_id;
      if (newRunId) {
        toast.success('已创建新的 Run', String(newRunId));
        notify.success(
          execute ? 'Resume & Execute 已触发' : 'Resume 已触发',
          `new_run_id: ${newRunId}`,
          `/diagnostics/links?graph_run_id=${encodeURIComponent(String(newRunId))}`
        );
        navigate(`/diagnostics/graphs/${newRunId}`);
      } else {
        await load();
      }
    } catch (e: any) {
      setError(e?.message || '执行失败');
      toast.error('执行失败', String(e?.message || ''));
      notify.error(execute ? 'Resume & Execute 失败' : 'Resume 失败', String(e?.message || ''));
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Graph Run</h1>
          <div className="text-sm text-gray-500 mt-1 break-all">{runId}</div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => runId && navigator.clipboard.writeText(runId)} icon={<Copy size={16} />}>
            复制 ID
          </Button>
          <Link to={`/diagnostics/links?graph_run_id=${encodeURIComponent(runId || '')}`}>
            <Button variant="primary" icon={<Share2 size={16} />}>
              打开 Links
            </Button>
          </Link>
        </div>
      </div>

      {error && <div className="text-sm text-error">{error}</div>}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-gray-200">概览</div>
            <div className="flex items-center gap-2">
              {run?.status && <Badge variant={toBadgeVariant(run.status)}>{run.status}</Badge>}
              <Button variant="ghost" onClick={load} icon={<RefreshCw size={16} />} loading={loading} />
              <Button
                variant="secondary"
                onClick={() => {
                  setPendingCheckpointId(undefined);
                  setConfirmMode('resume');
                  setConfirmOpen(true);
                }}
                icon={<Play size={16} />}
                loading={actionLoading}
              >
                Resume
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  setPendingCheckpointId(undefined);
                  setConfirmMode('resume_execute');
                  setConfirmOpen(true);
                }}
                icon={<Play size={16} />}
                loading={actionLoading}
              >
                Resume & Execute
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Tabs
            tabs={[
              {
                key: 'summary',
                label: 'Summary',
                children: (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                      <div className="p-3 bg-dark-bg rounded-lg">
                        <div className="text-xs text-gray-400 mb-1">run_id</div>
                        <div className="flex items-center gap-2">
                          <code className="text-xs text-gray-200 break-all">{run?.run_id || runId}</code>
                          <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(String(run?.run_id || runId || ''))} />
                        </div>
                      </div>
                      <div className="p-3 bg-dark-bg rounded-lg">
                        <div className="text-xs text-gray-400 mb-1">graph_name</div>
                        <div className="text-sm font-medium text-gray-100">{run?.graph_name || '-'}</div>
                      </div>
                      <div className="p-3 bg-dark-bg rounded-lg">
                        <div className="text-xs text-gray-400 mb-1">trace_id</div>
                        <div className="text-sm font-medium text-gray-100 break-all">{run?.trace_id || '-'}</div>
                      </div>
                      <div className="p-3 bg-dark-bg rounded-lg">
                        <div className="text-xs text-gray-400 mb-1">parent_run_id</div>
                        <div className="text-sm font-medium text-gray-100 break-all">{run?.parent_run_id || '-'}</div>
                      </div>
                      <div className="p-3 bg-dark-bg rounded-lg">
                        <div className="text-xs text-gray-400 mb-1">resumed_from_checkpoint_id</div>
                        <div className="text-sm font-medium text-gray-100 break-all">{run?.resumed_from_checkpoint_id || '-'}</div>
                      </div>
                      <div className="p-3 bg-dark-bg rounded-lg">
                        <div className="text-xs text-gray-400 mb-1">duration_ms</div>
                        <div className="text-sm font-medium text-gray-100">{run?.duration_ms ?? '-'}</div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <Button
                        variant="secondary"
                        icon={<Eye size={16} />}
                        onClick={() => {
                          setStateModalTitle('initial_state');
                          setStateModalPayload(run?.initial_state || {});
                          setStateModalOpen(true);
                        }}
                      >
                        查看 initial_state
                      </Button>
                      <Button
                        variant="secondary"
                        icon={<Eye size={16} />}
                        onClick={() => {
                          setStateModalTitle('final_state');
                          setStateModalPayload(run?.final_state || {});
                          setStateModalOpen(true);
                        }}
                      >
                        查看 final_state
                      </Button>
                    </div>
                  </div>
                ),
              },
              {
                key: 'checkpoints',
                label: `Checkpoints (${Array.isArray(checkpoints) ? checkpoints.length : 0})`,
                children: (
                  <Table columns={checkpointColumns as any} data={checkpoints} rowKey="checkpoint_id" />
                ),
              },
            ]}
          />
        </CardContent>
      </Card>

      <Modal
        open={stateModalOpen}
        onClose={() => setStateModalOpen(false)}
        title={stateModalTitle}
        width={900}
        footer={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => navigator.clipboard.writeText(JSON.stringify(stateModalPayload ?? {}, null, 2))}
              icon={<Copy size={16} />}
            >
              复制 JSON
            </Button>
            <Button onClick={() => setStateModalOpen(false)}>关闭</Button>
          </div>
        }
      >
        <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(stateModalPayload ?? {}, null, 2)}
        </pre>
      </Modal>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={confirmMode === 'resume_execute' ? '确认执行：Resume & Execute' : '确认执行：Resume'}
        width={560}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button
              variant={confirmMode === 'resume_execute' ? 'danger' : 'primary'}
              loading={actionLoading}
              onClick={async () => {
                setConfirmOpen(false);
                await resume(confirmMode === 'resume_execute', pendingCheckpointId);
              }}
            >
              确认
            </Button>
          </>
        }
      >
        <div className="space-y-2 text-sm text-gray-300">
          <div>
            run_id：<code className="text-xs">{runId}</code>
          </div>
          {pendingCheckpointId && (
            <div>
              checkpoint_id：<code className="text-xs">{pendingCheckpointId}</code>
            </div>
          )}
          {confirmMode === 'resume_execute' ? (
            <div className="text-warning">
              该操作会从 checkpoint 恢复并继续执行，系统将创建一个新的 run。请确认后再继续。
            </div>
          ) : (
            <div className="text-gray-400">
              该操作会从 checkpoint 恢复并创建新的 run（不继续执行）。
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default GraphRunDetail;
