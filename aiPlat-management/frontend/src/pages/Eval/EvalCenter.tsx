/**
 * EVAL_V1 E6 — /eval 评测中心 v1（G2a 后）。
 * Honesty: engineering calibration only — never claim accuracy / κ / external gate.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';
import EvalExecutionPlaneBanner from './EvalExecutionPlaneBanner';
import EvalAgentsPanel from './EvalAgentsPanel';
import EvalGatesPanel from './EvalGatesPanel';
import EvalG2bPanel from './EvalG2bPanel';
import EvalOverviewPanel from './EvalOverviewPanel';
import EvalPreferencePanel from './EvalPreferencePanel';
import EvalReportsPanel from './EvalReportsPanel';
import EvalReviewPanel from './EvalReviewPanel';
import EvalRunPanel from './EvalRunPanel';
import EvalSetsPanel from './EvalSetsPanel';
import EvalSettingsPanel from './EvalSettingsPanel';
import {
  EXECUTION_NOT_MIGRATED_COPY,
  shouldShowExecutionPlaneBanner,
} from './evalExecutionErrors';

type G2aStatus = {
  ok?: boolean;
  schema_version?: string;
  tenant_id?: string;
  set_id?: string;
  task_count?: number;
  labels_pending?: number;
  labels_adjudicated?: number;
  v0_lock_target?: number;
  v0_lock_ready?: boolean;
  v0_locked?: boolean;
  g2a_ready?: boolean;
  accuracy_claim?: boolean;
  kappa?: number | null;
  note?: string;
};

type EvalSet = { set_id?: string; name?: string; version?: string; status?: string };
type GateRow = {
  gate_id?: string;
  kind?: string;
  gate_claim?: boolean;
  accuracy_claim?: boolean;
  created_at?: string;
};
type ReviewQueue = {
  pending?: unknown[];
  adjudicated?: unknown[];
  items?: unknown[];
};

type Envelope<T> = { data?: T; items?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

function unwrapList<T>(res: Envelope<T[]> | { data?: { items?: T[] }; items?: T[] }): T[] {
  const body = res as any;
  if (Array.isArray(body?.data?.items)) return body.data.items;
  if (Array.isArray(body?.items)) return body.items;
  if (Array.isArray(body?.data)) return body.data;
  if (Array.isArray(body)) return body;
  return [];
}

const TABS = [
  { id: 'overview', label: '总览' },
  { id: 'sets', label: '评测集' },
  { id: 'review', label: '复核' },
  { id: 'gates', label: '门禁' },
  { id: 'reports', label: '报告' },
  { id: 'g2b', label: 'G2b' },
  { id: 'preference', label: 'Preference' },
  { id: 'agents', label: 'Agents' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'code-review', label: 'Code-review' },
  { id: 'settings', label: '设置' },
] as const;

type TabId = (typeof TABS)[number]['id'];

const TENANT = 'eval-v1';

const EvalCenter: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const tabParam = (params.get('tab') || 'overview').toLowerCase();
  const tab: TabId = (TABS.some((t) => t.id === tabParam) ? tabParam : 'overview') as TabId;

  const setTab = useCallback(
    (next: TabId) => {
      const p = new URLSearchParams(params);
      p.set('tab', next);
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const [status, setStatus] = useState<G2aStatus | null>(null);
  const [sets, setSets] = useState<EvalSet[]>([]);
  const [gates, setGates] = useState<GateRow[]>([]);
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [upstreamMode, setUpstreamMode] = useState<string | null>(null);
  const [b1lStubs, setB1lStubs] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [st, setsRes, gatesRes, qRes, upRes] = await Promise.all([
        apiClient.get<Envelope<G2aStatus>>(
          `/platform/apps/eval/store/g2a-status?tenant_id=${TENANT}`,
        ),
        apiClient.get<Envelope<EvalSet[]>>(
          `/platform/apps/eval/store/sets?tenant_id=${TENANT}`,
        ),
        apiClient.get<Envelope<GateRow[]>>(
          `/platform/apps/eval/store/gates?tenant_id=${TENANT}`,
        ),
        apiClient.get<Envelope<ReviewQueue>>(
          `/platform/apps/eval/store/review-queue?tenant_id=${TENANT}`,
        ),
        apiClient
          .get<Envelope<{ mode?: string; enabled?: boolean }>>(
            `/platform/apps/eval/store/upstream-status`,
          )
          .catch(() => null),
      ]);
      setStatus(unwrap(st));
      setSets(unwrapList(setsRes));
      setGates(unwrapList(gatesRes));
      setQueue(unwrap(qRes));
      const up = upRes ? unwrap(upRes) : null;
      setUpstreamMode(up?.mode ? String(up.mode) : null);
      // Standalone B1-L advertises stubs on product healthz; optional when proxied.
      setB1lStubs(false);
      if (up?.mode === 'proxy') {
        try {
          const hz = await apiClient.get<Envelope<{ b1l_execution_stubs?: boolean }>>(
            `/platform/apps/eval/healthz`,
          );
          const body = unwrap(hz) as { b1l_execution_stubs?: boolean };
          setB1lStubs(Boolean(body?.b1l_execution_stubs));
        } catch {
          // Proxy without product healthz still means standalone store → show banner.
          setB1lStubs(true);
        }
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accuracy = Boolean(status?.accuracy_claim);
  const pendingCount = useMemo(() => {
    if (typeof status?.labels_pending === 'number') return status.labels_pending;
    if (Array.isArray(queue?.pending)) return queue.pending.length;
    if (Array.isArray(queue?.items)) return queue.items.length;
    return null;
  }, [queue, status]);

  const showExecBanner = shouldShowExecutionPlaneBanner({
    upstreamMode,
    b1lExecutionStubs: b1lStubs,
  });

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5 text-gray-200">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-2xl font-semibold tracking-tight">评测中心</h1>
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
          EVAL_V1 E6 · canonical{' '}
          <code className="text-blue-300">/api/platform/apps/eval</code>
          {' · '}tenant <code className="text-blue-300">{TENANT}</code>
        </p>
      </header>

      {showExecBanner ? (
        <EvalExecutionPlaneBanner
          code="execution_not_migrated"
          detail={
            upstreamMode === 'proxy'
              ? `上游 mode=proxy · ${EXECUTION_NOT_MIGRATED_COPY}`
              : null
          }
        />
      ) : null}

      <div
        className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-3 flex gap-3 items-start"
        role="status"
      >
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-sm space-y-1">
          <div className="font-medium text-amber-200">诚实约束（强制）</div>
          <ul className="list-disc pl-5 text-amber-100/90 space-y-0.5">
            <li>
              <code>accuracy_claim</code> 必须为 false（当前：{String(accuracy)}）
            </li>
            <li>κ = null（D5 单人复核；G2b 前不计算）</li>
            <li>local <code>gate_claim</code> ≠ 外部 / staging / authorize</li>
          </ul>
        </div>
      </div>

      <nav className="flex flex-wrap gap-1 border-b border-gray-700 pb-2" aria-label="Eval tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 text-sm rounded-t ${
              tab === t.id
                ? 'bg-gray-800 text-white border border-b-0 border-gray-600'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {error ? (
        <div className="rounded border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          无法加载评测 store：{error}
        </div>
      ) : null}

      {tab === 'overview' && (
        <EvalOverviewPanel
          status={status}
          loading={loading}
          pendingCount={pendingCount}
          setsCount={sets.length}
          gatesCount={gates.length}
          upstreamMode={upstreamMode}
          onNavigate={(t) => setTab(t as TabId)}
        />
      )}

      {tab === 'sets' && <EvalSetsPanel tenantId={TENANT} />}

      {tab === 'review' && <EvalReviewPanel tenantId={TENANT} />}

      {tab === 'gates' && <EvalGatesPanel tenantId={TENANT} />}

      {tab === 'reports' && <EvalReportsPanel tenantId={TENANT} />}

      {tab === 'g2b' && <EvalG2bPanel tenantId={TENANT} />}

      {tab === 'preference' && <EvalPreferencePanel tenantId={TENANT} />}

      {tab === 'agents' && (
        <EvalAgentsPanel tenantId={TENANT} showExecBanner={showExecBanner} />
      )}

      {tab === 'knowledge' && (
        <section className="space-y-3 text-sm">
          <EvalRunPanel kind="kb_rag" upstreamMode={upstreamMode} tenantId={TENANT} />
          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
            <p className="text-gray-400">完整知识库 eval UI 仍可用：</p>
            <Link className="text-blue-400 hover:underline" to="/knowledge/library?tab=eval">
              打开 Knowledge · eval
            </Link>
          </div>
        </section>
      )}

      {tab === 'prompts' && (
        <section className="space-y-3 text-sm">
          <EvalRunPanel kind="prompt_eval" upstreamMode={upstreamMode} tenantId={TENANT} />
          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
            <p className="text-gray-400">模板管理入口：</p>
            <Link className="text-blue-400 hover:underline" to="/core/prompts">
              打开 Prompts
            </Link>
          </div>
        </section>
      )}

      {tab === 'code-review' && (
        <section className="space-y-3 text-sm">
          <EvalRunPanel kind="code_review" upstreamMode={upstreamMode} tenantId={TENANT} />
          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
            <p className="text-gray-400">值班板一键 Gold 仍在 Governance：</p>
            <Link className="text-blue-400 hover:underline" to="/governance">
              打开 Governance
            </Link>
          </div>
        </section>
      )}

      {tab === 'settings' && <EvalSettingsPanel tenantId={TENANT} />}
    </div>
  );
};

export default EvalCenter;
