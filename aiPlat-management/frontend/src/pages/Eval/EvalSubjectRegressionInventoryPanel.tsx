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
  pack_id?: string;
  pack_version?: string;
  pack_status?: string;
  quota_inventory_ok?: boolean;
  profile_complete?: boolean;
  case_count?: number;
  purpose_ok_or_better?: number;
  draft_pending?: number;
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
  };
};

type Props = { tenantId?: string };

export default function EvalSubjectRegressionInventoryPanel(_props: Props = {}) {
  const [loading, setLoading] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [error, setError] = useState('');
  const [promoteMsg, setPromoteMsg] = useState('');
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

  const rows = status?.subjects || [];
  const packsHref = status?.review_links?.case_packs_tab || '/eval?tab=case-packs';
  const methodHref = status?.review_links?.method_track_tab || '/eval?tab=method-track';
  const p1Href = status?.review_links?.p1_regression_tab || '/eval?tab=p1-regression';

  return (
    <div className="space-y-4 text-sm" data-testid="eval-subject-regression-inventory-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Subject Regression 总览诚实门（ADR）</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            subjects={status?.subject_count ?? '—'} · OBJECT_TYPES=
            {status?.object_type_subject_count ?? '—'} · quota_ok=
            {status?.quota_inventory_ok_count ?? '—'} · profile_complete=
            {status?.profile_complete_count ?? '—'} · draft_pending=
            {status?.draft_pending_total ?? '—'}
          </li>
          <li>
            claim_eligible={String(Boolean(status?.claim_eligible))} · accuracy_claim=
            {String(Boolean(status?.accuracy_claim))} · certification=
            {String(Boolean(status?.certification_eligible))}
          </li>
          <li>
            {status?.honesty ||
              '跨 Subject 配额盘点 ≠ claim；人审 purpose_ok/freeze 前不得宣称收口；Method 轨不在此表。'}
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
                {promoting ? 'Promoting…' : 'purpose_ok → freeze'}
              </button>
              <span className="text-gray-500">claim 仍关；仅工作区 registry 冻结</span>
            </div>
            {promoteMsg ? <p className="text-xs text-emerald-200/90">{promoteMsg}</p> : null}
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
                    <th className="py-1 pr-2">complete</th>
                    <th className="py-1 pr-2">draft</th>
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
                        <td className="py-2 pr-2">{String(Boolean(row.profile_complete))}</td>
                        <td className="py-2 pr-2">{row.draft_pending ?? 0}</td>
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
                      <td className="py-2 text-gray-500" colSpan={8}>
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
