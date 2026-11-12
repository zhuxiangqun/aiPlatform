/**
 * Case Pack P1 factory ops + P2 Suite Profile compile.
 * Honesty: claim_eligible stays false; frozen≠accuracy.
 */
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { agentEvalApi } from '../../services';

export default function EvalCasePackPanel() {
  const [params] = useSearchParams();
  const urlProfileId = String(params.get('profile_id') || '').trim();
  const [packId, setPackId] = useState('ws.demo.pack');
  const [version, setVersion] = useState('0.1.0');
  const [prompt, setPrompt] = useState('say ok');
  const [ticketId, setTicketId] = useState('');
  const [profileId, setProfileId] = useState(urlProfileId || 'agent.regression.v1');
  const [profileOptions, setProfileOptions] = useState<string[]>([
    urlProfileId || 'agent.regression.v1',
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (urlProfileId) setProfileId(urlProfileId);
  }, [urlProfileId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const out = await agentEvalApi.casePackSuiteProfiles();
        const rows = Array.isArray(out?.profiles) ? out.profiles : [];
        const ids = rows
          .map((p) =>
            p && typeof p === 'object'
              ? String((p as Record<string, unknown>).profile_id || '').trim()
              : '',
          )
          .filter(Boolean);
        if (!cancelled && ids.length) {
          setProfileOptions(ids);
          const preferred = urlProfileId && ids.includes(urlProfileId) ? urlProfileId : '';
          setProfileId((cur) => preferred || (ids.includes(cur) ? cur : ids[0]));
        }
      } catch (e) {
        // keep default profile id when suite-profiles unavailable
        if (!cancelled) {
          setMsg(
            `suite-profiles load skipped: ${e instanceof Error ? e.message : String(e)}`,
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [urlProfileId]);

  const run = useCallback(
    async (label: string, fn: () => Promise<Record<string, unknown>>) => {
      setBusy(true);
      setError('');
      setMsg('');
      setResult(null);
      try {
        const out = await fn();
        if (out && out.ok === false) {
          setError(String(out.error || out.message || `${label} failed`));
        } else {
          setMsg(`${label} ok · claim_eligible=${String(out?.claim_eligible ?? false)}`);
          if (typeof out?.ticket_id === 'string' && out.ticket_id.trim()) {
            setTicketId(out.ticket_id.trim());
          }
        }
        setResult(out);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const templateBody = () => ({
    pack_id: packId.trim(),
    version: version.trim(),
    template: {
      category: 'normal',
      rubric: { type: 'lexical', must_contain: ['ok'] },
      prompt: prompt.trim() || 'say ok',
    },
    variants: [{ case_id: `${packId.trim().split('.').pop() || 'c'}-1` }],
  });

  return (
    <div className="space-y-4 text-sm" data-testid="eval-case-pack-panel">
      <p className="text-slate-400">
        工作区 Case Pack 工厂链（draft → 人审 → freeze）。
        <span className="text-amber-300/90"> claim_eligible 恒 false；frozen ≠ 准确率宣称。</span>
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1">
          <span className="text-xs text-slate-500">pack_id</span>
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={packId}
            onChange={(e) => setPackId(e.target.value)}
            data-testid="eval-case-pack-id"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">version</span>
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            data-testid="eval-case-pack-version"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">template prompt</span>
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">suite profile</span>
          <select
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            data-testid="eval-case-pack-profile"
          >
            {profileOptions.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          className="rounded bg-slate-100 px-3 py-1.5 text-slate-900 disabled:opacity-50"
          data-testid="eval-case-pack-draft"
          onClick={() => run('draft', () => agentEvalApi.casePackDraft(templateBody()))}
        >
          Draft
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('enqueue', () =>
              agentEvalApi.casePackEnqueueReview({
                pack_id: packId.trim(),
                version: version.trim(),
              }),
            )
          }
        >
          Enqueue
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('approve', () =>
              agentEvalApi.casePackReview({
                pack_id: packId.trim(),
                version: version.trim(),
                decision: 'approve',
                reviewer: 'ui',
              }),
            )
          }
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('freeze', () =>
              agentEvalApi.casePackFreeze({
                pack_id: packId.trim(),
                version: version.trim(),
                frozen_by: 'ui',
              }),
            )
          }
        >
          Freeze
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-amber-700/60 px-3 py-1.5 text-amber-100 disabled:opacity-50"
          data-testid="eval-case-pack-promote-capability"
          onClick={() =>
            run('promote-capability', () =>
              agentEvalApi.casePackPromoteAgentCapability({
                reviewer: 'ui',
                frozen_by: 'ui',
                notes: 'P1 UI promote',
              }),
            )
          }
        >
          Promote agent.capability
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('expand', () =>
              agentEvalApi.casePackExpand({
                pack_id: packId.trim(),
                version: version.trim(),
                template: {
                  category: 'normal',
                  rubric: { type: 'lexical' },
                  prompt: `${prompt.trim()} extra`,
                },
                variants: [{ case_id: `x-${Date.now()}` }],
              }),
            )
          }
        >
          Expand
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('bump', () =>
              agentEvalApi.casePackBump({
                pack_id: packId.trim(),
                from_version: version.trim(),
              }),
            )
          }
        >
          version++
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-emerald-700/60 px-3 py-1.5 text-emerald-200 disabled:opacity-50"
          data-testid="eval-case-pack-coverage"
          onClick={() => run('coverage', () => agentEvalApi.casePackCoverage())}
        >
          Coverage
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-sky-700/60 px-3 py-1.5 text-sky-100 disabled:opacity-50"
          data-testid="eval-case-pack-compile-profile"
          onClick={() =>
            run('compile-profile', () =>
              agentEvalApi.casePackCompileSuiteProfile({
                profile_id: profileId.trim() || 'agent.regression.v1',
              }),
            )
          }
        >
          Compile Profile → Plan
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-sky-700/60 px-3 py-1.5 text-sky-100 disabled:opacity-50"
          data-testid="eval-case-pack-run-profile"
          onClick={() =>
            run('run-profile', () =>
              agentEvalApi.casePackRunSuiteProfile({
                profile_id: profileId.trim() || 'agent.regression.v1',
                live: false,
              }),
            )
          }
        >
          Run Profile (dry)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-orange-700/60 px-3 py-1.5 text-orange-100 disabled:opacity-50"
          data-testid="eval-case-pack-run-profile-live"
          onClick={() =>
            run('run-profile-live', () =>
              agentEvalApi.casePackRunSuiteProfile({
                profile_id: profileId.trim() || 'agent.smoke.v1',
                live: true,
                max_cases: 4,
              }),
            )
          }
        >
          Run Profile (live·smoke·4)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-sky-700/60 px-3 py-1.5 text-sky-100 disabled:opacity-50"
          data-testid="eval-case-pack-heatmap"
          onClick={() =>
            run('capability-heatmap', () =>
              agentEvalApi.casePackCapabilityHeatmap({
                profile_id: profileId.trim() || 'agent.regression.v1',
                exam:
                  result && result.report
                    ? (result as Record<string, unknown>)
                    : result || undefined,
              }),
            )
          }
        >
          Coverage heatmap
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-rose-700/60 px-3 py-1.5 text-rose-100 disabled:opacity-50"
          data-testid="eval-case-pack-cert-ready"
          onClick={() =>
            run('certification-readiness', () =>
              agentEvalApi.casePackCertificationReadiness({
                profile_id: profileId.trim() || 'agent.benchmark.v1',
                pack_kind: 'frozen',
                pack_status: 'active',
                compile_plan: true,
              }),
            )
          }
        >
          Cert readiness (pre-P5)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-violet-700/60 px-3 py-1.5 text-violet-100 disabled:opacity-50"
          data-testid="eval-case-pack-cap-coverage"
          onClick={() =>
            run('capability-coverage', () =>
              agentEvalApi.casePackCapabilityCoverage({
                profile_id: profileId.trim() || 'agent.regression.v1',
                min_per_capability: 8,
              }),
            )
          }
        >
          Cap coverage (min=8)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-violet-700/60 px-3 py-1.5 text-violet-100 disabled:opacity-50"
          data-testid="eval-case-pack-coverage-fill-dry"
          onClick={() =>
            run('coverage-fill-dry', () =>
              agentEvalApi.casePackCoverageFill({
                pack_id: packId.trim(),
                version: version.trim(),
                profile_id: profileId.trim() || 'agent.regression.v1',
                min_per_capability: 8,
                method: 'mutation',
                apply: false,
              }),
            )
          }
        >
          Coverage fill (dry)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-violet-700/60 px-3 py-1.5 text-violet-100 disabled:opacity-50"
          data-testid="eval-case-pack-coverage-fill-apply"
          onClick={() =>
            run('coverage-fill-apply', () =>
              agentEvalApi.casePackCoverageFill({
                pack_id: packId.trim(),
                version: version.trim(),
                profile_id: profileId.trim() || 'agent.regression.v1',
                min_per_capability: 8,
                method: 'mutation',
                apply: true,
              }),
            )
          }
        >
          Coverage fill (apply)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-fuchsia-700/60 px-3 py-1.5 text-fuchsia-100 disabled:opacity-50"
          data-testid="eval-case-pack-benchmark-ready"
          onClick={() =>
            run('benchmark-readiness', () =>
              agentEvalApi.casePackBenchmarkReadiness({
                min_per_capability: 8,
                compile_plan: true,
              }),
            )
          }
        >
          Benchmark readiness
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-fuchsia-700/60 px-3 py-1.5 text-fuchsia-100 disabled:opacity-50"
          data-testid="eval-case-pack-open-judge-cal"
          onClick={() =>
            run('open-judge-cal', () =>
              agentEvalApi.casePackOpenCapabilityJudgeCalibration({
                pack_id: packId.trim(),
                version: version.trim(),
                sample_n: 8,
              }),
            )
          }
        >
          Open judge calibration
        </button>
        <button
          type="button"
          disabled={busy || !ticketId.trim()}
          className="rounded border border-fuchsia-700/60 px-3 py-1.5 text-fuchsia-100 disabled:opacity-50"
          data-testid="eval-case-pack-judge-gate"
          onClick={() =>
            run('judge-gate', () =>
              agentEvalApi.casePackJudgeCalibrationGate({
                ticket_id: ticketId.trim(),
                threshold: 0.8,
              }),
            )
          }
        >
          Judge gate
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('holdout', () =>
              agentEvalApi.casePackHoldout({
                pack_id: packId.trim(),
                version: version.trim(),
                ratio: 0.5,
                seed: 'ui',
              }),
            )
          }
        >
          Holdout 50%
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          data-testid="eval-case-pack-mutate"
          onClick={() =>
            run('mutate', () =>
              agentEvalApi.casePackMutate({
                pack_id: `${packId.trim()}.mut`,
                version: version.trim(),
                seed: 'ui',
                ops: ['append_noise'],
                seed_cases: [
                  {
                    case_id: 'seed-ui',
                    prompt: prompt.trim() || 'say ok',
                    rubric: { type: 'lexical', must_contain: ['ok'] },
                    category: 'normal',
                  },
                ],
              }),
            )
          }
        >
          Mutate→generated
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('from-trace', () =>
              agentEvalApi.casePackFromTrace({
                pack_id: `${packId.trim()}.trace`,
                version: version.trim(),
                traces: [
                  {
                    prompt: prompt.trim() || 'say ok',
                    tool_calls: [{ name: 'demo_tool' }],
                    must_contain: ['ok'],
                  },
                ],
              }),
            )
          }
        >
          From-trace
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-violet-700/60 px-3 py-1.5 text-violet-200 disabled:opacity-50"
          data-testid="eval-case-pack-llm"
          onClick={() =>
            run('llm-candidates', () =>
              agentEvalApi.casePackLlmCandidates({
                pack_id: `${packId.trim()}.llm`,
                version: version.trim(),
                theme: prompt.trim() || 'agent smoke',
                n: 2,
                seed: 'ui',
                dry: true,
              }),
            )
          }
        >
          LLM candidates (dry)
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('propose-difficulty', () =>
              agentEvalApi.casePackProposeDifficulty({
                pack_id: packId.trim(),
                version: version.trim(),
                persist: false,
              }),
            )
          }
        >
          Propose difficulty
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('judge-ticket', () =>
              agentEvalApi.casePackJudgeCalibrationTicket({
                pack_id: packId.trim(),
                version: version.trim(),
                notes: 'ui open',
              }),
            )
          }
        >
          Judge ticket
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded border border-amber-700/60 px-3 py-1.5 text-amber-200 disabled:opacity-50"
          data-testid="eval-case-pack-calibrate-diff"
          onClick={() =>
            run('calibrate-difficulty', () =>
              agentEvalApi.casePackCalibrateDifficulty({
                pack_id: packId.trim(),
                version: version.trim(),
                rater: 'ui',
                labels: [
                  {
                    case_id: `${packId.trim().split('.').pop() || 'c'}-1`,
                    difficulty: 'medium',
                  },
                ],
              }),
            )
          }
        >
          Calibrate difficulty
        </button>
        <button
          type="button"
          disabled={busy || !ticketId.trim()}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('judge-rate', () =>
              agentEvalApi.casePackJudgeCalibrationRatings({
                ticket_id: ticketId.trim(),
                rater: 'ui-a',
                ratings: [
                  {
                    case_id: `${packId.trim().split('.').pop() || 'c'}-1`,
                    score: 1,
                    rater: 'ui-a',
                  },
                  {
                    case_id: `${packId.trim().split('.').pop() || 'c'}-1`,
                    score: 1,
                    rater: 'ui-b',
                  },
                ],
              }),
            )
          }
        >
          Judge rate
        </button>
        <button
          type="button"
          disabled={busy || !ticketId.trim()}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={() =>
            run('judge-close', () =>
              agentEvalApi.casePackJudgeCalibrationClose({
                ticket_id: ticketId.trim(),
                notes: 'ui close',
              }),
            )
          }
        >
          Judge close
        </button>
        {busy ? <Loader2 className="h-4 w-4 animate-spin self-center text-slate-400" /> : null}
      </div>

      {msg ? <p className="text-emerald-300/90">{msg}</p> : null}
      {error ? <p className="text-red-300">{error}</p> : null}

      {result && typeof result.report === 'object' && result.report ? (
        <div
          className="space-y-3 rounded border border-slate-800 bg-slate-950/60 p-3"
          data-testid="eval-case-pack-report"
        >
          {(() => {
            const report = result.report as Record<string, unknown>;
            const disc =
              report.disclosure && typeof report.disclosure === 'object'
                ? (report.disclosure as Record<string, unknown>)
                : {};
            const heat =
              report.heatmap && typeof report.heatmap === 'object'
                ? (report.heatmap as Record<string, unknown>)
                : {};
            const rows = Array.isArray(heat.rows) ? heat.rows : [];
            const unknown = Array.isArray(heat.unknown_capabilities)
              ? heat.unknown_capabilities
              : [];
            return (
              <>
                <div className="text-xs text-slate-400 space-y-1">
                  <div>
                    profile=<span className="text-slate-200">{String(disc.profile_id || '—')}</span>
                    {' · '}
                    claim_eligible=
                    <span className="text-amber-200">{String(disc.claim_eligible ?? false)}</span>
                    {' · '}
                    live=<span className="text-slate-200">{String(disc.live ?? false)}</span>
                  </div>
                  <div className="truncate">
                    manifest_hash={String(disc.manifest_hash || '—')}
                  </div>
                  <div className="truncate">
                    execution_fingerprint={String(disc.execution_fingerprint || '—')}
                  </div>
                </div>
                <div className="overflow-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="py-1 pr-2">capability</th>
                        <th className="py-1 pr-2">cases</th>
                        <th className="py-1 pr-2">need</th>
                        <th className="py-1 pr-2">selected</th>
                        <th className="py-1 pr-2">pass</th>
                        <th className="py-1 pr-2">fail</th>
                        <th className="py-1 pr-2">gap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((raw) => {
                        const r = raw as Record<string, unknown>;
                        const gap = Number(r.gap || 0);
                        return (
                          <tr key={String(r.capability_id)} className="border-t border-slate-800">
                            <td className="py-1 pr-2 text-slate-200">{String(r.capability_id)}</td>
                            <td className="py-1 pr-2">{String(r.cases ?? 0)}</td>
                            <td className="py-1 pr-2">{String(r.need ?? 0)}</td>
                            <td className="py-1 pr-2">{String(r.selected ?? 0)}</td>
                            <td className="py-1 pr-2 text-emerald-300">{String(r.pass ?? 0)}</td>
                            <td className="py-1 pr-2 text-red-300">{String(r.fail ?? 0)}</td>
                            <td
                              className={`py-1 pr-2 ${gap > 0 ? 'text-amber-300' : 'text-slate-400'}`}
                            >
                              {gap}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {unknown.length ? (
                  <p className="text-xs text-slate-500">
                    unknown (out of scope):{' '}
                    {unknown
                      .map((u) =>
                        u && typeof u === 'object'
                          ? String((u as Record<string, unknown>).capability_id || '')
                          : '',
                      )
                      .filter(Boolean)
                      .join(', ')}
                  </p>
                ) : null}
              </>
            );
          })()}
        </div>
      ) : null}

      {result ? (
        <pre
          className="max-h-80 overflow-auto rounded border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-300"
          data-testid="eval-case-pack-result"
        >
          {JSON.stringify(result, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
