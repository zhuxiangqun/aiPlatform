/**
 * Cross-Subject regression honesty inventory — quotas may be complete; claim stays closed.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { apiClient, agentEvalApi } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type SubjectRow = {
  subject_kind?: string;
  object_type_member?: boolean;
  tab_id?: string;
  tab_href?: string;
  ok?: boolean;
  error?: string | null;
  profile_id?: string;
  suite_profile_href?: string;
  pack_id?: string;
  pack_version?: string;
  pack_status?: string;
  quota_inventory_ok?: boolean;
  profile_complete?: boolean;
  case_count?: number;
  purpose_ok_or_better?: number;
  draft_pending?: number;
  content_purpose_ok_count?: number;
  content_purpose_ready?: boolean;
  workspace_promoted?: boolean;
  workspace_pack_kind?: string;
  workspace_pack_status?: string;
  workspace_promote_error?: string;
  claim_eligible?: boolean;
  accuracy_claim?: boolean;
  certification_eligible?: boolean;
};

type Inventory = {
  ok?: boolean;
  subject_count?: number;
  object_type_subject_count?: number;
  quota_inventory_ok_count?: number;
  profile_complete_count?: number;
  draft_pending_total?: number;
  content_purpose_ready_count?: number;
  workspace_id?: string;
  workspace_promoted_count?: number;
  subjects?: SubjectRow[];
  next_action?: string;
  honesty?: string;
  claim_eligible?: boolean;
  accuracy_claim?: boolean;
  certification_eligible?: boolean;
  review_links?: {
    method_track_tab?: string;
    case_packs_tab?: string;
    p1_regression_tab?: string;
    content_purpose_ok_tab?: string;
  };
};

type Props = { tenantId?: string };

export default function EvalSubjectRegressionInventoryPanel(_props: Props = {}) {
  const [loading, setLoading] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [examBusy, setExamBusy] = useState(false);
  const [error, setError] = useState('');
  const [promoteMsg, setPromoteMsg] = useState('');
  const [examMsg, setExamMsg] = useState('');
  const [status, setStatus] = useState<Inventory | null>(null);
  const [promoteKind, setPromoteKind] = useState('prompt');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<Inventory>>(
        `/platform/apps/eval/store/subject-regression-inventory`,
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

  const onPromote = useCallback(async () => {
    setPromoting(true);
    setPromoteMsg('');
    setError('');
    try {
      const out = await agentEvalApi.casePackPromoteSubjectCapability({
        subject_kind: promoteKind,
        reviewer: 'ui',
        frozen_by: 'ui',
        notes: `Subject Inventory promote ${promoteKind}`,
      });
      const body = unwrap(out as Envelope<Record<string, unknown>>);
      setPromoteMsg(
        `promote ${String(body.subject_kind || promoteKind)} → ${String(
          body.kind || '?',
        )} / claim=${String(Boolean(body.claim_eligible))} noop=${String(
          Boolean(body.noop),
        )}`,
      );
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPromoting(false);
    }
  }, [load, promoteKind]);

  const onPromoteAll = useCallback(async () => {
    setPromoting(true);
    setPromoteMsg('');
    setError('');
    try {
      const out = await agentEvalApi.casePackPromoteSubjectCapability({
        all: true,
        reviewer: 'ui',
        frozen_by: 'ui',
        notes: 'Subject Inventory promote_all',
      });
      const body = unwrap(out as Envelope<Record<string, unknown>>);
      const subjects = Array.isArray(body.subjects) ? body.subjects : [];
      const nErr = Number(body.n_errors ?? 0);
      setPromoteMsg(
        `promote_all n_subjects=${String(body.n_subjects ?? subjects.length)} n_errors=${nErr} / claim=${String(
          Boolean(body.claim_eligible),
        )}`,
      );
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPromoting(false);
    }
  }, [load]);

  const onCompileExamDry = useCallback(async () => {
    setExamBusy(true);
    setExamMsg('');
    setError('');
    try {
      const row = (status?.subjects || []).find((r) => r.subject_kind === promoteKind);
      const profileId = String(row?.profile_id || '').trim();
      if (!profileId) {
        throw new Error(`no profile_id for subject ${promoteKind}`);
      }
      const compiled = unwrap(
        (await agentEvalApi.casePackCompileSuiteProfile({
          profile_id: profileId,
        })) as Envelope<Record<string, unknown>>,
      );
      if (compiled && compiled.ok === false) {
        throw new Error(
          String(compiled.error || compiled.message || 'compile-suite-profile failed'),
        );
      }
      const exam = unwrap(
        (await agentEvalApi.casePackRunSuiteProfile({
          profile_id: profileId,
          live: false,
        })) as Envelope<Record<string, unknown>>,
      );
      if (exam && exam.ok === false) {
        throw new Error(String(exam.error || exam.message || 'run-suite-profile failed'));
      }
      setExamMsg(
        `compile+exam(dry) ${profileId} · claim=${String(
          Boolean(exam?.claim_eligible ?? compiled?.claim_eligible),
        )} · cases=${String(
          (exam as { n_cases?: number; case_count?: number })?.n_cases ??
            (exam as { case_count?: number })?.case_count ??
            '—',
        )}`,
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExamBusy(false);
    }
  }, [promoteKind, status?.subjects]);

  const rows = status?.subjects || [];
  const packsHref = status?.review_links?.case_packs_tab || '/eval?tab=case-packs';
  const methodHref = status?.review_links?.method_track_tab || '/eval?tab=method-track';
  const p1Href = status?.review_links?.p1_regression_tab || '/eval?tab=p1-regression';
  const selectedProfileId = String(
    rows.find((r) => r.subject_kind === promoteKind)?.profile_id || '',
  ).trim();

  return (
    <div className="space-y-4 text-sm" data-testid="eval-subject-regression-inventory-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Subject Regression 总览诚实门（ADR）</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            subjects={status?.subject_count ?? '—'} · OBJECT_TYPES=
            {status?.object_type_subject_count ?? '—'} · quota_ok=
            {status?.quota_inventory_ok_count ?? '—'} · content_purpose_ready=
            {status?.content_purpose_ready_count ?? '—'} · profile_complete=
            {status?.profile_complete_count ?? '—'} · workspace_promoted=
            {status?.workspace_promoted_count ?? '—'}
            {status?.workspace_id ? ` @${status.workspace_id}` : ' (无 workspace)'} ·
            draft_pending={status?.draft_pending_total ?? '—'}
          </li>
          <li>
            claim_eligible={String(Boolean(status?.claim_eligible))} · accuracy_claim=
            {String(Boolean(status?.accuracy_claim))} · certification=
            {String(Boolean(status?.certification_eligible))}
          </li>
          <li>
            {status?.honesty ||
              '跨 Subject 配额盘点 ≠ claim；content_purpose_ok 门禁 promote；人审 purpose_ok/freeze 前不得宣称收口；Method 轨不在此表。'}
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">subject_regression_inventory · 就绪矩阵</h2>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {loading && !status ? (
          <p className="text-gray-500">加载中…</p>
        ) : status ? (
          <>
            <p className="text-xs text-sky-200/90">下一步：{status.next_action}</p>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <label className="text-gray-400">
                Promote subject
                <select
                  className="ml-2 rounded border border-gray-600 bg-gray-950 px-2 py-1"
                  value={promoteKind}
                  onChange={(e) => setPromoteKind(e.target.value)}
                  data-testid="eval-subject-inventory-promote-kind"
                >
                  {rows.map((r) => (
                    <option key={r.subject_kind} value={r.subject_kind || ''}>
                      {r.subject_kind}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={promoting || !promoteKind}
                onClick={() => void onPromote()}
                className="rounded border border-amber-700/60 px-2 py-1 text-amber-100 disabled:opacity-50"
                data-testid="eval-subject-inventory-promote"
              >
                {promoting ? 'Promoting…' : 'Promote 当前'}
              </button>
              <button
                type="button"
                disabled={promoting || !rows.length}
                onClick={() => void onPromoteAll()}
                className="rounded border border-sky-700/60 px-2 py-1 text-sky-100 disabled:opacity-50"
                data-testid="eval-subject-inventory-promote-all"
                title="POST promote-subject-capability all=true；claim 仍关闭"
              >
                {promoting ? 'Promoting…' : 'Promote 全部'}
              </button>
              <button
                type="button"
                disabled={examBusy || promoting || !selectedProfileId}
                onClick={() => void onCompileExamDry()}
                className="rounded border border-violet-700/60 px-2 py-1 text-violet-100 disabled:opacity-50"
                data-testid="eval-subject-inventory-compile-exam-dry"
                title="compile-suite-profile → run-suite-profile live=false；claim 仍关闭"
              >
                {examBusy
                  ? 'Exam…'
                  : selectedProfileId
                    ? `Compile+Exam dry (${selectedProfileId})`
                    : 'Compile+Exam dry'}
              </button>
              <span className="text-gray-500">
                claim 仍关；需 content_purpose_ready；仅工作区 registry 冻结；exam≠accuracy
              </span>
            </div>
            {promoteMsg ? <p className="text-xs text-emerald-200/90">{promoteMsg}</p> : null}
            {examMsg ? <p className="text-xs text-violet-200/90">{examMsg}</p> : null}
            <div className="flex flex-wrap gap-3 text-xs">
              <Link className="text-sky-300 hover:underline" to={packsHref}>
                打开 Case Pack
              </Link>
              <Link className="text-sky-300 hover:underline" to={p1Href}>
                打开 P1 Regression
              </Link>
              <Link className="text-sky-300 hover:underline" to={methodHref}>
                打开 Method 轨
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-700">
                    <th className="py-1 pr-2">subject</th>
                    <th className="py-1 pr-2">OT</th>
                    <th className="py-1 pr-2">pack</th>
                    <th className="py-1 pr-2">cases</th>
                    <th className="py-1 pr-2">quota</th>
                    <th className="py-1 pr-2">content</th>
                    <th className="py-1 pr-2">complete</th>
                    <th className="py-1 pr-2">ws promote</th>
                    <th className="py-1 pr-2">draft</th>
                    <th className="py-1 pr-2">suite</th>
                    <th className="py-1">tab</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length ? (
                    rows.map((row) => (
                      <tr key={row.subject_kind} className="border-b border-gray-800 align-top">
                        <td className="py-2 pr-2 font-mono">{row.subject_kind}</td>
                        <td className="py-2 pr-2">{row.object_type_member ? 'Y' : '—'}</td>
                        <td className="py-2 pr-2 font-mono">
                          {row.pack_id || '—'}@{row.pack_version || '—'}
                          <div className="text-gray-500">{row.pack_status || ''}</div>
                          {row.error ? (
                            <div className="text-red-300">{row.error}</div>
                          ) : null}
                        </td>
                        <td className="py-2 pr-2">{row.case_count ?? 0}</td>
                        <td className="py-2 pr-2">
                          {row.quota_inventory_ok ? '齐' : '缺口'}
                        </td>
                        <td className="py-2 pr-2">
                          {row.content_purpose_ready
                            ? `ok ${row.content_purpose_ok_count ?? 0}`
                            : `缺 ${row.content_purpose_ok_count ?? 0}`}
                        </td>
                        <td className="py-2 pr-2">{String(Boolean(row.profile_complete))}</td>
                        <td className="py-2 pr-2">
                          {row.workspace_promoted
                            ? `Y ${row.workspace_pack_kind || 'frozen'}`
                            : status?.workspace_id
                              ? '—'
                              : 'n/a'}
                          {row.workspace_promote_error ? (
                            <div className="text-gray-500">{row.workspace_promote_error}</div>
                          ) : null}
                        </td>
                        <td className="py-2 pr-2">{row.draft_pending ?? 0}</td>
                        <td className="py-2 pr-2">
                          {row.profile_id ? (
                            <Link
                              className="text-sky-300 hover:underline font-mono"
                              to={
                                row.suite_profile_href ||
                                `/eval?tab=case-packs&profile_id=${encodeURIComponent(row.profile_id)}`
                              }
                              title="Case Pack compile-suite-profile → run exam"
                            >
                              {row.profile_id}
                            </Link>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="py-2">
                          <Link
                            className="text-sky-300 hover:underline"
                            to={row.tab_href || `/eval?tab=${row.tab_id || ''}`}
                          >
                            {row.tab_id || '—'}
                          </Link>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="py-2 text-gray-500" colSpan={11}>
                        —
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
