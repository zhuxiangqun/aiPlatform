/**
 * EVAL_V1 /eval local preview — human-readable G2a summary.
 * Honesty: engineering calibration only — never claim accuracy / κ / external gate.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from 'lucide-react';
import { apiClient } from '../../services';

type G2aStatus = {
  ok?: boolean;
  tenant_id?: string;
  set_id?: string;
  task_count?: number;
  labels_pending?: number;
  labels_adjudicated?: number;
  v0_lock_target?: number;
  v0_locked?: boolean;
  g2a_ready?: boolean;
  accuracy_claim?: boolean;
  kappa?: number | null;
  note?: string;
};

type GateRow = {
  id?: string;
  decision?: string;
  candidate?: string;
  created_at?: string;
  meta?: {
    report_id?: string;
    gate_claim?: boolean;
    accuracy_claim?: boolean;
    engineering_pass?: boolean;
    checks?: Record<string, boolean>;
    mode?: string;
  };
};

type GateReport = {
  id?: string;
  metrics?: {
    task_count?: number;
    pass_rate?: number;
    mean_score?: number;
    regression_detection_rate?: number;
    false_block_rate?: number;
    k_repeat_stdev_mean?: number;
    decision?: string;
    gate_claim?: boolean;
    accuracy_claim?: boolean;
    failure_taxonomy?: {
      counts?: Record<string, number>;
      samples?: Record<string, string[]>;
      total_failures?: number;
    };
    checks?: Record<string, boolean>;
  };
};

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

function pct(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${(Number(n) * 100).toFixed(0)}%`;
}

const CHECK_LABELS: Record<string, string> = {
  pass_rate_ok: '通过率达标',
  k_stdev_ok: '重复跑稳定',
  regression_detection_ok: '能抓住故意埋的回归',
  false_block_ok: '误拦不高',
};

const EvalPreview: React.FC = () => {
  const [status, setStatus] = useState<G2aStatus | null>(null);
  const [gate, setGate] = useState<GateRow | null>(null);
  const [report, setReport] = useState<GateReport | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const stRes = await apiClient.get<Envelope<G2aStatus>>(
        '/platform/apps/eval/store/g2a-status?tenant_id=eval-v1',
      );
      const st = unwrap(stRes);
      setStatus(st);

      const gatesRes = await apiClient.get<
        Envelope<{ items?: GateRow[]; total?: number } | GateRow[]>
      >('/platform/apps/eval/store/gates?tenant_id=eval-v1&limit=5');
      const gatesBody = unwrap(gatesRes) as { items?: GateRow[] } | GateRow[];
      const items = Array.isArray(gatesBody)
        ? gatesBody
        : gatesBody?.items || [];
      const latest = items[0] || null;
      setGate(latest);

      const reportId = latest?.meta?.report_id;
      if (reportId) {
        const rptRes = await apiClient.get<Envelope<GateReport>>(
          `/platform/apps/eval/store/reports/${encodeURIComponent(reportId)}?tenant_id=eval-v1`,
        );
        setReport(unwrap(rptRes));
      } else {
        setReport(null);
      }
    } catch (e: any) {
      setError(String(e?.message || e));
      setStatus(null);
      setGate(null);
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const m = report?.metrics;
  const checks = m?.checks || gate?.meta?.checks || {};
  const failSamples = useMemo(() => {
    const samples = m?.failure_taxonomy?.samples || {};
    const out: { kind: string; id: string }[] = [];
    for (const [kind, ids] of Object.entries(samples)) {
      for (const id of ids || []) out.push({ kind, id });
    }
    return out.slice(0, 8);
  }, [m]);

  const locked = Boolean(status?.v0_locked);
  const engPass = Boolean(
    m?.decision === 'pass' || gate?.meta?.engineering_pass || gate?.decision === 'pass',
  );
  const gateClaim = Boolean(m?.gate_claim ?? gate?.meta?.gate_claim);
  const verdictOk = locked && engPass;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6 text-gray-200">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-2xl font-semibold tracking-tight">评测中心 · Preview</h1>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-gray-600 text-sm hover:bg-gray-800"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <p className="text-sm text-gray-400">
          用人话看本地 G2a：测了什么、过没过、还有什么问题。不是准确率认证页。
        </p>
      </header>

      {error ? (
        <div className="rounded border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          加载失败：{error}
        </div>
      ) : null}

      {/* 1. Plain summary */}
      <section
        className={`rounded-lg border px-4 py-4 space-y-2 ${
          verdictOk
            ? 'border-green-700/50 bg-green-950/20'
            : 'border-yellow-700/50 bg-yellow-950/20'
        }`}
      >
        <div className="flex items-start gap-3">
          {verdictOk ? (
            <CheckCircle2 className="w-6 h-6 text-green-400 shrink-0 mt-0.5" />
          ) : (
            <XCircle className="w-6 h-6 text-yellow-400 shrink-0 mt-0.5" />
          )}
          <div className="space-y-2 text-sm">
            <div className="text-base font-medium">
              {loading && !status
                ? '加载中…'
                : verdictOk
                  ? '本地校准门禁：通过'
                  : '本地校准尚未就绪或未通过'}
            </div>
            <p className="text-gray-300 leading-relaxed">
              测的是：<strong>代码审查金标</strong>
              （模型报出的安全/质量问题，能不能对上人工标准答案）。
              不是测「整个产品好不好」，也不是生产上线审批。
            </p>
            <ul className="list-disc pl-5 text-gray-300 space-y-1">
              <li>
                金标题库：{status?.task_count ?? '—'} 条；已人工确认{' '}
                {status?.labels_adjudicated ?? '—'} / {status?.v0_lock_target ?? 30}
                {status?.labels_pending
                  ? `（另有 ${status.labels_pending} 条未审，不影响已锁 v0）`
                  : ''}
              </li>
              <li>
                v0 金标锁：{locked ? '已锁定' : '未锁定'}
                {gateClaim ? ' · 已拿本地 gate_claim' : ''}
              </li>
              <li>
                最近一次门禁抽样：{m?.task_count ?? '—'} 题 · 通过率{' '}
                {pct(m?.pass_rate)} · 结论{' '}
                {m?.decision || gate?.decision || '—'}
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* 2. Checklist */}
      <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <div className="text-sm font-medium">本地门禁检查（工程校准）</div>
        {Object.keys(checks).length === 0 ? (
          <p className="text-sm text-gray-500">还没有门禁报告。先跑 lock-v0 → gate-g2a。</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {Object.entries(checks).map(([k, ok]) => (
              <li key={k} className="flex items-center gap-2">
                {ok ? (
                  <CheckCircle2 className="w-4 h-4 text-green-400" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400" />
                )}
                <span>{CHECK_LABELS[k] || k}</span>
              </li>
            ))}
          </ul>
        )}
        {m ? (
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm pt-2 border-t border-gray-800">
            <div>
              <dt className="text-gray-500">通过率</dt>
              <dd>{pct(m.pass_rate)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">平均分</dt>
              <dd>{m.mean_score != null ? Number(m.mean_score).toFixed(2) : '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">回归检出</dt>
              <dd>{pct(m.regression_detection_rate)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">误拦率</dt>
              <dd>{pct(m.false_block_rate)}</dd>
            </div>
          </dl>
        ) : null}
      </section>

      {/* 3. Problems */}
      <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <div className="text-sm font-medium">有没有问题？</div>
        {(m?.failure_taxonomy?.total_failures || 0) === 0 && failSamples.length === 0 ? (
          <p className="text-sm text-gray-300">
            最近一次门禁抽样里，没有记入失败分类的题（或尚未跑门禁）。
            抽样通过率未必 100%，低于阈值才算门禁失败。
          </p>
        ) : (
          <>
            <p className="text-sm text-gray-300">
              门禁仍可通过，但抽样里有{' '}
              <strong>{m?.failure_taxonomy?.total_failures ?? failSamples.length}</strong>{' '}
              题未过阈值（常见：报不全 / 多报）。示例：
            </p>
            <ul className="text-sm space-y-1 font-mono text-gray-400">
              {failSamples.map((s) => (
                <li key={`${s.kind}-${s.id}`}>
                  {s.id}
                  <span className="text-gray-600"> · {s.kind}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {/* 4. Honesty — short */}
      <div
        className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 flex gap-3 items-start"
        role="note"
      >
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-sm text-amber-100/90 space-y-1">
          <div className="font-medium text-amber-200">请勿过度解读</div>
          <p>
            这是<strong>本机工程校准</strong>。不能据此说「评测准确率已达标」，也不能当预发 /
            生产授权。accuracy=
            {String(Boolean(status?.accuracy_claim))}；κ=null（单人复核）。
          </p>
        </div>
      </div>

      <section className="text-sm text-gray-400 space-y-2">
        <div className="font-medium text-gray-300">相关入口</div>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <Link className="text-blue-400 hover:underline" to="/diagnostics/eval">
              Agent 评估（旧页）
            </Link>
          </li>
          <li>
            <Link className="text-blue-400 hover:underline" to="/governance">
              Governance · code-review-gold
            </Link>
          </li>
          <li>
            <span className="text-gray-500">完整 E6 评测中心</span> — 未解冻
          </li>
        </ul>
      </section>
    </div>
  );
};

export default EvalPreview;
