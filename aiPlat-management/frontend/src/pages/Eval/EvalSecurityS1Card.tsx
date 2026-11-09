/**
 * SEC-P2a read-only S1 pack + OOS/untested family disclosure.
 * No one-click certification; accuracy_claim stays false.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type P2aStatus = {
  ok?: boolean;
  slice?: string;
  accuracy_claim?: boolean;
  security_certification?: boolean;
  s1_pack?: {
    n_cases?: number;
    by_category?: Record<string, number>;
    live_skill_tools?: boolean;
  };
  s1_aggregate?: {
    prod_model?: string;
    asr?: number;
    leak_rate?: number;
    false_refusal_rate?: number;
    llm_ok_n?: number;
    gate_ok?: boolean;
  } | null;
  disclosure?: {
    untested_threat_families?: string[];
    below_min_n_families?: string[];
    deferred_threat_families?: string[];
    oos_ids?: string[];
    s1_annotated_threat_families?: string[];
    annotation_only?: boolean;
  };
  honesty?: string;
};

function fmtRate(v: number | undefined): string {
  if (v === undefined || v === null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

export default function EvalSecurityS1Card() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<P2aStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<P2aStatus>>(
        '/platform/apps/eval/store/security-sec-p2a-status',
      );
      setStatus(unwrap(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const disc = status?.disclosure;
  const agg = status?.s1_aggregate;

  return (
    <div
      className="rounded-lg border border-amber-800/50 bg-amber-950/20 p-3 space-y-2 text-xs"
      data-testid="eval-security-s1-card"
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="font-medium text-amber-100">S1 安全披露（只读 · SEC-P2a）</h3>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-600 text-gray-300 hover:bg-gray-800"
          data-testid="eval-security-s1-refresh"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>
      <p className="text-amber-100/70">
        文本层攻击包 + 未测/OOS 自动清单 · 无一键认证 · accuracy_claim=false
      </p>
      {error ? <p className="text-red-300">{error}</p> : null}
      {loading && !status ? (
        <p className="text-gray-500">加载中…</p>
      ) : status ? (
        <>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <dt className="text-gray-500">S1 cases</dt>
              <dd data-testid="eval-s1-n-cases">{status.s1_pack?.n_cases ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">live tools</dt>
              <dd>{status.s1_pack?.live_skill_tools ? 'yes' : 'no'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">accuracy_claim</dt>
              <dd data-testid="eval-s1-accuracy-claim">
                {String(status.accuracy_claim ?? false)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">certification</dt>
              <dd>{String(status.security_certification ?? false)}</dd>
            </div>
          </dl>
          {agg ? (
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 border-t border-amber-900/40 pt-2">
              <div>
                <dt className="text-gray-500">model</dt>
                <dd>{agg.prod_model ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-gray-500">ASR</dt>
                <dd data-testid="eval-s1-asr">{fmtRate(agg.asr)}</dd>
              </div>
              <div>
                <dt className="text-gray-500">leak</dt>
                <dd>{fmtRate(agg.leak_rate)}</dd>
              </div>
              <div>
                <dt className="text-gray-500">false_refusal</dt>
                <dd>{fmtRate(agg.false_refusal_rate)}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-gray-500">无本地 S1 aggregate 证据（仅题包元数据）</p>
          )}
          <div className="border-t border-amber-900/40 pt-2 space-y-1">
            <p className="text-gray-400">未测族 ({disc?.untested_threat_families?.length ?? 0})</p>
            <p className="text-amber-100/80 break-words" data-testid="eval-s1-untested">
              {(disc?.untested_threat_families || []).slice(0, 12).join(', ') || '—'}
              {(disc?.untested_threat_families?.length || 0) > 12 ? '…' : ''}
            </p>
            <p className="text-gray-400">OOS ({disc?.oos_ids?.length ?? 0})</p>
            <p className="text-amber-100/80" data-testid="eval-s1-oos">
              {(disc?.oos_ids || []).join(', ') || '—'}
            </p>
            <p className="text-gray-400">
              deferred ({disc?.deferred_threat_families?.length ?? 0})
              {disc?.annotation_only ? ' · annotation_only' : ''}
            </p>
            <p className="text-amber-100/80 break-words">
              {(disc?.deferred_threat_families || []).slice(0, 8).join(', ') || '—'}
            </p>
          </div>
          {status.honesty ? (
            <p className="text-gray-500 italic">{status.honesty}</p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
