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
  failures?: unknown[];
  run_ids?: string[];
  error?: string;
};

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
          accuracy_claim 恒不展示为真 · local store / proxy 只读
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
            {items.map((r, i) => (
              <li key={r.id || i} className="py-2 flex justify-between gap-3 items-start">
                <button
                  type="button"
                  className="text-left text-blue-300 hover:underline truncate"
                  onClick={() => void fetchDetail(String(r.id || ''))}
                >
                  {r.id || `report-${i}`}
                </button>
                <span className="text-gray-500 shrink-0 text-xs">
                  {r.created_at || '—'} · metrics[{metricsHint(r.metrics)}]
                </span>
              </li>
            ))}
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
            <p
              className={`text-xs ${
                compareResult.comparable ? 'text-emerald-300' : 'text-amber-300'
              }`}
            >
              {compareResult.comparable
                ? `comparable · score_delta=${String(compareResult.score_delta ?? '—')}`
                : `不可直接比较 · ${String(compareResult.incomparable_reason || '—')}`}
            </p>
            <pre
              className="text-xs bg-gray-950/80 border border-gray-800 rounded p-3 overflow-auto max-h-64 text-gray-300"
              data-testid="eval-compare-result"
            >
              {JSON.stringify(compareResult, null, 2)}
            </pre>
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
