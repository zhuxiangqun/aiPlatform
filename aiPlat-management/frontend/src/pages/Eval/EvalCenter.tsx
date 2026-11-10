/**
 * EVAL_V1 E6 — /eval 评测中心 v1（G2a 后）。
 * Honesty: engineering calibration only — never claim accuracy / κ / external gate.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';
import { clearPageData, reportPageData } from '../../lib/pageDataBridge';
import EvalCollapsibleBanner from './EvalCollapsibleBanner';
import EvalExecutionPlaneBanner from './EvalExecutionPlaneBanner';
import EvalAgentsPanel from './EvalAgentsPanel';
import EvalGeneratedAppsPanel from './EvalGeneratedAppsPanel';
import EvalEvidencePanel from './EvalEvidencePanel';
import EvalSkillsPanel from './EvalSkillsPanel';
import EvalGatesPanel from './EvalGatesPanel';
import EvalG2bPanel from './EvalG2bPanel';
import EvalMethodTrackPanel from './EvalMethodTrackPanel';
import EvalP1RegressionPanel from './EvalP1RegressionPanel';
import EvalP4StatusPanel from './EvalP4StatusPanel';
import EvalPromptRegressionPanel from './EvalPromptRegressionPanel';
import EvalWorkflowRegressionPanel from './EvalWorkflowRegressionPanel';
import EvalModelRegressionPanel from './EvalModelRegressionPanel';
import EvalToolRegressionPanel from './EvalToolRegressionPanel';
import EvalSessionRegressionPanel from './EvalSessionRegressionPanel';
import EvalKbRegressionPanel from './EvalKbRegressionPanel';
import EvalCodeReviewRegressionPanel from './EvalCodeReviewRegressionPanel';
import EvalMultiAgentRegressionPanel from './EvalMultiAgentRegressionPanel';
import EvalOverviewPanel from './EvalOverviewPanel';
import EvalPreferencePanel from './EvalPreferencePanel';
import EvalReportsPanel from './EvalReportsPanel';
import EvalScorecardPanel from './EvalScorecardPanel';
import EvalReviewPanel from './EvalReviewPanel';
import EvalRunPanel from './EvalRunPanel';
import EvalSetsPanel from './EvalSetsPanel';
import EvalSettingsPanel from './EvalSettingsPanel';
import EvalTabGuide from './EvalTabGuide';
import EvalTypedPlanPanel from './EvalTypedPlanPanel';
import EvalCasePackPanel from './EvalCasePackPanel';
import EvalCaseEditorPanel from './EvalCaseEditorPanel';
import EvalWorksheetPanel from './EvalWorksheetPanel';
import { EVAL_TAB_GUIDES, evalConsultantPageData } from './evalTabGuides';
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

/** 成果物评测 / 题目与报告 — 主路径 */
const ARTIFACT_TABS = [
  { id: 'overview', label: '总览' },
  { id: 'agents', label: '评测 Agent' },
  { id: 'skills', label: '评测 Skill' },
  { id: 'apps', label: '评测生成应用' },
  { id: 'sets', label: '评测集' },
  { id: 'reports', label: '报告' },
] as const;

/** 评测管道自检 — 不是在考产品 */
const PIPE_TABS = [
  { id: 'code-review', label: 'Code-review' },
  { id: 'session', label: 'Session' },
  { id: 'skill', label: 'Skill 管道' },
] as const;

const ADVANCED_TABS = [
  { id: 'review', label: '复核' },
  { id: 'gates', label: '门禁' },
  { id: 'typed-plan', label: '对象Plan' },
  { id: 'case-packs', label: 'Case Pack' },
  { id: 'case-editor', label: '题目维护' },
  { id: 'method-track', label: 'Method轨' },
  { id: 'p1-regression', label: 'P1 Regression' },
  { id: 'prompt-regression', label: 'Prompt Regression' },
  { id: 'workflow-regression', label: 'Workflow Regression' },
  { id: 'model-regression', label: 'Model Regression' },
  { id: 'tool-regression', label: 'Tool Regression' },
  { id: 'session-regression', label: 'Session Regression' },
  { id: 'kb-regression', label: 'KB Regression' },
  { id: 'code-review-regression', label: 'Code Review Regression' },
  { id: 'multi-agent-regression', label: 'Multi-Agent Regression' },
  { id: 'p4-status', label: 'P4 Benchmark' },
  { id: 'g2b', label: 'G2b' },
  { id: 'preference', label: 'Preference' },
  { id: 'scorecard', label: 'Scorecard' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'worksheets', label: 'Worksheets' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'arena', label: 'Arena' },
  { id: 'research', label: 'P2 Research' },
  { id: 'settings', label: '设置' },
] as const;

const TABS = [...ARTIFACT_TABS, ...PIPE_TABS, ...ADVANCED_TABS] as const;
type TabId = (typeof TABS)[number]['id'];

const ADVANCED_IDS = new Set<string>(ADVANCED_TABS.map((t) => t.id));
const PIPE_IDS = new Set<string>(PIPE_TABS.map((t) => t.id));
const ADVANCED_STORAGE_KEY = 'eval.nav.advanced.open';
const PIPE_STORAGE_KEY = 'eval.nav.pipe.open';

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function writeFlag(key: string, open: boolean) {
  try {
    localStorage.setItem(key, open ? '1' : '0');
  } catch {
    /* ignore */
  }
}

const TENANT = 'eval-v1';

const EvalCenter: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const tabParam = (params.get('tab') || 'overview').toLowerCase();
  const tab: TabId = (TABS.some((t) => t.id === tabParam) ? tabParam : 'overview') as TabId;

  const [pipeOpen, setPipeOpen] = useState(() => {
    if (PIPE_IDS.has(tabParam)) return true;
    return readFlag(PIPE_STORAGE_KEY);
  });
  const [advancedOpen, setAdvancedOpen] = useState(() => {
    if (ADVANCED_IDS.has(tabParam)) return true;
    return readFlag(ADVANCED_STORAGE_KEY);
  });

  useEffect(() => {
    if (PIPE_IDS.has(tab) && !pipeOpen) setPipeOpen(true);
  }, [tab, pipeOpen]);

  useEffect(() => {
    if (ADVANCED_IDS.has(tab) && !advancedOpen) setAdvancedOpen(true);
  }, [tab, advancedOpen]);

  const togglePipe = useCallback(() => {
    setPipeOpen((prev) => {
      const next = !prev;
      writeFlag(PIPE_STORAGE_KEY, next);
      return next;
    });
  }, []);

  const toggleAdvanced = useCallback(() => {
    setAdvancedOpen((prev) => {
      const next = !prev;
      writeFlag(ADVANCED_STORAGE_KEY, next);
      return next;
    });
  }, []);

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

  // P2-4: feed 小朱 — current tab guide + all-tab catalog + live G2a snapshot.
  useEffect(() => {
    reportPageData(
      '/eval',
      evalConsultantPageData({
        tabId: tab,
        upstreamMode,
        accuracyClaim: accuracy,
        g2aReady: Boolean(status?.g2a_ready),
        v0Locked: Boolean(status?.v0_locked),
        pending: pendingCount,
        setsCount: sets.length,
        gatesCount: gates.length,
      }),
    );
    return () => clearPageData('/eval');
  }, [
    tab,
    upstreamMode,
    accuracy,
    status?.g2a_ready,
    status?.v0_locked,
    pendingCount,
    sets.length,
    gates.length,
  ]);

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
          两条路别混：
          <strong className="text-violet-200/90 font-medium">评测 Agent / Skill / 生成应用</strong>
          ＝评成果物；折叠「验管道」里的 Code-review / Session / Skill 管道＝只验 fixture，不评产品。
        </p>
      </header>

      {showExecBanner ? (
        <EvalExecutionPlaneBanner
          code="execution_not_migrated"
          detail={
            upstreamMode === 'proxy'
              ? `当前上游 mode=proxy（本机 Job 已接到 :8010）· 产品上仍记「${EXECUTION_NOT_MIGRATED_COPY}」`
              : '当前上游 mode=cohost：Session/Arena/Skill 等 Job 需先起本地 eval proxy'
          }
        />
      ) : null}

      <EvalCollapsibleBanner
        storageKey="eval.banner.honesty.open"
        testId="eval-honesty-banner"
        toneClassName="border-amber-700/50 bg-amber-950/30 text-amber-100"
        icon={<AlertTriangle className="w-5 h-5 text-amber-400" />}
        summary={
          <>
            诚实约束（强制）· 防误读
            <span className="font-normal text-amber-100/70 text-xs sm:text-sm ml-2">
              accuracy_claim={String(accuracy)} · 点击展开
            </span>
          </>
        }
      >
        <p className="text-amber-100/80 text-xs sm:text-sm">
          页面上的分数、κ、门禁，默认都是「工程自检」，不要当成「模型已经测准」或「可以对外发布」。
        </p>
        <ul className="list-disc pl-5 text-amber-100/90 space-y-0.5">
          <li>
            <code>accuracy_claim</code>＝是否宣称准确率 · 必须为 false（当前：
            {String(accuracy)}）
          </li>
          <li>
            κ（kappa）＝两个人标得是否一致 · 本地单人复核时为 null；G2b 的 κ 也不是准确率
          </li>
          <li>
            <code>gate_claim</code>＝本机门禁过了没 · 不等于外部 / staging / 生产授权
          </li>
        </ul>
      </EvalCollapsibleBanner>

      <nav className="space-y-2 border-b border-gray-700 pb-2" aria-label="Eval tabs">
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-[10px] uppercase tracking-wide text-violet-300/70 mr-1">成果物</span>
          {ARTIFACT_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              title={EVAL_TAB_GUIDES[t.id]?.what || t.label}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 text-sm rounded-t ${
                tab === t.id
                  ? 'bg-violet-950/50 text-violet-50 border border-b-0 border-violet-600/50'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {t.label}
            </button>
          ))}
          <button
            type="button"
            data-testid="eval-nav-pipe-toggle"
            onClick={togglePipe}
            className="px-2.5 py-1.5 text-xs rounded border border-sky-800/50 text-sky-200/80 hover:bg-sky-950/40"
            aria-expanded={pipeOpen}
          >
            {pipeOpen ? '收起「验管道」▴' : '验管道 ▾'}
          </button>
          <button
            type="button"
            data-testid="eval-nav-advanced-toggle"
            onClick={toggleAdvanced}
            className="px-2.5 py-1.5 text-xs rounded border border-gray-700 text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
            aria-expanded={advancedOpen}
          >
            {advancedOpen ? '收起高级 ▴' : '高级 ▾'}
          </button>
        </div>
        {pipeOpen ? (
          <div className="flex flex-wrap gap-1 items-center" data-testid="eval-nav-pipe">
            <span className="text-[10px] text-sky-300/70 mr-1">管道自检 · 非成果物</span>
            {PIPE_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                title={EVAL_TAB_GUIDES[t.id]?.what || t.label}
                onClick={() => setTab(t.id)}
                className={`px-2.5 py-1 text-xs rounded ${
                  tab === t.id
                    ? 'bg-sky-950/50 text-sky-50 border border-sky-700/50'
                    : 'text-sky-200/70 hover:text-sky-100 border border-transparent'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        ) : null}
        {advancedOpen ? (
          <div className="flex flex-wrap gap-1" data-testid="eval-nav-advanced">
            {ADVANCED_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                title={EVAL_TAB_GUIDES[t.id]?.what || t.label}
                onClick={() => setTab(t.id)}
                className={`px-2.5 py-1 text-xs rounded ${
                  tab === t.id
                    ? 'bg-gray-800 text-white border border-gray-600'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        ) : null}
      </nav>

      {tab !== 'overview' ? <EvalTabGuide tabId={tab} /> : null}

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

      {tab === 'typed-plan' && <EvalTypedPlanPanel />}

      {tab === 'case-packs' && <EvalCasePackPanel />}

      {tab === 'case-editor' && <EvalCaseEditorPanel />}

      {tab === 'reports' && <EvalReportsPanel tenantId={TENANT} />}

      {tab === 'method-track' && <EvalMethodTrackPanel tenantId={TENANT} />}

      {tab === 'p1-regression' && <EvalP1RegressionPanel tenantId={TENANT} />}

      {tab === 'prompt-regression' && <EvalPromptRegressionPanel tenantId={TENANT} />}

      {tab === 'workflow-regression' && (
        <EvalWorkflowRegressionPanel tenantId={TENANT} />
      )}

      {tab === 'model-regression' && <EvalModelRegressionPanel tenantId={TENANT} />}

      {tab === 'tool-regression' && <EvalToolRegressionPanel tenantId={TENANT} />}

      {tab === 'session-regression' && (
        <EvalSessionRegressionPanel tenantId={TENANT} />
      )}

      {tab === 'kb-regression' && <EvalKbRegressionPanel tenantId={TENANT} />}

      {tab === 'code-review-regression' && (
        <EvalCodeReviewRegressionPanel tenantId={TENANT} />
      )}

      {tab === 'multi-agent-regression' && (
        <EvalMultiAgentRegressionPanel tenantId={TENANT} />
      )}

      {tab === 'p4-status' && <EvalP4StatusPanel tenantId={TENANT} />}

      {tab === 'g2b' && <EvalG2bPanel tenantId={TENANT} />}

      {tab === 'preference' && <EvalPreferencePanel tenantId={TENANT} />}

      {tab === 'scorecard' && <EvalScorecardPanel tenantId={TENANT} />}

      {tab === 'evidence' && <EvalEvidencePanel tenantId={TENANT} />}
      {tab === 'worksheets' && <EvalWorksheetPanel tenantId={TENANT} />}

      {tab === 'agents' && (
        <EvalAgentsPanel tenantId={TENANT} />
      )}

      {tab === 'skills' && <EvalSkillsPanel tenantId={TENANT} />}

      {tab === 'apps' && <EvalGeneratedAppsPanel />}

      {tab === 'knowledge' && (
        <section className="space-y-3 text-sm">
          <EvalRunPanel kind="kb_rag" upstreamMode={upstreamMode} tenantId={TENANT} />
          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
            <p className="text-gray-400">知识库管理（非评测主入口）：</p>
            <Link className="text-blue-400 hover:underline" to="/knowledge/library?tab=eval">
              打开 Knowledge · library
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

      {tab === 'session' && (
        <section className="space-y-3 text-sm">
          <EvalRunPanel kind="session_eval" upstreamMode={upstreamMode} tenantId={TENANT} />
        </section>
      )}

      {tab === 'arena' && (
        <section className="space-y-3 text-sm">
          <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90">
            默认只比「谁写得更长」（烟雾测试），不是质量裁判；盲评结果只当证据展示，不打开质量门禁。
          </div>
          <EvalRunPanel kind="arena" upstreamMode={upstreamMode} tenantId={TENANT} />
        </section>
      )}

      {tab === 'skill' && (
        <section className="space-y-3 text-sm">
          <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90">
            管道自检：只跑预制 fixture 对账；需要 Docker 沙箱探针。评真实 Skill suite 请用成果物「评测
            Skill」。
          </div>
          <EvalRunPanel kind="skill_suite" upstreamMode={upstreamMode} tenantId={TENANT} />
        </section>
      )}

      {tab === 'research' && (
        <section className="space-y-4 text-sm">
          <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90">
            三项都是工程自检门（上下文 / 记忆 / 自学习）。通过 ≠ 生产已写回记忆或授权自学习上线。
          </div>
          <EvalRunPanel kind="context_mgmt" upstreamMode={upstreamMode} tenantId={TENANT} />
          <EvalRunPanel kind="memory_persist" upstreamMode={upstreamMode} tenantId={TENANT} />
          <EvalRunPanel kind="self_learn" upstreamMode={upstreamMode} tenantId={TENANT} />
        </section>
      )}

      {tab === 'settings' && <EvalSettingsPanel tenantId={TENANT} />}
    </div>
  );
};

export default EvalCenter;
