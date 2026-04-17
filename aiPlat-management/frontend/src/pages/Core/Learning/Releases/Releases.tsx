import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, Eye, ExternalLink, RefreshCw, RotateCcw, Settings, Trash2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Select, Table, toast } from '../../../../components/ui';
import { learningApi, type LearningArtifact } from '../../../../services';

type Candidate = LearningArtifact;

function formatTs(v: any): string {
  if (v == null) return '-';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isFinite(n) && n > 1e12) {
    return new Date(n).toISOString();
  }
  if (Number.isFinite(n) && n > 1e9) {
    return new Date(n * 1000).toISOString();
  }
  return String(v);
}

function toNumTsSeconds(v: any): number | null {
  if (v == null) return null;
  const n = typeof v === 'string' ? Number(v) : v;
  if (!Number.isFinite(n)) return null;
  // tolerate ms/seconds
  if (n > 1e12) return Math.floor(n / 1000);
  if (n > 1e9) return Math.floor(n);
  return null;
}

function getPublishedAtTs(c: Candidate): number | null {
  const meta = (c.metadata || {}) as any;
  const p = toNumTsSeconds(meta?.published_at);
  if (p != null) return p;
  const created = toNumTsSeconds(c.created_at);
  return created;
}

function getActiveSortBasis(c: Candidate): { basis: 'published_at' | 'created_at' | 'unknown'; ts: number | null } {
  const meta = (c.metadata || {}) as any;
  const p = toNumTsSeconds(meta?.published_at);
  if (p != null) return { basis: 'published_at', ts: p };
  const created = toNumTsSeconds(c.created_at);
  if (created != null) return { basis: 'created_at', ts: created };
  return { basis: 'unknown', ts: null };
}

function formatRemaining(expiresAtSeconds: number | null): { text: string; expired: boolean } {
  if (expiresAtSeconds == null) return { text: '-', expired: false };
  const now = Math.floor(Date.now() / 1000);
  const diff = expiresAtSeconds - now;
  const expired = diff <= 0;
  const s = Math.abs(diff);
  if (s < 60) return { text: `${expired ? '-' : ''}${s}s`, expired };
  if (s < 3600) return { text: `${expired ? '-' : ''}${Math.floor(s / 60)}m`, expired };
  if (s < 86400) return { text: `${expired ? '-' : ''}${Math.floor(s / 3600)}h`, expired };
  return { text: `${expired ? '-' : ''}${Math.floor(s / 86400)}d`, expired };
}

const Releases: React.FC = () => {
  const navigate = useNavigate();
  const [agentId, setAgentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [published, setPublished] = useState<Candidate[]>([]);
  const [history, setHistory] = useState<Candidate[]>([]);
  const [historyStatus, setHistoryStatus] = useState<string>('');

  const [ttlOpen, setTtlOpen] = useState(false);
  const [ttlCandidateId, setTtlCandidateId] = useState<string>('');
  const [ttlSeconds, setTtlSeconds] = useState<string>('');
  const [expiresAt, setExpiresAt] = useState<string>('');

  const [rbOpen, setRbOpen] = useState(false);
  const [rbResult, setRbResult] = useState<any>(null);
  const [rbBaselineCandidateId, setRbBaselineCandidateId] = useState<string>('');
  const [rbCurrentWindow, setRbCurrentWindow] = useState<string>('50');
  const [rbBaselineWindow, setRbBaselineWindow] = useState<string>('50');
  const [rbMinSamples, setRbMinSamples] = useState<string>('10');
  const [rbErDeltaThr, setRbErDeltaThr] = useState<string>('0.1');
  const [rbAvgDurThr, setRbAvgDurThr] = useState<string>('');
  const [rbLinkBaseline, setRbLinkBaseline] = useState<boolean>(false);
  const [rbMaxLinkedEvidence, setRbMaxLinkedEvidence] = useState<string>('200');
  const [rbRequireApproval, setRbRequireApproval] = useState<boolean>(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const pub = await learningApi.listArtifacts({
        target_type: 'agent',
        target_id: agentId || undefined,
        kind: 'release_candidate',
        status: 'published',
        limit: 50,
        offset: 0,
      });
      const pubItems = (pub.items || []) as Candidate[];
      pubItems.sort((a, b) => (getPublishedAtTs(b) || 0) - (getPublishedAtTs(a) || 0));
      setPublished(pubItems);

      const hist = await learningApi.listArtifacts({
        target_type: 'agent',
        target_id: agentId || undefined,
        kind: 'release_candidate',
        status: historyStatus || undefined,
        // history: include rolled_back/draft by not filtering status
        limit: 200,
        offset: 0,
      });
      const items = (hist.items || []) as Candidate[];
      items.sort((a, b) => (getPublishedAtTs(b) || 0) - (getPublishedAtTs(a) || 0));
      setHistory(items);
    } catch (e: any) {
      toast.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCandidateDetail = (c: Candidate) => {
    navigate(`/core/learning/artifacts/${c.artifact_id}`);
  };

  const openRollbackReport = async (c: Candidate) => {
    const meta = (c.metadata || {}) as any;
    const rid = meta.rollback_regression_report_id;
    if (!rid) {
      toast.info('该 candidate 未记录 rollback_regression_report_id');
      return;
    }
    navigate(`/core/learning/artifacts/${String(rid)}`);
  };

  const openTtlEditor = (c: Candidate) => {
    const meta = (c.metadata || {}) as any;
    setTtlCandidateId(c.artifact_id);
    setTtlSeconds(meta?.ttl_seconds != null ? String(meta.ttl_seconds) : '');
    setExpiresAt(meta?.expires_at != null ? String(meta.expires_at) : '');
    setTtlOpen(true);
  };

  const saveTtl = async () => {
    if (!ttlCandidateId) return;
    const mu: Record<string, unknown> = {};
    if (ttlSeconds.trim()) {
      const n = Number(ttlSeconds);
      if (!Number.isFinite(n) || n <= 0) {
        toast.error('ttl_seconds 必须是正数');
        return;
      }
      mu.ttl_seconds = n;
    }
    if (expiresAt.trim()) {
      const n = Number(expiresAt);
      if (!Number.isFinite(n) || n <= 0) {
        toast.error('expires_at 必须是 unix seconds 或 unix ms');
        return;
      }
      mu.expires_at = n;
    }
    try {
      // 用 status=published + metadata_update 做“只更新 TTL 信息”，避免重复 publish 副作用
      await learningApi.setArtifactStatus(ttlCandidateId, 'published', mu);
      toast.success('已更新 TTL');
      setTtlOpen(false);
      fetchData();
    } catch (e: any) {
      toast.error(e?.message || '更新失败');
    }
  };

  const rollback = async (candidateId: string) => {
    try {
      await learningApi.rollbackCandidate(candidateId, { user_id: 'admin', require_approval: false, reason: 'manual' });
      toast.success('已回滚');
      fetchData();
    } catch (e: any) {
      toast.error(e?.message || '回滚失败');
    }
  };

  const expireNow = async () => {
    try {
      await learningApi.expireReleases({ target_type: 'agent', target_id: agentId || undefined, now: Math.floor(Date.now() / 1000) });
      toast.success('已执行 expire 检查');
      fetchData();
    } catch (e: any) {
      toast.error(e?.message || 'expire 失败');
    }
  };

  const publishedActive = published?.[0];
  const activeBasis = publishedActive ? getActiveSortBasis(publishedActive) : null;

  const columns = useMemo(
    () => [
      {
        title: 'candidate_id',
        dataIndex: 'artifact_id',
        key: 'artifact_id',
        render: (v: string) => (
          <button className="text-left" onClick={() => navigate(`/core/learning/artifacts/${String(v)}`)} title="打开详情页">
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '')}</code>
          </button>
        ),
      },
      { title: 'version', dataIndex: 'version', key: 'version' },
      {
        title: 'status',
        dataIndex: 'status',
        key: 'status',
        render: (v: string) => <Badge variant={v === 'published' ? 'success' : v === 'rolled_back' ? 'error' : 'default'}>{v}</Badge>,
      },
      {
        title: 'expires_at',
        key: 'expires_at',
        render: (_: any, r: Candidate) => {
          const exp = toNumTsSeconds((r.metadata as any)?.expires_at);
          const rem = formatRemaining(exp);
          return (
            <div className="flex flex-col gap-0.5">
              <div className="text-xs text-gray-300">{formatTs((r.metadata as any)?.expires_at)}</div>
              <div className={`text-xs ${rem.expired ? 'text-red-400' : 'text-gray-500'}`}>{rem.text}</div>
            </div>
          );
        },
      },
      {
        title: 'rollback_report',
        key: 'rollback_report',
        render: (_: any, r: Candidate) => {
          const rid = (r.metadata as any)?.rollback_regression_report_id;
          return rid ? (
            <button className="text-left" onClick={() => navigate(`/core/learning/artifacts/${String(rid)}`)} title="打开回滚报告">
              <code className="text-xs">{String(rid).slice(0, 12)}</code>
            </button>
          ) : (
            '-'
          );
        },
      },
      {
        title: 'actions',
        key: 'actions',
        render: (_: any, r: Candidate) => (
          <div className="flex items-center gap-2">
            <Button variant="ghost" icon={<Eye size={14} />} onClick={() => openCandidateDetail(r)}>
              详情
            </Button>
            <Button variant="ghost" icon={<RotateCcw size={14} />} onClick={() => openRollbackReport(r)}>
              回滚原因
            </Button>
            {r.trace_id && (
              <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/traces/${r.trace_id}`)}>
                Trace
              </Button>
            )}
            <Button variant="ghost" icon={<Settings size={14} />} onClick={() => openTtlEditor(r)}>
              TTL
            </Button>
            {r.status === 'published' && (
              <Button variant="secondary" icon={<Trash2 size={14} />} onClick={() => rollback(r.artifact_id)}>
                回滚
              </Button>
            )}
          </div>
        ),
      },
    ],
    []
  );

  const runAutoRollback = async (dryRun: boolean) => {
    if (!agentId) {
      toast.error('请先填写 agent_id');
      return;
    }
    try {
      const payload: Record<string, unknown> = {
        agent_id: agentId,
        candidate_id: publishedActive?.artifact_id,
        baseline_candidate_id: rbBaselineCandidateId || undefined,
        current_window: Number(rbCurrentWindow) || 50,
        baseline_window: Number(rbBaselineWindow) || 50,
        min_samples: Number(rbMinSamples) || 10,
        error_rate_delta_threshold: Number(rbErDeltaThr) || 0.1,
        avg_duration_delta_threshold: rbAvgDurThr.trim() ? Number(rbAvgDurThr) : undefined,
        link_baseline: rbLinkBaseline,
        max_linked_evidence: Number(rbMaxLinkedEvidence) || 200,
        require_approval: rbRequireApproval,
        dry_run: dryRun,
        user_id: 'admin',
      };
      const res = await learningApi.autoRollbackRegression(payload);
      setRbResult(res);
      setRbOpen(true);
      if (!dryRun && res?.status === 'approval_required') {
        toast.info('已创建审批请求，请到审批中心处理');
      }
      if (!dryRun && res?.rollback === 'done') {
        toast.success('回滚已执行');
        fetchData();
      }
    } catch (e: any) {
      toast.error(e?.message || '执行失败');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Release Candidates</h1>
          <div className="text-sm text-gray-500 mt-1">active candidate、TTL/expires_at、历史与回滚原因（regression_report）</div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" icon={<Clock size={16} />} onClick={expireNow} disabled={!agentId}>
            立即检查过期
          </Button>
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchData} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              className="w-72"
              placeholder="agent_id（必填，用于查询/expire/回归回滚）"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            />
            <Select
              className="w-44"
              value={historyStatus}
              onChange={(v) => setHistoryStatus(v)}
              options={[
                { label: '全部状态', value: '' },
                { label: 'draft', value: 'draft' },
                { label: 'published', value: 'published' },
                { label: 'rolled_back', value: 'rolled_back' },
              ]}
            />
            <Button variant="primary" onClick={fetchData}>
              查询
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-3 text-sm text-gray-300">
            Active published candidate：{' '}
            {publishedActive ? (
              <>
                <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{publishedActive.artifact_id}</code>
                <span className="ml-2 text-gray-500">
                  排序依据: {activeBasis?.basis} {activeBasis?.ts != null ? `(${formatTs(activeBasis.ts)})` : ''}
                </span>
                <span className="ml-2 text-gray-500">expires_at: {formatTs((publishedActive.metadata as any)?.expires_at)}</span>
              </>
            ) : (
              <span className="text-gray-500">无</span>
            )}
          </div>

          <Table columns={columns as any} data={history} rowKey={(r: any) => String(r.artifact_id)} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-gray-200">回归回滚（auto-rollback-regression）</div>
              <div className="text-xs text-gray-500 mt-1">支持 dry-run 预览、执行回滚与 require-approval 走审批门</div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => runAutoRollback(true)}>
                预览(dry-run)
              </Button>
              <Button variant="primary" onClick={() => runAutoRollback(false)}>
                执行
              </Button>
              <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate('/core/approvals')}>
                去审批中心
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Input label="baseline_candidate_id（可选）" value={rbBaselineCandidateId} onChange={(e) => setRbBaselineCandidateId(e.target.value)} />
            <Input label="current_window" value={rbCurrentWindow} onChange={(e) => setRbCurrentWindow(e.target.value)} />
            <Input label="baseline_window" value={rbBaselineWindow} onChange={(e) => setRbBaselineWindow(e.target.value)} />
            <Input label="min_samples" value={rbMinSamples} onChange={(e) => setRbMinSamples(e.target.value)} />
            <Input label="error_rate_delta_threshold" value={rbErDeltaThr} onChange={(e) => setRbErDeltaThr(e.target.value)} />
            <Input label="avg_duration_delta_threshold（可选，ms）" value={rbAvgDurThr} onChange={(e) => setRbAvgDurThr(e.target.value)} />
            <Input label="max_linked_evidence" value={rbMaxLinkedEvidence} onChange={(e) => setRbMaxLinkedEvidence(e.target.value)} />
            <Select
              label="link_baseline"
              value={rbLinkBaseline ? 'true' : 'false'}
              onChange={(v) => setRbLinkBaseline(v === 'true')}
              options={[
                { label: 'false', value: 'false' },
                { label: 'true', value: 'true' },
              ]}
            />
            <Select
              label="require_approval"
              value={rbRequireApproval ? 'true' : 'false'}
              onChange={(v) => setRbRequireApproval(v === 'true')}
              options={[
                { label: 'true', value: 'true' },
                { label: 'false', value: 'false' },
              ]}
            />
          </div>
        </CardContent>
      </Card>

      <Modal
        open={ttlOpen}
        onClose={() => setTtlOpen(false)}
        title={ttlCandidateId ? `设置 TTL: ${ttlCandidateId}` : '设置 TTL'}
        width={640}
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" onClick={() => setTtlOpen(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={saveTtl}>
              保存
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <div className="text-xs text-gray-500">
            写入到 candidate.metadata：ttl_seconds / expires_at。expires_at 支持 unix seconds 或 unix ms。
          </div>
          <Input label="ttl_seconds（可选）" value={ttlSeconds} onChange={(e) => setTtlSeconds(e.target.value)} placeholder="例如 3600" />
          <Input label="expires_at（可选）" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} placeholder="例如 1710000000" />
        </div>
      </Modal>

      <Modal
        open={rbOpen}
        onClose={() => setRbOpen(false)}
        title="auto-rollback-regression 结果"
        width={920}
        footer={<Button onClick={() => setRbOpen(false)}>关闭</Button>}
      >
        <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(rbResult || {}, null, 2)}
        </pre>
      </Modal>
    </div>
  );
};

export default Releases;
