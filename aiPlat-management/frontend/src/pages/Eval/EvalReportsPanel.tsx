/**
 * UI-2 — Reports browser: store list + id lookup + gold JSONL strip.
 * Honesty: never surface accuracy_claim as true from this panel.
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type StoreReport = {
  id?: string;
  created_at?: string;
  metrics?: Record<string, unknown>;
  scoring?: Record<string, unknown>;
  failures?: unknown[];
  run_ids?: string[];
  error?: string;
};

/** Mirror package extract_composite_version — list badge only. */
function compositeVersionOf(r: StoreReport): string | null {
  const fromBlock = (block: unknown): string | null => {
    if (!block || typeof block !== 'object') return null;
    const policy = (block as { policy?: { composite_version?: unknown } }).policy;
    const ver = policy?.composite_version;
    return typeof ver === 'string' && ver.trim() ? ver.trim() : null;
  };
  const scoring = r.scoring;
  if (scoring && typeof scoring === 'object') {
    const v = fromBlock((scoring as { composite?: unknown }).composite);
    if (v) return v;
  }
  const metrics = r.metrics;
  if (metrics && typeof metrics === 'object') {
    const mScoring = (metrics as { scoring?: { composite?: unknown } }).scoring;
    const v1 = fromBlock(mScoring?.composite);
    if (v1) return v1;
    const v2 = fromBlock((metrics as { composite?: unknown }).composite);
    if (v2) return v2;
  }
  return fromBlock(r as { composite?: unknown });
}

function reportMetaHint(r: StoreReport): string {
  const metrics = r.metrics;
  const meta =
    metrics && typeof metrics === 'object'
      ? (metrics as { meta?: Record<string, unknown> }).meta
      : undefined;
  if (!meta || typeof meta !== 'object') return '';
  const bits: string[] = [];
  for (const key of ['runner_id', 'judge_id', 'dataset_version', 'runner_version'] as const) {
    const v = meta[key];
    if (typeof v === 'string' && v.trim()) bits.push(`${key}=${v.trim()}`);
  }
  return bits.slice(0, 3).join(' ');
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function deltaEntries(deltas: unknown): Array<[string, string]> {
  const rec = asRecord(deltas);
  if (!rec) return [];
  return Object.keys(rec)
    .sort()
    .map((k) => {
      const raw = rec[k];
      const text = raw === null || raw === undefined ? '—' : String(raw);
      return [k, text] as [string, string];
    });
}

function CompareSummary({ result }: { result: Record<string, unknown> }) {
  const comparable = Boolean(result.comparable);
  const baseline = asRecord(result.baseline);
  const candidate = asRecord(result.candidate);
  const failures = asRecord(result.failures);
  const familyRows = deltaEntries(result.family_deltas);
  const metricRows = deltaEntries(result.metric_deltas).slice(0, 8);
  const added = Array.isArray(failures?.added) ? (failures!.added as unknown[]) : [];
  const removed = Array.isArray(failures?.removed) ? (failures!.removed as unknown[]) : [];

  return (
    <div className="space-y-3 text-xs" data-testid="eval-compare-summary">
      <p className={comparable ? 'text-emerald-300' : 'text-amber-300'}>
        {comparable
          ? `comparable · score_delta=${String(result.score_delta ?? '—')}`
          : `不可直接比较 · ${String(result.incomparable_reason || '—')}`}
        {' · '}
        <span className="text-gray-500">accuracy_claim=false</span>
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-gray-300">
        <div className="rounded border border-gray-800 bg-gray-950/60 p-2">
          <div className="text-gray-500 mb-1">baseline</div>
          <div>id={String(baseline?.id ?? '—')}</div>
          <div>composite={String(baseline?.composite_version ?? '—')}</div>
          <div>score={String(baseline?.score ?? '—')}</div>
        </div>
        <div className="rounded border border-gray-800 bg-gray-950/60 p-2">
          <div className="text-gray-500 mb-1">candidate</div>
          <div>id={String(candidate?.id ?? '—')}</div>
          <div>composite={String(candidate?.composite_version ?? '—')}</div>
          <div>score={String(candidate?.score ?? '—')}</div>
        </div>
      </div>
      {comparable && familyRows.length > 0 ? (
        <div>
          <div className="text-gray-500 mb-1">family_deltas</div>
          <ul className="grid grid-cols-2 gap-1 text-gray-300">
            {familyRows.map(([k, v]) => (
              <li key={k}>
                {k}: {v}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {comparable && metricRows.length > 0 ? (
        <div>
          <div className="text-gray-500 mb-1">metric_deltas（最多 8）</div>
          <ul className="grid grid-cols-2 gap-1 text-gray-300">
            {metricRows.map(([k, v]) => (
              <li key={k}>
                {k}: {v}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {failures ? (
        <div className="text-gray-300">
          <div className="text-gray-500 mb-1">failures</div>
          <div>
            baseline={String(failures.baseline_count ?? '—')} · candidate=
            {String(failures.candidate_count ?? '—')} · shared=
            {String(failures.shared_count ?? '—')}
          </div>
          {added.length ? (
            <div className="truncate">added: {added.slice(0, 5).map(String).join(', ')}</div>
          ) : null}
          {removed.length ? (
            <div className="truncate">removed: {removed.slice(0, 5).map(String).join(', ')}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

type GoldReport = {
  profile?: string;
  case_count?: number;
  precision?: number | null;
  recall?: number | null;
  p0_recall?: number | null;
  created_at?: string;
  report_path?: string;
};

type Props = { tenantId?: string };

export default function EvalReportsPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [items, setItems] = useState<StoreReport[]>([]);
  const [goldItems, setGoldItems] = useState<GoldReport[]>([]);
  const [lookupId, setLookupId] = useState('');
  const [detail, setDetail] = useState<StoreReport | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [baselineId, setBaselineId] = useState('');
  const [candidateId, setCandidateId] = useState('');
  const [compareBusy, setCompareBusy] = useState(false);
  const [compareResult, setCompareResult] = useState<Record<string, unknown> | null>(null);
  const [compareError, setCompareError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [storeRes, goldRes] = await Promise.all([
        apiClient.get<Envelope<{ items?: StoreReport[]; total?: number }>>(
          `/platform/apps/eval/store/reports?tenant_id=${encodeURIComponent(tenantId)}&limit=30`,
        ),
        apiClient
          .get<Envelope<{ items?: GoldReport[]; total?: number }>>(
            `/platform/apps/eval/code-review-gold/reports?tenant_id=${encodeURIComponent(tenantId)}&limit=5`,
          )
          .catch(() => null),
      ]);
      const store = unwrap(storeRes) as { items?: StoreReport[] };
      setItems(Array.isArray(store?.items) ? store.items : []);
      if (goldRes) {
        const gold = unwrap(goldRes) as { items?: GoldReport[] };
        setGoldItems(Array.isArray(gold?.items) ? gold.items : []);
      } else {
        setGoldItems([]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const fetchDetail = async (reportId: string) => {
    const id = reportId.trim();
    if (!id) return;
    setDetailBusy(true);
    setDetail(null);
    try {
      const res = await apiClient.get<Envelope<StoreReport>>(
        `/platform/apps/eval/store/reports/${encodeURIComponent(id)}?tenant_id=${encodeURIComponent(tenantId)}`,
      );
      const row = unwrap(res) as StoreReport;
      setDetail(row);
      setLookupId(id);
    } catch (e: unknown) {
      setDetail({ id, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setDetailBusy(false);
    }
  };

  const metricsHint = (m?: Record<string, unknown>) => {
    if (!m || typeof m !== 'object') return '—';
    const keys = Object.keys(m).slice(0, 4);
    return keys.length ? keys.join(', ') : '{}';
  };

  const runCompare = async () => {
    const bid = baselineId.trim();
    const cid = candidateId.trim();
    if (!bid || !cid) return;
    setCompareBusy(true);
    setCompareError('');
    setCompareResult(null);
    try {
      const res = await apiClient.post<Envelope<Record<string, unknown>>>(
        `/platform/apps/eval/store/reports/compare?tenant_id=${encodeURIComponent(tenantId)}`,
        { baseline_id: bid, candidate_id: cid },
      );
      setCompareResult(unwrap(res) as Record<string, unknown>);
    } catch (e: unknown) {
      setCompareError(e instanceof Error ? e.message : String(e));
    } finally {
      setCompareBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-sm" data-testid="eval-reports-panel">
      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Store 报告</h2>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <p className="text-xs text-gray-500">
          accuracy_claim 恒不展示为真 · 趋势对比仅同 composite_version · local store / proxy 只读
        </p>
        {error ? (
          <p className="text-red-300 text-xs">加载失败: {error}</p>
        ) : null}
        {loading && items.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : items.length === 0 ? (
          <p className="text-gray-500">暂无 store 报告（可按 id 拉取）。</p>
        ) : (
          <ul className="divide-y divide-gray-800">
            {items.map((r, i) => {
              const cv = compositeVersionOf(r);
              const metaHint = reportMetaHint(r);
              return (
              <li key={r.id || i} className="py-2 flex justify-between gap-3 items-start">
                <button
                  type="button"
                  className="text-left text-blue-300 hover:underline truncate"
                  onClick={() => void fetchDetail(String(r.id || ''))}
                >
                  {r.id || `report-${i}`}
                </button>
                <span className="text-gray-500 shrink-0 text-xs text-right max-w-[60%]">
                  <span
                    className={cv ? 'text-emerald-400/90' : 'text-amber-400/80'}
                    data-testid="eval-report-composite-version"
                  >
                    {cv ? `composite ${cv}` : 'no composite_version'}
                  </span>
                  {metaHint ? (
                    <>
                      {' · '}
                      <span data-testid="eval-report-meta">{metaHint}</span>
                    </>
                  ) : null}
                  {' · '}
                  {r.created_at || '—'} · metrics[{metricsHint(r.metrics)}]
                </span>
              </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3" data-testid="eval-report-compare">
        <h3 className="font-medium">报告对比（P1b）</h3>
        <p className="text-xs text-gray-500">
          仅当两侧 <code className="text-gray-400">policy.composite_version</code> 相同才
          comparable；跨版本标「不可直接比较」。accuracy_claim 恒 false。
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            className="flex-1 min-w-[10rem] px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
            value={baselineId}
            onChange={(e) => setBaselineId(e.target.value)}
            placeholder="baseline rpt_…"
            data-testid="eval-compare-baseline"
          />
          <input
            className="flex-1 min-w-[10rem] px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
            value={candidateId}
            onChange={(e) => setCandidateId(e.target.value)}
            placeholder="candidate rpt_…"
            data-testid="eval-compare-candidate"
          />
          <button
            type="button"
            data-testid="eval-compare-run"
            disabled={compareBusy || !baselineId.trim() || !candidateId.trim()}
            onClick={() => void runCompare()}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-emerald-800/80 hover:bg-emerald-700 disabled:opacity-50 text-white"
          >
            {compareBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            对比
          </button>
        </div>
        {items.length >= 2 ? (
          <p className="text-xs text-gray-500">
            快捷填入最近两条：
            <button
              type="button"
              className="ml-2 text-blue-300 hover:underline"
              onClick={() => {
                setBaselineId(String(items[1]?.id || ''));
                setCandidateId(String(items[0]?.id || ''));
              }}
            >
              用列表第 2 / 第 1 条
            </button>
          </p>
        ) : null}
        {compareError ? <p className="text-red-300 text-xs">{compareError}</p> : null}
        {compareResult ? (
          <div className="space-y-2">
            <CompareSummary result={compareResult} />
            <details className="text-xs text-gray-500">
              <summary className="cursor-pointer hover:text-gray-300">原始 JSON</summary>
              <pre
                className="mt-2 text-xs bg-gray-950/80 border border-gray-800 rounded p-3 overflow-auto max-h-64 text-gray-300"
                data-testid="eval-compare-result"
              >
                {JSON.stringify(compareResult, null, 2)}
              </pre>
            </details>
          </div>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <h3 className="font-medium">按 report_id 拉取</h3>
        <div className="flex flex-wrap gap-2">
          <input
            className="flex-1 min-w-[12rem] px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            placeholder="rpt_…"
            data-testid="eval-report-lookup-id"
          />
          <button
            type="button"
            data-testid="eval-report-lookup"
            disabled={detailBusy || !lookupId.trim()}
            onClick={() => void fetchDetail(lookupId)}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-blue-700/80 hover:bg-blue-600 disabled:opacity-50 text-white"
          >
            {detailBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            拉取
          </button>
        </div>
        {detail ? (
          <pre
            className="text-xs bg-gray-950/80 border border-gray-800 rounded p-3 overflow-auto max-h-64 text-gray-300"
            data-testid="eval-report-detail"
          >
            {JSON.stringify(detail, null, 2)}
          </pre>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
        <h3 className="font-medium">Code-review gold JSONL（最近）</h3>
        {goldItems.length === 0 ? (
          <p className="text-gray-500">无 gold 报告（先 Run match-only）。</p>
        ) : (
          <ul className="divide-y divide-gray-800">
            {goldItems.map((g, i) => (
              <li key={i} className="py-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-300">
                <span>{g.profile || '—'}</span>
                <span>cases={g.case_count ?? '—'}</span>
                <span>
                  P={g.precision ?? '—'} R={g.recall ?? '—'}
                </span>
                <span className="truncate text-gray-500">{g.created_at || g.report_path || '—'}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
