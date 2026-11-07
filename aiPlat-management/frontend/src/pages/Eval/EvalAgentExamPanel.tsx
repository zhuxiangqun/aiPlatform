/**
 * Agent eval: pick agent + case set → dry-run or live + attributable report.
 * Single-paper vs local smoke suite are separate sub-tabs (save viewport).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { agentEvalApi, workspaceAgentApi } from '../../services';
import type { Agent } from '../../services';
import EvalAttributableReportCard, {
  type AttributableReport,
} from './EvalAttributableReportCard';
import EvalExamSuitePanel from './EvalExamSuitePanel';
import EvalFullReportPanel from './EvalFullReportPanel';
import { buildFullSinglePaperReport } from './fullExamReport';
import { agentExamRuntimeAnn, formatRuntimeAnn } from './examRuntimeTier';

type ExamSet = {
  set_id: string;
  category?: string;
  description?: string;
  tasks?: number;
};

type ExamSubTab = 'single' | 'suite';

const SUBTAB_STORAGE = 'aiplat.eval.agentExam.subTab';

function readSubTab(): ExamSubTab {
  try {
    const v = localStorage.getItem(SUBTAB_STORAGE);
    if (v === 'suite' || v === 'single') return v;
  } catch {
    /* ignore */
  }
  return 'single';
}

type Props = {
  /** Pre-select agent when opened from dashboard picker. */
  agentId?: string;
  onAgentChange?: (id: string) => void;
  /** Notify parent when exam paper changes (history/report scope). */
  onSetChange?: (setId: string) => void;
  onExamDone?: () => void;
};

export default function EvalAgentExamPanel({
  agentId = '',
  onAgentChange,
  onSetChange,
  onExamDone,
}: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sets, setSets] = useState<ExamSet[]>([]);
  const [selectedAgent, setSelectedAgent] = useState(agentId);
  const [setId, setSetId] = useState('default/normal');
  const [busyMode, setBusyMode] = useState<'dry' | 'live' | null>(null);
  const busy = busyMode !== null;
  const [suiteBusy, setSuiteBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [report, setReport] = useState<AttributableReport | null>(null);
  /** session = 本页刚跑完；stored = 主动加载的落盘历史（≠ 本会话结果） */
  const [reportSource, setReportSource] = useState<'session' | 'stored' | null>(null);
  const [subTab, setSubTab] = useState<ExamSubTab>(() => readSubTab());
  const [inspectHint, setInspectHint] = useState('');
  const examLocked = busy || suiteBusy;
  const singleFullReport = useMemo(() => {
    if (!report || report.ok === false) return null;
    const aid = selectedAgent.trim();
    const sid = setId.trim();
    if (!aid || !sid) return null;
    return buildFullSinglePaperReport({ agentId: aid, setId: sid, report });
  }, [report, selectedAgent, setId]);

  const pickSubTab = useCallback((t: ExamSubTab) => {
    if (examLocked) return;
    setSubTab(t);
    try {
      localStorage.setItem(SUBTAB_STORAGE, t);
    } catch {
      /* ignore */
    }
  }, [examLocked]);

  useEffect(() => {
    setSelectedAgent(agentId);
    setReport(null);
    setReportSource(null);
    setMsg('');
  }, [agentId]);

  useEffect(() => {
    workspaceAgentApi
      .list({ limit: 200 })
      .then((res) => setAgents(Array.isArray(res?.agents) ? res.agents : []))
      .catch(() => setAgents([]));
    agentEvalApi
      .listExamSets()
      .then((res) => {
        const items = Array.isArray(res?.items) ? res.items : [];
        setSets(items);
        if (items.length && !items.some((s) => s.set_id === setId)) {
          const next = items[0].set_id;
          setSetId(next);
          onSetChange?.(next);
        } else if (setId) {
          onSetChange?.(setId);
        }
      })
      .catch(() => setSets([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load only
  }, []);

  const loadReport = useCallback(
    async (aid: string, sid: string, source: 'session' | 'stored' = 'stored') => {
      if (!aid.trim()) {
        setReport(null);
        setReportSource(null);
        return;
      }
      try {
        // Scope to selected paper — never show auto_session as if it were this exam.
        const res = await agentEvalApi.attributableReport(aid.trim(), 5, sid.trim());
        setReport(res as AttributableReport);
        setReportSource(source);
      } catch {
        setReport(null);
        setReportSource(null);
      }
    },
    [],
  );

  const inspectFromSuite = useCallback(
    (payload: { dimId: string; setId: string; title: string; status: string }) => {
      if (suiteBusy || busy) return;
      const sid = String(payload.setId || '').trim();
      const aid = selectedAgent.trim();
      if (!sid) return;
      setSetId(sid);
      onSetChange?.(sid);
      setSubTab('single');
      try {
        localStorage.setItem(SUBTAB_STORAGE, 'single');
      } catch {
        /* ignore */
      }
      setInspectHint(
        `已从冒烟跳到「${payload.title}」相关题集 ${sid}，下方是那次保存的结果。先看问题再改；不要马上重跑，否则可能碰巧变好、看不出刚才哪里挂了。`,
      );
      setError('');
      setMsg('');
      if (aid) void loadReport(aid, sid, 'stored');
      else {
        setReport(null);
        setReportSource(null);
      }
    },
    [suiteBusy, busy, onSetChange, selectedAgent, loadReport],
  );

  const pickAgent = (id: string) => {
    setSelectedAgent(id);
    onAgentChange?.(id);
    setReport(null);
    setReportSource(null);
    setMsg('');
    setInspectHint('');
  };

  const pickSet = (id: string) => {
    setSetId(id);
    onSetChange?.(id);
    setReport(null);
    setReportSource(null);
    setMsg('');
  };

  const run = useCallback(
    async (live: boolean) => {
      const aid = selectedAgent.trim();
      const sid = setId.trim();
      if (!aid || !sid) {
        setError('请选择 Agent 和用例集');
        return;
      }
      if (suiteBusy) {
        setError('标准冒烟流程进行中，请等待或中止后再单卷评测');
        return;
      }
      setBusyMode(live ? 'live' : 'dry');
      setReport(null);
      setReportSource(null);
      setError('');
      setMsg(live ? '正在正式评测（live，可能较久）…' : '正在预检（dry-run）…');
      try {
        const res = await agentEvalApi.runExam({
          agent_id: aid,
          set_id: sid,
          live,
        });
        if (res?.ok === false || res?.error) {
          setError(String(res.error || 'exam failed'));
          setMsg('');
          return;
        }
        {
          const r = res as {
            runtime_tier?: string;
            runtime_claim?: boolean;
            runtime_claim_reason?: string;
            message?: string;
            composite_score?: number;
            grade?: string;
            total_tasks?: number;
          };
          const displayAnn = r.runtime_tier
            ? {
                runtime_tier: r.runtime_tier,
                runtime_claim: Boolean(r.runtime_claim),
                runtime_claim_reason: String(r.runtime_claim_reason || ''),
              }
            : agentExamRuntimeAnn(live);
          const base =
            r.message ||
            `${live ? 'Live' : 'Dry-run'} · score=${r.composite_score} (${r.grade}) · tasks=${r.total_tasks}`;
          setMsg(`${base}\n${formatRuntimeAnn(displayAnn)}`);
        }
        if (res.attributable_report) {
          const resAny = res as Record<string, unknown>;
          const ar = {
            ...(res.attributable_report as Record<string, unknown>),
          };
          for (const k of [
            'run_id',
            'model',
            'agent_version',
            'code_revision',
            'runtime_tier',
            'runtime_claim',
            'runtime_claim_reason',
            'eval_time',
          ] as const) {
            if (ar[k] == null && resAny[k] != null) ar[k] = resAny[k];
          }
          setReport(ar as AttributableReport);
          setReportSource('session');
        } else {
          await loadReport(aid, sid, 'session');
        }
        onExamDone?.();
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        setMsg('');
      } finally {
        setBusyMode(null);
      }
    },
    [selectedAgent, setId, onExamDone, loadReport, suiteBusy],
  );

  const tabBtn = (id: ExamSubTab, label: string, testId: string) => (
    <button
      type="button"
      data-testid={testId}
      disabled={examLocked && subTab !== id}
      onClick={() => pickSubTab(id)}
      className={`px-3 py-1.5 rounded text-xs border ${
        subTab === id
          ? 'border-violet-500/70 bg-violet-950/40 text-violet-50'
          : 'border-gray-600 text-gray-300 hover:bg-gray-800/60'
      } disabled:opacity-50`}
    >
      {label}
      {id === 'suite' && suiteBusy ? ' · 进行中' : null}
      {id === 'single' && busy ? ' · 进行中' : null}
    </button>
  );

  return (
    <section
      className="rounded-lg border border-violet-700/40 bg-violet-950/20 p-4 space-y-3 text-sm"
      data-testid="eval-agent-exam-panel"
    >
      <div>
        <h2 className="font-medium text-violet-100">评测 Agent</h2>
        <p className="text-xs text-violet-100/70 mt-1">
          选一个 Agent，再选：只测一套题（单卷），或按固定顺序连跑多套（本地冒烟）。
          得分是工程参考，不是「准确率认证」。
        </p>
      </div>

      <label className="block space-y-1 max-w-xl">
        <span className="text-[11px] text-gray-500">Agent（两 Tab 共用）</span>
        <select
          data-testid="eval-exam-agent"
          className="w-full h-9 rounded border border-gray-600 bg-gray-950 px-2 text-xs text-gray-200"
          value={selectedAgent}
          disabled={examLocked}
          onChange={(e) => pickAgent(e.target.value)}
        >
          <option value="">选择 Agent…</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name || a.name || a.id} ({a.id})
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-wrap gap-2" data-testid="eval-exam-subtabs">
        {tabBtn('single', '单套题', 'eval-exam-tab-single')}
        {tabBtn('suite', '连跑冒烟', 'eval-exam-tab-suite')}
      </div>

      {/* Keep both panes mounted so suite matrix survives single↔suite tab switches. */}
      <div
        className={`space-y-3 ${subTab === 'single' ? '' : 'hidden'}`}
        data-testid="eval-exam-single-pane"
        aria-hidden={subTab !== 'single'}
      >
        {inspectHint ? (
          <p
            className="text-xs text-sky-100/90 rounded border border-sky-800/50 bg-sky-950/30 px-2 py-1.5"
            data-testid="eval-exam-inspect-hint"
          >
            {inspectHint}{' '}
            <button
              type="button"
              className="underline text-sky-200"
              onClick={() => setInspectHint('')}
            >
              关闭
            </button>
          </p>
        ) : null}
        <label className="block space-y-1 max-w-xl">
          <span className="text-[11px] text-gray-500">用例集</span>
          <select
            data-testid="eval-exam-set"
            className="w-full h-9 rounded border border-gray-600 bg-gray-950 px-2 text-xs text-gray-200"
            value={setId}
            disabled={examLocked}
            onChange={(e) => pickSet(e.target.value)}
          >
            {sets.length === 0 ? <option value="">暂无用例集</option> : null}
            {sets.map((s) => (
              <option key={s.set_id} value={s.set_id}>
                {s.set_id} · {s.tasks ?? '?'}题 · {s.description || s.category || ''}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="eval-exam-dry"
            disabled={examLocked || !selectedAgent || !setId}
            onClick={() => void run(false)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-xs text-gray-200 hover:bg-gray-800 disabled:opacity-50"
          >
            {busyMode === 'dry' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            预检（不真正跑）
          </button>
          <button
            type="button"
            data-testid="eval-exam-live"
            disabled={examLocked || !selectedAgent || !setId}
            onClick={() => void run(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-violet-500/70 text-violet-100 hover:bg-violet-950/50 disabled:opacity-50"
          >
            {busyMode === 'live' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            正式评测
          </button>
          <button
            type="button"
            data-testid="eval-exam-load-stored"
            disabled={examLocked || !selectedAgent || !setId}
            onClick={() => void loadReport(selectedAgent, setId, 'stored')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-700 text-xs text-gray-400 hover:bg-gray-900 disabled:opacity-50"
            title="查看这套题最近一次保存的结果"
          >
            查看上次结果
          </button>
        </div>

        {error ? <p className="text-xs text-red-300">{error}</p> : null}
        {msg ? (
          <p
            className="text-xs text-violet-100/90 whitespace-pre-wrap"
            data-testid="eval-exam-msg"
          >
            {msg}
          </p>
        ) : null}

        {!report && !busy ? (
          <p className="text-xs text-gray-500" data-testid="eval-exam-report-empty">
            还没有结果。点「正式评测」开始，或点「查看上次结果」看历史。
          </p>
        ) : null}

        {singleFullReport ? <EvalFullReportPanel report={singleFullReport} /> : null}

        <EvalAttributableReportCard
          report={report}
          source={reportSource}
          title={
            setId
              ? reportSource === 'stored'
                ? `上次结果 · ${setId}`
                : `本次结果 · ${setId}`
              : '评测结果说明'
          }
        />
      </div>

      <div
        className={subTab === 'suite' ? '' : 'hidden'}
        data-testid="eval-exam-suite-pane"
        aria-hidden={subTab !== 'suite'}
      >
        {busy ? (
          <p className="text-xs text-amber-200/90 mb-2">
            单卷评测进行中，冒烟已锁定；结束后可再开跑。
          </p>
        ) : null}
        <EvalExamSuitePanel
          agentId={selectedAgent}
          disabled={busy}
          onBusyChange={setSuiteBusy}
          onPaperDone={(sid) => {
            // Local focus only — do not notify parent (avoids history refetch every paper).
            setSetId(sid);
          }}
          onSuiteDone={(lastSetId) => {
            if (lastSetId) {
              setSetId(lastSetId);
              onSetChange?.(lastSetId);
            }
            onExamDone?.();
          }}
          onInspectDim={inspectFromSuite}
        />
      </div>
    </section>
  );
}
