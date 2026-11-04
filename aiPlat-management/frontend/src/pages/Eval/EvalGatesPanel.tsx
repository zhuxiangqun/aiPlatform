/**
 * UI-4 — Gates browser: list/detail + local calibrate-e4 / gate-e5 / gate-g2a.
 * Honesty: local gate_claim ≠ accuracy / external authorize.
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw, Play } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

function unwrapList<T>(res: unknown): T[] {
  const body = res as { data?: { items?: T[] }; items?: T[] } & T[];
  if (Array.isArray(body?.data?.items)) return body.data!.items!;
  if (Array.isArray(body?.items)) return body.items!;
  if (Array.isArray(body?.data)) return body.data as T[];
  if (Array.isArray(body)) return body;
  return [];
}

type GateRow = {
  id?: string;
  gate_id?: string;
  baseline?: string;
  candidate?: string;
  decision?: string;
  kind?: string;
  gate_claim?: boolean;
  accuracy_claim?: boolean;
  created_at?: string;
  thresholds?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  error?: string;
};

type Props = { tenantId?: string };

function gateId(g: GateRow): string {
  return String(g.id || g.gate_id || '');
}

function gateKind(g: GateRow): string {
  const meta = g.meta || {};
  return String(g.kind || meta.kind || meta.mode || g.decision || '—');
}

function gateClaim(g: GateRow): boolean {
  if (typeof g.gate_claim === 'boolean') return g.gate_claim;
  const meta = g.meta || {};
  return Boolean(meta.gate_claim);
}

function accuracyClaim(g: GateRow): boolean {
  if (typeof g.accuracy_claim === 'boolean') return g.accuracy_claim;
  const meta = g.meta || {};
  return Boolean(meta.accuracy_claim);
}

export default function EvalGatesPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [items, setItems] = useState<GateRow[]>([]);
  const [detail, setDetail] = useState<GateRow | null>(null);
  const [mode, setMode] = useState<'pr' | 'nightly' | 'release'>('pr');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get(
        `/platform/apps/eval/store/gates?tenant_id=${encodeURIComponent(tenantId)}&limit=50`,
      );
      setItems(unwrapList<GateRow>(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const fetchDetail = async (id: string) => {
    const gid = id.trim();
    if (!gid) return;
    setBusy(true);
    try {
      const res = await apiClient.get<Envelope<GateRow>>(
        `/platform/apps/eval/store/gates/${encodeURIComponent(gid)}?tenant_id=${encodeURIComponent(tenantId)}`,
      );
      setDetail(unwrap(res));
    } catch (e: unknown) {
      setDetail({ id: gid, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (path: string, body: Record<string, unknown>, label: string) => {
    setBusy(true);
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<Record<string, unknown>>>(path, {
        tenant_id: tenantId,
        ...body,
      });
      const d = unwrap(res) as { ok?: boolean; error?: string; gate_claim?: boolean; accuracy_claim?: boolean; id?: string };
      if (d && d.ok === false) {
        setMsg(`${label} 失败: ${d.error || 'unknown'}`);
      } else {
        setMsg(
          `${label} ok · id=${d.id || '—'} · gate_claim=${String(Boolean(d.gate_claim))} · accuracy_claim=${String(Boolean(d.accuracy_claim))}（local only）`,
        );
        await load();
        if (d.id) await fetchDetail(String(d.id));
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-sm" data-testid="eval-gates-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90">
        local <code>gate_claim</code> ≠ accuracy / staging authorize · κ 仍 null（G2b 前）
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">门禁结果（local）</h2>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <label className="text-xs text-gray-500">
            mode{' '}
            <select
              className="ml-1 px-2 py-1 rounded bg-gray-950 border border-gray-700 text-gray-200"
              value={mode}
              onChange={(e) => setMode(e.target.value as typeof mode)}
              data-testid="eval-gate-mode"
            >
              <option value="pr">pr</option>
              <option value="nightly">nightly</option>
              <option value="release">release</option>
            </select>
          </label>
          <button
            type="button"
            disabled={busy}
            data-testid="eval-gate-e5"
            onClick={() =>
              void runAction('/platform/apps/eval/store/gate-e5', { mode }, 'gate-e5')
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-blue-700/80 hover:bg-blue-600 disabled:opacity-50 text-white"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Run E5
          </button>
          <button
            type="button"
            disabled={busy}
            data-testid="eval-gate-g2a"
            onClick={() =>
              void runAction('/platform/apps/eval/store/gate-g2a', { mode }, 'gate-g2a')
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-violet-600/80 text-violet-100 hover:bg-violet-950/40 disabled:opacity-50"
          >
            Run G2a
          </button>
          <button
            type="button"
            disabled={busy}
            data-testid="eval-calibrate-e4"
            onClick={() =>
              void runAction('/platform/apps/eval/store/calibrate-e4', { k: 3 }, 'calibrate-e4')
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-gray-200 hover:bg-gray-800 disabled:opacity-50"
          >
            Calibrate E4
          </button>
        </div>

        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {msg ? (
          <p className="text-gray-300 font-mono text-xs whitespace-pre-wrap" data-testid="eval-gates-msg">
            {msg}
          </p>
        ) : null}

        {loading && items.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : items.length === 0 ? (
          <p className="text-gray-500">暂无 gate 记录。</p>
        ) : (
          <ul className="divide-y divide-gray-800" data-testid="eval-gates-list">
            {items.map((g, i) => {
              const id = gateId(g);
              return (
                <li key={id || i} className="py-2 grid grid-cols-2 sm:grid-cols-4 gap-2 items-center">
                  <button
                    type="button"
                    className="text-left truncate text-blue-300 hover:underline"
                    onClick={() => void fetchDetail(id)}
                  >
                    {id || `gate-${i}`}
                  </button>
                  <span className="text-gray-400 truncate">{gateKind(g)}</span>
                  <span>gate_claim={String(gateClaim(g))}</span>
                  <span className="text-amber-200/90">accuracy={String(accuracyClaim(g))}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {detail ? (
        <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
          <h3 className="font-medium">Gate detail</h3>
          <pre
            className="text-xs bg-gray-950/80 border border-gray-800 rounded p-3 overflow-auto max-h-64 text-gray-300"
            data-testid="eval-gate-detail"
          >
            {JSON.stringify(detail, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
