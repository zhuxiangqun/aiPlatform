/**
 * EVAL_V1 E6 — /eval 评测中心 v1（G2a 后）。
 * Honesty: engineering calibration only — never claim accuracy / κ / external gate.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiClient } from '../../services';
import DiagnosticsEvalDashboard from '../Diagnostics/EvalDashboard';

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

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [st, setsRes, gatesRes, qRes] = await Promise.all([
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
      ]);
      setStatus(unwrap(st));
      setSets(unwrapList(setsRes));
      setGates(unwrapList(gatesRes));
      setQueue(unwrap(qRes));
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const locked = Boolean(status?.v0_locked);
  const accuracy = Boolean(status?.accuracy_claim);
  const pendingCount = useMemo(() => {
    if (typeof status?.labels_pending === 'number') return status.labels_pending;
    if (Array.isArray(queue?.pending)) return queue.pending.length;
    if (Array.isArray(queue?.items)) return queue.items.length;
    return null;
  }, [queue, status]);

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
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <ShieldCheck className={`w-4 h-4 ${locked ? 'text-green-400' : 'text-gray-500'}`} />
            G2a 总览
          </div>
          {loading && !status ? (
            <div className="text-sm text-gray-500">加载中…</div>
          ) : status ? (
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-gray-500">v0_locked</dt>
                <dd className={locked ? 'text-green-300' : 'text-yellow-300'}>
                  {String(status.v0_locked)}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">g2a_ready</dt>
                <dd>{String(status.g2a_ready)}</dd>
              </div>
              <div>
                <dt className="text-gray-500">tasks</dt>
                <dd>{status.task_count ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-gray-500">adjudicated</dt>
                <dd>
                  {status.labels_adjudicated ?? '—'}/{status.v0_lock_target ?? 30}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">pending</dt>
                <dd>{pendingCount ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-gray-500">sets / gates</dt>
                <dd>
                  {sets.length} / {gates.length}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-3">
                <dt className="text-gray-500">note</dt>
                <dd className="text-gray-300">{status.note || '—'}</dd>
              </div>
            </dl>
          ) : null}
        </section>
      )}

      {tab === 'sets' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
          <h2 className="text-sm font-medium">评测集</h2>
          {sets.length === 0 ? (
            <p className="text-sm text-gray-500">暂无 set（或服务未返回 items）。</p>
          ) : (
            <ul className="divide-y divide-gray-800 text-sm">
              {sets.map((s, i) => (
                <li key={s.set_id || i} className="py-2 flex justify-between gap-3">
                  <span className="truncate">
                    {s.name || s.set_id || `set-${i}`}
                    {s.version ? (
                      <span className="text-gray-500 ml-2">v{s.version}</span>
                    ) : null}
                  </span>
                  <span className="text-gray-500 shrink-0">{s.status || '—'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === 'review' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3 text-sm">
          <h2 className="font-medium">人工复核队列</h2>
          <p className="text-gray-400">
            pending ≈ {pendingCount ?? '—'} · adjudicated ≈{' '}
            {status?.labels_adjudicated ??
              (Array.isArray(queue?.adjudicated) ? queue.adjudicated.length : '—')}
          </p>
          <p className="text-gray-500">
            写操作（adjudicate / lock-v0）仍走 canonical API / 运维 runbook；本 tab 只读。
          </p>
        </section>
      )}

      {tab === 'gates' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
          <h2 className="text-sm font-medium">门禁结果（local）</h2>
          {gates.length === 0 ? (
            <p className="text-sm text-gray-500">暂无 gate 记录。</p>
          ) : (
            <ul className="divide-y divide-gray-800 text-sm">
              {gates.map((g, i) => (
                <li key={g.gate_id || i} className="py-2 grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <span className="truncate">{g.gate_id || `gate-${i}`}</span>
                  <span className="text-gray-400">{g.kind || '—'}</span>
                  <span>
                    gate_claim={String(Boolean(g.gate_claim))}
                  </span>
                  <span className="text-amber-200/90">
                    accuracy={String(Boolean(g.accuracy_claim))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === 'reports' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2 text-sm">
          <h2 className="font-medium">报告</h2>
          <p className="text-gray-400">
            按 report_id 拉取：
            <code className="text-blue-300 ml-1">
              GET /api/platform/apps/eval/store/reports/&#123;id&#125;
            </code>
          </p>
          <p className="text-gray-500">
            G2a 本地报告示例见运维记录（如 <code>rpt_c12dfe23ba70</code>）；本页不自动宣称 accuracy。
          </p>
        </section>
      )}

      {tab === 'agents' && (
        <section className="space-y-3">
          <p className="text-sm text-gray-400">
            承接旧页 <code>/diagnostics/eval</code>。需要原布局可{' '}
            <Link className="text-blue-400 hover:underline" to="/diagnostics/eval?legacy=1">
              打开 legacy
            </Link>
            。
          </p>
          <DiagnosticsEvalDashboard />
        </section>
      )}

      {tab === 'knowledge' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 text-sm space-y-2">
          <h2 className="font-medium">Knowledge 评测</h2>
          <p className="text-gray-400">迁移入口：知识库 eval tab。</p>
          <Link className="text-blue-400 hover:underline" to="/knowledge/library?tab=eval">
            打开 Knowledge · eval
          </Link>
        </section>
      )}

      {tab === 'prompts' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 text-sm space-y-2">
          <h2 className="font-medium">Prompt 评测</h2>
          <p className="text-gray-400">承接 Prompt eval 能力入口。</p>
          <Link className="text-blue-400 hover:underline" to="/core/prompts">
            打开 Prompts
          </Link>
        </section>
      )}

      {tab === 'code-review' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 text-sm space-y-2">
          <h2 className="font-medium">code-review-gold</h2>
          <p className="text-gray-400">Governance 金标评估入口。</p>
          <Link className="text-blue-400 hover:underline" to="/governance">
            打开 Governance
          </Link>
        </section>
      )}

      {tab === 'settings' && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 text-sm space-y-2">
          <h2 className="font-medium">设置</h2>
          <ul className="list-disc pl-5 text-gray-400 space-y-1">
            <li>tenant 默认 <code>{TENANT}</code>（G2a lock 轨）</li>
            <li>judge / 阈值写操作仍走 API；UI 不暴露 accuracy 开关</li>
            <li>
              G2c（可选）：同人二次盲测 → <code>intra_rater_kappa</code> / self-consistency；
              <strong className="text-amber-200/90"> ≠ accuracy</strong>，≠ 第二标注者 / G2b
            </li>
            <li>
              G2c API：
              <code className="text-blue-300 ml-1">GET …/store/g2c-status</code>、
              <code className="text-blue-300">POST …/store/g2c-retest</code>、
              <code className="text-blue-300">POST …/store/g2c-report</code>
            </li>
            <li>G2b / 外部 gate：已 defer，未解冻</li>
          </ul>
        </section>
      )}
    </div>
  );
};

export default EvalCenter;
