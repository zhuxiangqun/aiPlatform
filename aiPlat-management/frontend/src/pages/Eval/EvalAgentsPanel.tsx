/**
 * UI-6 — Agents tab: skill-eval suites strip + legacy diagnostics embed.
 * Dynamic suite run still package-plane / B2; cohost list is read-only.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';
import DiagnosticsEvalDashboard from '../Diagnostics/EvalDashboard';
import { EXECUTION_NOT_MIGRATED_COPY } from './evalExecutionErrors';

function unwrapList<T>(res: unknown): T[] {
  const body = res as { data?: { items?: T[] }; items?: T[] } & T[];
  if (Array.isArray(body?.data?.items)) return body.data!.items!;
  if (Array.isArray(body?.items)) return body.items!;
  if (Array.isArray(body?.data)) return body.data as T[];
  if (Array.isArray(body)) return body;
  return [];
}

type SuiteRow = {
  id?: string;
  suite_id?: string;
  name?: string;
  status?: string;
  updated_at?: string;
};

type Props = {
  tenantId?: string;
  showExecBanner?: boolean;
};

export default function EvalAgentsPanel({
  tenantId = 'eval-v1',
  showExecBanner = false,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [suites, setSuites] = useState<SuiteRow[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get(
        `/platform/apps/eval/skill-evals/suites?tenant_id=${encodeURIComponent(tenantId)}&limit=30`,
      );
      setSuites(unwrapList<SuiteRow>(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setSuites([]);
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-3" data-testid="eval-agents-panel">
      {showExecBanner ? (
        <p className="text-sm text-sky-200/90" data-testid="eval-agents-exec-note">
          {EXECUTION_NOT_MIGRATED_COPY} — Agents 动态 run 请走 package Worker；下方 suites 只读 + 共宿诊断视图。
        </p>
      ) : null}

      <section className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3 text-sm">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Skill-eval suites</h2>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        {error ? (
          <p className="text-xs text-amber-200/90">suites 不可用: {error}</p>
        ) : null}
        {loading && suites.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : suites.length === 0 ? (
          <p className="text-gray-500">暂无 suite（或 API 未返回 items）。</p>
        ) : (
          <ul className="divide-y divide-gray-800" data-testid="eval-agents-suites">
            {suites.map((s, i) => {
              const id = String(s.id || s.suite_id || `suite-${i}`);
              return (
                <li key={id} className="py-2 flex justify-between gap-3 text-xs">
                  <span className="truncate font-mono text-blue-200">{s.name || id}</span>
                  <span className="text-gray-500 shrink-0">{s.status || s.updated_at || '—'}</span>
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-[11px] text-gray-600">
          suite run → package <code>/skill-evals/suites/&#123;id&#125;/run</code>（B2 allowlist）
        </p>
      </section>

      <p className="text-sm text-gray-400">
        承接旧页 <code>/diagnostics/eval</code>。需要原布局可{' '}
        <Link className="text-blue-400 hover:underline" to="/diagnostics/eval?legacy=1">
          打开 legacy
        </Link>
        。
      </p>
      <DiagnosticsEvalDashboard />
    </div>
  );
}
