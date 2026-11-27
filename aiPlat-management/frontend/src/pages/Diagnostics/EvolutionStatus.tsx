/**
 * 五域 + 小朱自进化状态可见面：目标进度 / 时间线 / 待批与回滚纠偏。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Check, X, Undo2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, toast } from '../../components/ui';
import { toastGateError } from '../../components/ui';
import { diagnosticsApi } from '../../services';
import { clearPageData, reportPageData } from '../../lib/pageDataBridge';
import { evolutionStatusGlossaryText } from '../../lib/consultantLayerA';

type GoalRow = {
  goal_id?: string;
  domain?: string;
  title?: string;
  description?: string;
  meets?: boolean | null;
  value?: number | string | null;
  baseline_missing?: boolean;
  measured_at?: number;
  threshold?: number;
  reason?: string;
};

type ProposalRow = {
  id: string;
  kind?: string;
  title?: string;
  summary?: string;
  status?: string;
  created_at?: number;
  updated_at?: number;
  goal_id?: string;
};

type TimelineEvent = {
  ts?: number;
  event?: string;
  proposal_id?: string;
  kind?: string;
  title?: string;
  status?: string;
  reason?: string;
  summary?: string;
};

function fmtTs(ts?: number): string {
  if (!ts) return '—';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

function statusBadge(st?: string) {
  const s = (st || '').toUpperCase();
  if (s === 'HUMAN_GATE') return <Badge variant="warning">待批</Badge>;
  if (s === 'APPLIED') return <Badge variant="success">已应用</Badge>;
  if (s === 'APPROVED') return <Badge variant="info">已批准</Badge>;
  if (s === 'REJECTED') return <Badge variant="error">已拒绝</Badge>;
  if (s === 'ROLLED_BACK') return <Badge variant="default">已回滚</Badge>;
  return <Badge variant="default">{st || '—'}</Badge>;
}

const EvolutionStatus: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await diagnosticsApi.getEvolutionStatus({ limit: 50 });
      setData(res);
    } catch (e: any) {
      setData(null);
      toastGateError(e, '加载自进化状态失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const goals = (data?.goals?.goals || data?.goals || []) as GoalRow[];
    const goalList = Array.isArray(goals) ? goals : [];
    const pending = (data?.pending || []) as ProposalRow[];
    const applied = (data?.applied || []) as ProposalRow[];
    reportPageData('/diagnostics/evolution-status', {
      guideGlossary: evolutionStatusGlossaryText(),
      pendingCount: data?.pending_count ?? pending.length,
      appliedCount: applied.length,
      goalMetCount: goalList.filter((g) => g?.meets === true).length,
      goalTotal: goalList.length,
      timelineCount: Array.isArray(data?.timeline) ? data.timeline.length : 0,
      e5Claimed: false,
      feedsProductionRouting: false,
    });
    return () => clearPageData('/diagnostics/evolution-status');
  }, [data]);

  const decide = async (id: string, decision: 'approve' | 'reject') => {
    setBusyId(id);
    try {
      const res = await diagnosticsApi.decideEvolutionProposal(id, { decision });
      if (res?.ok === false) {
        toast.error(String(res?.reason || '操作失败'));
      } else {
        toast.success(decision === 'approve' ? '已批准（有界应用）' : '已拒绝');
        await load();
      }
    } catch (e: any) {
      toastGateError(e, '决策失败');
    } finally {
      setBusyId('');
    }
  };

  const rollback = async (id: string) => {
    const reason = window.prompt('纠偏原因（将写入台账）', '方向不对') || '';
    if (!reason.trim()) {
      toast.error('请填写回滚原因');
      return;
    }
    setBusyId(id);
    try {
      const res = await diagnosticsApi.rollbackEvolutionProposal(id, { reason: reason.trim() });
      if (res?.ok === false) {
        toast.error(String(res?.reason || '回滚失败'));
      } else {
        toast.success('已回滚（有界撤销；不改生产选模）');
        await load();
      }
    } catch (e: any) {
      toastGateError(e, '回滚失败');
    } finally {
      setBusyId('');
    }
  };

  const goalsRaw = data?.goals?.goals ?? data?.goals ?? [];
  const goals: GoalRow[] = Array.isArray(goalsRaw) ? goalsRaw : [];
  const pending: ProposalRow[] = Array.isArray(data?.pending) ? data.pending : [];
  const applied: ProposalRow[] = Array.isArray(data?.applied) ? data.applied : [];
  const timeline: TimelineEvent[] = Array.isArray(data?.timeline) ? data.timeline : [];

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Link to="/diagnostics" className="text-slate-400 hover:text-slate-200">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-slate-100">自进化状态</h1>
            <p className="text-sm text-slate-400">
              五域目标 + 小朱提案时间线；待批可拒、已应用可回滚（不宣称 E5 / 不改生产选模）
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </Button>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-medium text-slate-300">五域目标进度</h2>
          <p className="text-xs text-slate-500 mt-1">
            五域 = 小朱自进化盯的 5 件事（答得好不好、测全没、交付齐没、经验靠谱吗、试点备好没）。
            「还缺数据」表示样本/库存不够，先补材料再看进度。
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {goals.length === 0 && (
            <Card>
              <CardContent className="py-4 text-sm text-slate-400">
                {loading ? '加载中…' : '暂无目标测量（或缺测）'}
              </CardContent>
            </Card>
          )}
          {goals.map((g) => (
            <Card key={g.goal_id || g.title}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-medium text-slate-100 leading-snug">
                    {g.title || g.goal_id || '目标'}
                  </span>
                  {g.meets === true ? (
                    <Badge variant="success">达标</Badge>
                  ) : g.baseline_missing ? (
                    <Badge variant="warning">还缺数据</Badge>
                  ) : (
                    <Badge variant="default">未达标</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="text-xs text-slate-400 space-y-2">
                {g.description ? (
                  <p className="text-slate-400 leading-relaxed">{g.description}</p>
                ) : null}
                <div>
                  当前进度：{g.value == null ? '—' : String(g.value)}
                  {g.threshold != null ? `（达标线 ≥ ${g.threshold}）` : ''}
                </div>
                <div>更新：{fmtTs(g.measured_at)}</div>
                {g.reason ? <div className="text-amber-400/90">{g.reason}</div> : null}
                <div className="text-[11px] text-slate-600 font-mono truncate" title={g.goal_id}>
                  机读 id：{g.goal_id || '—'}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-slate-300">时间线</h2>
        <Card>
          <CardContent className="py-3 space-y-2 max-h-72 overflow-y-auto">
            {timeline.length === 0 && (
              <div className="text-sm text-slate-400">{loading ? '加载中…' : '暂无事件'}</div>
            )}
            {timeline.map((ev, i) => (
              <div
                key={`${ev.proposal_id}-${ev.event}-${ev.ts}-${i}`}
                className="flex gap-3 text-sm border-b border-slate-800/60 pb-2 last:border-0"
              >
                <div className="w-40 shrink-0 text-xs text-slate-500">{fmtTs(ev.ts)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-200">{ev.event || 'event'}</span>
                    {statusBadge(ev.status)}
                    <span className="text-xs text-slate-500">{ev.kind}</span>
                  </div>
                  <div className="text-slate-400 truncate">{ev.title || ev.proposal_id}</div>
                  {(ev.reason || ev.summary) && (
                    <div className="text-xs text-slate-500 truncate">{ev.reason || ev.summary}</div>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-slate-300">
          待批（{pending.length}）
        </h2>
        <div className="space-y-2">
          {pending.length === 0 && (
            <div className="text-sm text-slate-400">无待批提案</div>
          )}
          {pending.map((p) => (
            <Card key={p.id}>
              <CardContent className="py-3 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    {statusBadge(p.status)}
                    <span className="text-slate-200 text-sm">{p.title || p.id}</span>
                    <span className="text-xs text-slate-500">{p.kind}</span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">{p.summary || '—'}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    {fmtTs(p.created_at)} · {p.goal_id || '无 goal_id'}
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyId === p.id}
                    onClick={() => decide(p.id, 'approve')}
                  >
                    <Check className="w-3 h-3 mr-1" />
                    批准
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyId === p.id}
                    onClick={() => decide(p.id, 'reject')}
                  >
                    <X className="w-3 h-3 mr-1" />
                    拒绝
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-slate-300">
          已应用（可回滚 · {applied.length}）
        </h2>
        <div className="space-y-2">
          {applied.length === 0 && (
            <div className="text-sm text-slate-400">无已应用提案</div>
          )}
          {applied.map((p) => (
            <Card key={p.id}>
              <CardContent className="py-3 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    {statusBadge(p.status)}
                    <span className="text-slate-200 text-sm">{p.title || p.id}</span>
                    <span className="text-xs text-slate-500">{p.kind}</span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">{p.summary || '—'}</div>
                  <div className="text-xs text-slate-500 mt-1">{fmtTs(p.updated_at || p.created_at)}</div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId === p.id}
                  onClick={() => rollback(p.id)}
                >
                  <Undo2 className="w-3 h-3 mr-1" />
                  回滚
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
};

export default EvolutionStatus;
