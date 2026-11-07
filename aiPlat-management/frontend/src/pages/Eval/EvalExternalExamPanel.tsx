/**
 * External pull-mode exam: register/select http_chat_pull target → dry-run / live.
 * Results persist as ext:{target_id} under the current named workspace.
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { agentEvalApi } from '../../services';
import EvalAttributableReportCard, {
  type AttributableReport,
} from './EvalAttributableReportCard';
import { formatRuntimeAnn } from './examRuntimeTier';

type ExamSet = {
  set_id: string;
  category?: string;
  description?: string;
  tasks?: number;
};

type ExtTarget = {
  target_id: string;
  label?: string;
  base_url?: string;
  path?: string;
  agent_id?: string;
};

type Props = {
  /** When exam finishes, parent can refresh history for ext:{id}. */
  onAgentChange?: (extAgentId: string) => void;
  onSetChange?: (setId: string) => void;
  onExamDone?: () => void;
};

export default function EvalExternalExamPanel({
  onAgentChange,
  onSetChange,
  onExamDone,
}: Props) {
  const [targets, setTargets] = useState<ExtTarget[]>([]);
  const [sets, setSets] = useState<ExamSet[]>([]);
  const [targetId, setTargetId] = useState('');
  const [setId, setSetId] = useState('default/normal');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [report, setReport] = useState<AttributableReport | null>(null);

  const [newId, setNewId] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newBase, setNewBase] = useState('http://127.0.0.1:9999');
  const [newPath, setNewPath] = useState('/v1/chat');

  const refreshTargets = useCallback(async () => {
    try {
      const res = await agentEvalApi.listExternalTargets();
      setTargets(Array.isArray(res?.items) ? (res.items as ExtTarget[]) : []);
    } catch {
      setTargets([]);
    }
  }, []);

  useEffect(() => {
    void refreshTargets();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once
  }, []);

  const extAgentId = targetId.trim() ? `ext:${targetId.trim()}` : '';

  const loadReport = useCallback(async (aid: string, sid: string) => {
    if (!aid.trim()) {
      setReport(null);
      return;
    }
    try {
      const res = await agentEvalApi.attributableReport(aid.trim(), 5, sid.trim());
      setReport(res as AttributableReport);
    } catch {
      setReport(null);
    }
  }, []);

  useEffect(() => {
    if (extAgentId) {
      onAgentChange?.(extAgentId);
      void loadReport(extAgentId, setId);
    }
  }, [extAgentId, setId, loadReport, onAgentChange]);

  const pickTarget = (id: string) => {
    setTargetId(id);
    if (id.trim()) onAgentChange?.(`ext:${id.trim()}`);
  };

  const pickSet = (id: string) => {
    setSetId(id);
    onSetChange?.(id);
  };

  const register = useCallback(async () => {
    const tid = newId.trim();
    const base = newBase.trim();
    if (!tid || !base) {
      setError('登记需要 target_id 与 base_url');
      return;
    }
    setBusy(true);
    setError('');
    setMsg('正在登记外部目标（含 SSRF 校验）…');
    try {
      const res = await agentEvalApi.upsertExternalTarget({
        target_id: tid,
        label: newLabel.trim() || tid,
        base_url: base,
        path: newPath.trim() || '/v1/chat',
      });
      if (res?.ok === false || res?.error) {
        setError(String(res.error || 'register failed'));
        setMsg('');
        return;
      }
      setMsg(`已登记 ${tid}`);
      setTargetId(tid);
      onAgentChange?.(`ext:${tid}`);
      await refreshTargets();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setMsg('');
    } finally {
      setBusy(false);
    }
  }, [newId, newLabel, newBase, newPath, onAgentChange, refreshTargets]);

  const run = useCallback(
    async (live: boolean) => {
      const tid = targetId.trim();
      const sid = setId.trim();
      if (!tid || !sid) {
        setError('请选择外部目标与用例集');
        return;
      }
      setBusy(true);
      setError('');
      setMsg(live ? '正在外部 live 拉模式评测…' : '正在外部预检…');
      try {
        const res = await agentEvalApi.runExternalExam({
          target_id: tid,
          set_id: sid,
          live,
        });
        if (res?.ok === false || res?.error) {
          setError(String(res.error || 'external exam failed'));
          setMsg('');
          return;
        }
        {
          const r = res as {
            message?: string;
            agent_id?: string;
            composite_score?: number;
            grade?: string;
            runtime_tier?: string;
            runtime_claim?: boolean;
            runtime_claim_reason?: string;
          };
          const base =
            r.message ||
            `${live ? 'Live' : 'Dry-run'} · ${r.agent_id} · score=${r.composite_score} (${r.grade})`;
          const rtLine = r.runtime_tier
            ? `\n${formatRuntimeAnn({
                runtime_tier: r.runtime_tier,
                runtime_claim: r.runtime_claim,
                runtime_claim_reason: r.runtime_claim_reason,
              })}`
            : '\nruntime_tier=external_pull';
          setMsg(`${base}${rtLine}`);
        }
        if (res.attributable_report) {
          setReport(res.attributable_report as AttributableReport);
        } else if (res.agent_id) {
          await loadReport(String(res.agent_id), sid);
        }
        if (res.agent_id) onAgentChange?.(String(res.agent_id));
        onExamDone?.();
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        setMsg('');
      } finally {
        setBusy(false);
      }
    },
    [targetId, setId, onExamDone, loadReport, onAgentChange],
  );

  return (
    <section
      className="rounded-lg border border-sky-700/40 bg-sky-950/20 p-4 space-y-3 text-sm"
      data-testid="eval-external-exam-panel"
    >
      <div>
        <h2 className="font-medium text-sky-100">外部目标（拉模式）</h2>
        <p className="text-xs text-sky-100/80 mt-1" data-testid="eval-external-honesty">
          外部拉模式 · 对话文本；若试卷有 expected_tools 且对方返回 tool_calls，按 IN_ORDER
          计工具序（≠ 副作用充分 / ≠ 准确率）。结果落在当前命名工作区，agent_id 为{' '}
          <code className="text-[11px]">ext:&#123;target_id&#125;</code>。
          归档 <code className="text-[11px]">runtime_tier=external_pull</code>
          （≠ workspace_execute · ≠ pi）。
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <label className="block space-y-1">
          <span className="text-[11px] text-gray-500">已登记目标</span>
          <select
            data-testid="eval-external-target"
            className="w-full h-9 rounded border border-gray-600 bg-gray-950 px-2 text-xs text-gray-200"
            value={targetId}
            onChange={(e) => pickTarget(e.target.value)}
          >
            <option value="">选择外部目标…</option>
            {targets.map((t) => (
              <option key={t.target_id} value={t.target_id}>
                {t.label || t.target_id} ({t.agent_id || `ext:${t.target_id}`})
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] text-gray-500">用例集</span>
          <select
            data-testid="eval-external-set"
            className="w-full h-9 rounded border border-gray-600 bg-gray-950 px-2 text-xs text-gray-200"
            value={setId}
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
      </div>

      <details className="rounded border border-sky-800/50 bg-black/20 p-2">
        <summary className="cursor-pointer text-xs text-sky-100/90">登记新目标</summary>
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input
            data-testid="eval-external-new-id"
            className="h-8 rounded border border-gray-600 bg-gray-950 px-2 text-xs"
            placeholder="target_id"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
          />
          <input
            className="h-8 rounded border border-gray-600 bg-gray-950 px-2 text-xs"
            placeholder="label"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
          />
          <input
            data-testid="eval-external-new-base"
            className="h-8 rounded border border-gray-600 bg-gray-950 px-2 text-xs sm:col-span-2"
            placeholder="base_url (http/https)"
            value={newBase}
            onChange={(e) => setNewBase(e.target.value)}
          />
          <input
            className="h-8 rounded border border-gray-600 bg-gray-950 px-2 text-xs"
            placeholder="path"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
          />
          <button
            type="button"
            data-testid="eval-external-register"
            disabled={busy}
            onClick={() => void register()}
            className="h-8 rounded border border-sky-600/70 text-xs text-sky-100 hover:bg-sky-950/40 disabled:opacity-50"
          >
            登记（需允许私网时设 AIPLAT_EXTERNAL_EVAL_ALLOW_PRIVATE=1）
          </button>
        </div>
      </details>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="eval-external-dry"
          disabled={busy || !targetId || !setId}
          onClick={() => void run(false)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-xs text-gray-200 hover:bg-gray-800 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          预检
        </button>
        <button
          type="button"
          data-testid="eval-external-live"
          disabled={busy || !targetId || !setId}
          onClick={() => void run(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-sky-500/70 text-sky-100 hover:bg-sky-950/50 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          正式评测（live 拉）
        </button>
      </div>

      {error ? <p className="text-xs text-red-300">{error}</p> : null}
      {msg ? (
        <p className="text-xs font-mono text-sky-100/90 whitespace-pre-wrap" data-testid="eval-external-msg">
          {msg}
        </p>
      ) : null}

      <EvalAttributableReportCard
        report={report}
        title={setId ? `外部可归因 · ${setId}` : '外部可归因报告'}
      />
    </section>
  );
}
