/**
 * Case Pack P1 factory ops (draft → review → freeze + expand/bump/coverage).
 * Honesty: claim_eligible stays false; frozen≠accuracy.
 */
import { useCallback, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { agentEvalApi } from '../../services';

export default function EvalCasePackPanel() {
  const [packId, setPackId] = useState('ws.demo.pack');
  const [version, setVersion] = useState('0.1.0');
  const [prompt, setPrompt] = useState('say ok');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

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

      <div className="grid gap-3 sm:grid-cols-3">
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
        {busy ? <Loader2 className="h-4 w-4 animate-spin self-center text-slate-400" /> : null}
      </div>

      {msg ? <p className="text-emerald-300/90">{msg}</p> : null}
      {error ? <p className="text-red-300">{error}</p> : null}
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
