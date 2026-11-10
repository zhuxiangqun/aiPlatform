/**
 * Skill Subject regression honesty — quotas may be complete; claim stays closed.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type DraftCapRow = {
  capability_id?: string;
  draft_count?: number;
  sample_case_ids?: string[];
};

type GapRow = {
  capability_id?: string;
  quota?: number;
  have?: number;
};

type SkillRegStatus = {
  ok?: boolean;
  profile_id?: string;
  pack_id?: string;
  pack_version?: string;
  pack_status?: string;
  quota_inventory_ok?: boolean;
  profile_complete?: boolean;
  case_count?: number;
  purpose_ok_or_better?: number;
  draft_pending?: number;
  quotas?: Record<string, number>;
  counts_by_capability?: Record<string, number>;
  gaps?: GapRow[];
  draft_by_capability?: DraftCapRow[];
  review_status_counts?: Record<string, number>;
  next_action?: string;
  review_links?: {
    case_packs_tab?: string;
    skills_tab?: string;
    prompt_regression_tab?: string;
  };
  accuracy_claim?: boolean;
  claim_eligible?: boolean;
  certification_eligible?: boolean;
  honesty?: string;
};

type Props = { tenantId?: string };

export default function EvalSkillRegressionPanel(_props: Props = {}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<SkillRegStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<SkillRegStatus>>(
        `/platform/apps/eval/store/skill-regression-status`,
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

  const reviews = status?.review_status_counts || {};
  const gaps = status?.gaps || [];
  const drafts = status?.draft_by_capability || [];
  const quotas = status?.quotas || {};
  const counts = status?.counts_by_capability || {};
  const packsHref = status?.review_links?.case_packs_tab || '/eval?tab=case-packs';
  const skillsHref = status?.review_links?.skills_tab || '/eval?tab=skills';
  const promptHref =
    status?.review_links?.prompt_regression_tab || '/eval?tab=prompt-regression';

  return (
    <div className="space-y-4 text-sm" data-testid="eval-skill-regression-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Skill Regression 诚实门（ADR）</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            配额盘点：{status?.quota_inventory_ok ? '齐' : '缺口'} · profile_complete=
            {String(Boolean(status?.profile_complete))} · pack=
            {status?.pack_status || '—'}
          </li>
          <li>
            claim_eligible={String(Boolean(status?.claim_eligible))} · accuracy_claim=
            {String(Boolean(status?.accuracy_claim))} · certification=
            {String(Boolean(status?.certification_eligible))}
          </li>
          <li>
            {status?.honesty ||
              'lexical fixture ≠ live core_skill_execute；人审 purpose_ok/freeze 前不得宣称收口。'}
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">
            {status?.profile_id || 'skill.regression.v1'} · 就绪快照
          </h2>
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
            <p className="text-xs text-gray-400">
              {status.pack_id || 'skill.capability'}@{status.pack_version || '—'} · cases=
              {status.case_count ?? '—'} · purpose_ok+=
              {status.purpose_ok_or_better ?? 0} · draft_pending=
              {status.draft_pending ?? '—'}
            </p>
            <p className="text-xs text-sky-200/90">下一步：{status.next_action}</p>
            <div className="flex flex-wrap gap-3 text-xs">
              <Link className="text-sky-300 hover:underline" to={packsHref}>
                打开 Case Pack
              </Link>
              <Link className="text-sky-300 hover:underline" to={skillsHref}>
                打开评测 Skill
              </Link>
              <Link className="text-sky-300 hover:underline" to={promptHref}>
                对照 Prompt Regression
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-700">
                    <th className="py-1 pr-2">capability</th>
                    <th className="py-1 pr-2">quota</th>
                    <th className="py-1">have</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(quotas).length ? (
                    Object.keys(quotas)
                      .sort()
                      .map((cap) => (
                        <tr key={cap} className="border-b border-gray-800">
                          <td className="py-2 pr-2 font-mono">{cap}</td>
                          <td className="py-2 pr-2">{quotas[cap]}</td>
                          <td className="py-2">{counts[cap] ?? 0}</td>
                        </tr>
                      ))
                  ) : (
                    <tr>
                      <td className="py-2 text-gray-500" colSpan={3}>
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

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-2">
        <h2 className="font-medium">Gaps / review</h2>
        {gaps.length ? (
          <ul className="list-disc pl-5 text-xs text-amber-200">
            {gaps.map((g) => (
              <li key={g.capability_id}>
                {g.capability_id}: have={g.have ?? 0} / quota={g.quota ?? 0}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-gray-400">无配额缺口（仍不开放 claim）。</p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-700">
                <th className="py-1 pr-2">review.status</th>
                <th className="py-1">count</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(reviews).length ? (
                Object.entries(reviews).map(([k, v]) => (
                  <tr key={k} className="border-b border-gray-800">
                    <td className="py-2 pr-2 font-mono">{k}</td>
                    <td className="py-2">{v}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-2 text-gray-500" colSpan={2}>
                    —
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-700">
                <th className="py-1 pr-2">capability</th>
                <th className="py-1 pr-2">draft</th>
                <th className="py-1">sample case_ids</th>
              </tr>
            </thead>
            <tbody>
              {drafts.length ? (
                drafts.map((row) => (
                  <tr
                    key={row.capability_id}
                    className="border-b border-gray-800 align-top"
                  >
                    <td className="py-2 pr-2 font-mono">{row.capability_id}</td>
                    <td className="py-2 pr-2">{row.draft_count ?? 0}</td>
                    <td className="py-2 text-gray-300 font-mono">
                      {(row.sample_case_ids || []).join(', ') || '—'}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-2 text-gray-500" colSpan={3}>
                    无 draft
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
