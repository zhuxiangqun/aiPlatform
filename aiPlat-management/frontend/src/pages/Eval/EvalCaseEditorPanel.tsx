/**
 * Capability Case Editor — browse seeds + edit workspace draft cases.
 * Honesty: claim_eligible stays false; frozen packs require bump.
 */
import { useCallback, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { agentEvalApi } from '../../services';
import EvalNamedWorkspacePicker from './EvalNamedWorkspacePicker';

type CaseSummary = {
  case_id?: string;
  capability_id?: string;
  prompt_preview?: string;
  review_status?: string;
  purpose_summary?: string;
};

const CAPS = [
  '',
  'clarification',
  'task_completion',
  'safety',
  'error_recovery',
  'robustness',
  'planning',
  'efficiency',
  'observability',
];

function emptyCase(capability = 'clarification'): Record<string, unknown> {
  return {
    case_id: `agent.${capability}.new001`,
    capabilities: [capability],
    category: capability,
    prompt: '',
    difficulty: 'medium',
    risk_level: 'low',
    rubric: { type: 'lexical', must_contain: [''], must_not_contain: [] },
    test_purpose: {
      summary: '',
      why_this_case: '',
      expected_behavior: [''],
      failure_signals: [''],
      not_testing: [''],
      oracle_rationale: 'lexical must_contain / must_not',
    },
    requires: { capabilities: [capability] },
    object_types: ['agent'],
    applies_to: { object_types: ['agent'] },
    oracle: { type: 'lexical' },
    expected_tools: [],
    forbidden_tools: [],
    expected_steps: [],
    holdout: false,
    tags: ['agent', capability, 'case_editor'],
    review: { status: 'draft', notes: 'ui new case' },
  };
}

export default function EvalCaseEditorPanel() {
  const [packId, setPackId] = useState('agent.capability');
  const [version, setVersion] = useState('0.1.0');
  const [source, setSource] = useState<'seed' | 'workspace'>('seed');
  const [capFilter, setCapFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [editable, setEditable] = useState(false);
  const [rows, setRows] = useState<CaseSummary[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [draftJson, setDraftJson] = useState('');

  const packOpts = useMemo(
    () => ({ pack_id: packId.trim(), version: version.trim() }),
    [packId, version],
  );

  const run = useCallback(async (label: string, fn: () => Promise<Record<string, unknown>>) => {
    setBusy(true);
    setError('');
    setMsg('');
    try {
      const out = await fn();
      if (out && out.ok === false) {
        setError(String(out.error || out.message || `${label} failed`));
      } else {
        setMsg(
          `${label} ok · editable=${String(out?.editable ?? '')} · claim=${String(out?.claim_eligible ?? false)}`,
        );
        if (typeof out?.version === 'string' && out.version.trim()) {
          setVersion(out.version.trim());
        }
      }
      return out;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshList = useCallback(async () => {
    const out =
      source === 'seed'
        ? await run('seed-list', () => agentEvalApi.caseEditorSeedList(capFilter || undefined))
        : await run('workspace-list', () =>
            agentEvalApi.caseEditorList({
              ...packOpts,
              capability_id: capFilter || undefined,
            }),
          );
    if (!out || out.ok === false) return;
    const list = Array.isArray(out.cases) ? (out.cases as CaseSummary[]) : [];
    setRows(list);
    setEditable(Boolean(out.editable));
  }, [capFilter, packOpts, run, source]);

  const openDraft = useCallback(async () => {
    const out = await run('open-editor', () =>
      agentEvalApi.caseEditorOpen({ ...packOpts, bump_if_frozen: true }),
    );
    if (!out || out.ok === false) return;
    setSource('workspace');
    setEditable(Boolean(out.editable));
    await refreshList();
  }, [packOpts, refreshList, run]);

  const loadCase = useCallback(
    async (caseId: string) => {
      setSelectedId(caseId);
      const out =
        source === 'seed'
          ? await run('seed-get', () => agentEvalApi.caseEditorSeedGet(caseId))
          : await run('workspace-get', () => agentEvalApi.caseEditorGet(caseId, packOpts));
      if (!out || out.ok === false) return;
      const c = out.case;
      setDraftJson(JSON.stringify(c && typeof c === 'object' ? c : {}, null, 2));
      if (source === 'workspace') setEditable(Boolean(out.editable));
    },
    [packOpts, run, source],
  );

  const saveCase = useCallback(async () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(draftJson) as Record<string, unknown>;
    } catch (e) {
      setError(`JSON 无效: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    const out = await run('upsert', () =>
      agentEvalApi.caseEditorUpsert({ ...packOpts, case: parsed }),
    );
    if (!out || out.ok === false) return;
    setSource('workspace');
    await refreshList();
  }, [draftJson, packOpts, refreshList, run]);

  const deleteCase = useCallback(async () => {
    if (!selectedId.trim()) return;
    const out = await run('delete', () =>
      agentEvalApi.caseEditorDelete({ ...packOpts, case_id: selectedId.trim() }),
    );
    if (!out || out.ok === false) return;
    setDraftJson('');
    setSelectedId('');
    await refreshList();
  }, [packOpts, refreshList, run, selectedId]);

  const newCase = useCallback(() => {
    const cap = capFilter || 'clarification';
    setSelectedId('');
    setDraftJson(JSON.stringify(emptyCase(cap), null, 2));
    setSource('workspace');
  }, [capFilter]);

  return (
    <div className="space-y-4 text-sm" data-testid="eval-case-editor-panel">
      <p className="text-slate-400">
        题目维护：种子只读浏览；可编辑对象是当前命名工作区的 draft pack。
        <span className="text-amber-300/90">
          {' '}
          不直接改 git seeds；frozen 需 bump；claim_eligible 恒 false。
        </span>
      </p>

      <EvalNamedWorkspacePicker onChange={() => setMsg('workspace switched')} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="space-y-1">
          <span className="text-xs text-slate-500">source</span>
          <select
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={source}
            onChange={(e) => setSource(e.target.value as 'seed' | 'workspace')}
            data-testid="eval-case-editor-source"
          >
            <option value="seed">seed (read-only)</option>
            <option value="workspace">workspace draft</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">pack_id</span>
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={packId}
            onChange={(e) => setPackId(e.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">version</span>
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            data-testid="eval-case-editor-version"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">capability filter</span>
          <select
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
            value={capFilter}
            onChange={(e) => setCapFilter(e.target.value)}
          >
            {CAPS.map((c) => (
              <option key={c || 'all'} value={c}>
                {c || '(all)'}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded bg-slate-100 px-3 py-1.5 text-slate-900 disabled:opacity-50"
            data-testid="eval-case-editor-refresh"
            onClick={() => void refreshList()}
          >
            Refresh
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded border border-amber-700/60 px-3 py-1.5 text-amber-100 disabled:opacity-50"
            data-testid="eval-case-editor-open"
            onClick={() => void openDraft()}
          >
            Open draft
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50"
          onClick={newCase}
        >
          New case JSON
        </button>
        <button
          type="button"
          disabled={busy || !editable}
          className="rounded border border-emerald-700/60 px-3 py-1.5 text-emerald-100 disabled:opacity-40"
          data-testid="eval-case-editor-save"
          onClick={() => void saveCase()}
        >
          Save upsert
        </button>
        <button
          type="button"
          disabled={busy || !editable || !selectedId}
          className="rounded border border-rose-800/60 px-3 py-1.5 text-rose-100 disabled:opacity-40"
          data-testid="eval-case-editor-delete"
          onClick={() => void deleteCase()}
        >
          Delete
        </button>
        {busy ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : null}
      </div>

      {error ? <p className="text-rose-300">{error}</p> : null}
      {msg ? <p className="text-slate-400">{msg}</p> : null}
      <p className="text-xs text-slate-500">
        editable={String(editable)} · rows={rows.length} · selected={selectedId || '—'}
      </p>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="max-h-[28rem] overflow-auto rounded border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-950 text-slate-500">
              <tr>
                <th className="px-2 py-1">case_id</th>
                <th className="px-2 py-1">cap</th>
                <th className="px-2 py-1">preview</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const id = String(r.case_id || '');
                return (
                  <tr
                    key={id}
                    className={`cursor-pointer border-t border-slate-800 hover:bg-slate-900/60 ${
                      selectedId === id ? 'bg-slate-900' : ''
                    }`}
                    onClick={() => void loadCase(id)}
                  >
                    <td className="px-2 py-1 font-mono text-slate-200">{id}</td>
                    <td className="px-2 py-1 text-slate-400">{String(r.capability_id || '')}</td>
                    <td className="px-2 py-1 text-slate-500">
                      {String(r.prompt_preview || r.purpose_summary || '').slice(0, 48)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <textarea
          className="min-h-[28rem] w-full rounded border border-slate-700 bg-slate-950 p-2 font-mono text-xs text-slate-200"
          value={draftJson}
          onChange={(e) => setDraftJson(e.target.value)}
          spellCheck={false}
          data-testid="eval-case-editor-json"
          placeholder="选择题目或 New case JSON"
        />
      </div>
    </div>
  );
}
