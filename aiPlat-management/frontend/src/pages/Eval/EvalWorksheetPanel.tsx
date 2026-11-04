/**
 * Human worksheet pack panel — generate/list/download; never claims accuracy.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type PackRow = {
  stamp?: string;
  files?: string[];
  g2b_task_n?: number | null;
  preference_pair_n?: number | null;
};

type PackStatus = {
  ok?: boolean;
  packs?: PackRow[];
  latest_stamp?: string | null;
  accuracy_claim?: boolean;
  note?: string;
  runbook?: string;
  pack_root?: string;
};

type Props = { tenantId?: string };

export default function EvalWorksheetPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<PackStatus | null>(null);
  const [preview, setPreview] = useState<{ stamp: string; filename: string; content: string; audience?: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<PackStatus>>(
        `/platform/apps/eval/store/worksheet-pack-status?tenant_id=${encodeURIComponent(tenantId)}&limit=20`,
      );
      setStatus(unwrap(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = async () => {
    setGenerating(true);
    setError('');
    try {
      await apiClient.post(`/platform/apps/eval/store/worksheet-pack-generate`, {
        tenant_id: tenantId,
      });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  };

  const openFile = async (stamp: string, filename: string) => {
    setError('');
    try {
      const res = await apiClient.get<
        Envelope<{ ok?: boolean; content?: string; audience?: string; error?: string }>
      >(
        `/platform/apps/eval/store/worksheet-pack-file?tenant_id=${encodeURIComponent(tenantId)}&stamp=${encodeURIComponent(stamp)}&filename=${encodeURIComponent(filename)}`,
      );
      const body = unwrap(res);
      if (!body?.ok) {
        setError(body?.error || 'load failed');
        return;
      }
      setPreview({
        stamp,
        filename,
        content: String(body.content || ''),
        audience: body.audience,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const downloadPreview = () => {
    if (!preview) return;
    const blob = new Blob([preview.content], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = preview.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const packs = status?.packs || [];

  return (
    <div className="space-y-4 text-sm" data-testid="eval-worksheet-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Worksheet 诚实约束</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>只把 <code>*_annotator_*.json</code> 发给两名真人（盲标）</li>
          <li>
            <code>g2b_facilitator.json</code> / <code>model_outputs.json</code> 含 gold 提示 · 勿外发
          </li>
          <li>
            <code>accuracy_claim</code>={String(Boolean(status?.accuracy_claim))} · 空白包 ≠ κ / accuracy
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Human worksheet packs</h2>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void generate()}
              disabled={generating}
              className="px-2.5 py-1 rounded border border-blue-700/60 text-xs text-blue-100 hover:bg-blue-950/40 disabled:opacity-50"
            >
              {generating ? '生成中…' : '生成新包'}
            </button>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>
        </div>
        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {status?.note ? <p className="text-xs text-gray-400">{status.note}</p> : null}
        {status?.pack_root ? (
          <p className="text-xs font-mono text-blue-200/80 break-all">{status.pack_root}</p>
        ) : null}

        {loading && !status ? (
          <p className="text-gray-500">加载中…</p>
        ) : packs.length === 0 ? (
          <p className="text-gray-500 text-xs">尚无 pack — 点击「生成新包」。</p>
        ) : (
          <ul className="space-y-3">
            {packs.map((p) => (
              <li key={p.stamp} className="rounded border border-gray-700/80 p-3 space-y-2">
                <div className="flex flex-wrap gap-3 text-xs">
                  <span className="font-mono text-gray-100">{p.stamp}</span>
                  <span className="text-gray-500">
                    g2b={p.g2b_task_n ?? '—'} · pref={p.preference_pair_n ?? '—'}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(p.files || []).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => void openFile(String(p.stamp), f)}
                      className={`px-2 py-0.5 rounded border text-[11px] ${
                        f.includes('annotator')
                          ? 'border-green-800/60 text-green-200/90'
                          : f.includes('facilitator') || f === 'model_outputs.json'
                            ? 'border-amber-800/60 text-amber-200/90'
                            : 'border-gray-600 text-gray-300'
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {preview ? (
        <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h3 className="font-medium text-sm font-mono">
              {preview.stamp}/{preview.filename}
              {preview.audience ? (
                <span className="ml-2 text-xs text-gray-400">({preview.audience})</span>
              ) : null}
            </h3>
            <button
              type="button"
              onClick={downloadPreview}
              className="px-2 py-1 rounded border border-gray-600 text-xs text-gray-200 hover:bg-gray-800"
            >
              下载
            </button>
          </div>
          <pre className="max-h-80 overflow-auto text-[11px] text-gray-300 whitespace-pre-wrap break-all">
            {preview.content.slice(0, 12000)}
            {preview.content.length > 12000 ? '\n…(truncated)' : ''}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
