/**
 * UI-3 — Eval sets: list + create set + add task + gold import.
 * Honesty: maintaining a set ≠ accuracy claim. No update/delete API yet.
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

function unwrapList<T>(res: unknown): T[] {
  const body = res as { data?: { items?: T[] }; items?: T[] } & T[];
  if (Array.isArray(body?.data?.items)) return body.data!.items!;
  if (Array.isArray(body?.items)) return body.items!;
  if (Array.isArray(body?.data)) return body.data as T[];
  if (Array.isArray(body)) return body;
  return [];
}

type EvalSet = {
  id?: string;
  set_id?: string;
  name?: string;
  version?: string;
  split?: string;
  status?: string;
  updated_at?: string;
};

type EvalTask = {
  id?: string;
  set_id?: string;
  tags?: string[];
  source?: string;
  hard_negative?: boolean;
  created_at?: string;
};

type Props = { tenantId?: string };

const fieldClass =
  'w-full rounded border border-gray-600 bg-gray-950/60 px-2 py-1.5 text-xs text-gray-200 placeholder:text-gray-600';
const labelClass = 'block text-[11px] text-gray-500 mb-0.5';
const btnClass =
  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-xs text-gray-200 hover:bg-gray-800 disabled:opacity-50';

function parseJsonObject(raw: string, field: string): Record<string, unknown> {
  const t = raw.trim();
  if (!t) return {};
  let v: unknown;
  try {
    v = JSON.parse(t);
  } catch {
    throw new Error(`${field} 不是合法 JSON`);
  }
  if (v === null || typeof v !== 'object' || Array.isArray(v)) {
    throw new Error(`${field} 须为 JSON 对象`);
  }
  return v as Record<string, unknown>;
}

export default function EvalSetsPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [sets, setSets] = useState<EvalSet[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [tasks, setTasks] = useState<EvalTask[]>([]);
  const [tasksBusy, setTasksBusy] = useState(false);
  const [busy, setBusy] = useState(false);

  const [setName, setSetName] = useState('');
  const [setVersion, setSetVersion] = useState('0');
  const [setSplit, setSetSplit] = useState('dev');

  const [taskSource, setTaskSource] = useState('manual');
  const [taskTags, setTaskTags] = useState('');
  const [taskHardNeg, setTaskHardNeg] = useState(false);
  const [taskInput, setTaskInput] = useState('{\n  \n}');
  const [taskExpected, setTaskExpected] = useState('{\n  \n}');
  const [taskRubric, setTaskRubric] = useState('');

  const loadSets = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get(
        `/platform/apps/eval/store/sets?tenant_id=${encodeURIComponent(tenantId)}&limit=100`,
      );
      setSets(unwrapList<EvalSet>(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void loadSets();
  }, [loadSets]);

  const loadTasks = async (setId: string) => {
    const id = setId.trim();
    if (!id) return;
    setSelectedId(id);
    setTasksBusy(true);
    setTasks([]);
    try {
      const res = await apiClient.get(
        `/platform/apps/eval/store/tasks?set_id=${encodeURIComponent(id)}&tenant_id=${encodeURIComponent(tenantId)}&limit=100`,
      );
      setTasks(unwrapList<EvalTask>(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTasksBusy(false);
    }
  };

  const createSet = async () => {
    const name = setName.trim();
    if (!name) {
      setError('请填写 set name');
      return;
    }
    setBusy(true);
    setError('');
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<EvalSet & { error?: string }>>(
        `/platform/apps/eval/store/sets`,
        {
          name,
          version: setVersion.trim() || '0',
          split: setSplit.trim() || 'dev',
          tenant_id: tenantId,
        },
      );
      const row = unwrap(res);
      if ((row as { error?: string })?.error) {
        setError(String((row as { error?: string }).error));
        return;
      }
      const id = String(row.id || row.set_id || '');
      setMsg(`已创建 set ${id || name}`);
      setSetName('');
      await loadSets();
      if (id) await loadTasks(id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const createTask = async () => {
    if (!selectedId) {
      setError('请先选择或创建一个 set');
      return;
    }
    setBusy(true);
    setError('');
    setMsg('');
    try {
      const input = parseJsonObject(taskInput, 'input');
      const expected = parseJsonObject(taskExpected, 'expected');
      const rubric = taskRubric.trim()
        ? parseJsonObject(taskRubric, 'rubric')
        : undefined;
      const tags = taskTags
        .split(/[,，\s]+/)
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await apiClient.post<
        Envelope<EvalTask & { ok?: boolean; error?: string }>
      >(`/platform/apps/eval/store/tasks`, {
        set_id: selectedId,
        input,
        expected,
        rubric,
        tags,
        hard_negative: taskHardNeg,
        source: taskSource.trim() || 'manual',
        tenant_id: tenantId,
      });
      const row = unwrap(res);
      if (row?.ok === false || row?.error) {
        setError(String(row.error || 'create task failed'));
        return;
      }
      setMsg(`已追加 task ${row.id || ''}`);
      setTaskTags('');
      setTaskHardNeg(false);
      setTaskInput('{\n  \n}');
      setTaskExpected('{\n  \n}');
      setTaskRubric('');
      await loadTasks(selectedId);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runImport = async (kind: 'migrate' | 'bootstrap') => {
    setBusy(true);
    setError('');
    setMsg('');
    try {
      const path =
        kind === 'migrate'
          ? '/platform/apps/eval/store/migrate/code-review-gold'
          : '/platform/apps/eval/store/bootstrap-e3';
      const res = await apiClient.post<
        Envelope<{ ok?: boolean; error?: string; set_id?: string; imported?: number; task_count?: number }>
      >(path, { tenant_id: tenantId });
      const body = unwrap(res);
      if (body?.ok === false || body?.error) {
        setError(String(body.error || 'import failed'));
        return;
      }
      setMsg(
        kind === 'migrate'
          ? `已导入 code-review-gold · set=${body.set_id || '—'} · imported=${body.imported ?? '—'}`
          : `E3 bootstrap · set=${body.set_id || '—'} · tasks=${body.task_count ?? '—'}`,
      );
      await loadSets();
      if (body.set_id) await loadTasks(String(body.set_id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const setKey = (s: EvalSet) => String(s.id || s.set_id || '');

  return (
    <div className="space-y-4 text-sm" data-testid="eval-sets-panel">
      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">评测集维护</h2>
          <button
            type="button"
            onClick={() => void loadSets()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <p className="text-xs text-amber-200/90">
          可新建 set / 追加 task / 导入黄金集 · 尚无改删 API · 维护 ≠ accuracy
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="eval-sets-migrate-gold"
            disabled={busy}
            onClick={() => void runImport('migrate')}
            className={btnClass}
          >
            导入 code-review-gold
          </button>
          <button
            type="button"
            data-testid="eval-sets-bootstrap-e3"
            disabled={busy}
            onClick={() => void runImport('bootstrap')}
            className={btnClass}
          >
            Bootstrap E3（导入+复核队列）
          </button>
        </div>
        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {msg ? (
          <p className="text-gray-300 font-mono text-xs whitespace-pre-wrap" data-testid="eval-sets-msg">
            {msg}
          </p>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <h3 className="font-medium flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> 新建评测集
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div>
            <label className={labelClass} htmlFor="eval-set-name">
              name
            </label>
            <input
              id="eval-set-name"
              data-testid="eval-set-name"
              className={fieldClass}
              value={setName}
              onChange={(e) => setSetName(e.target.value)}
              placeholder="my-set"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="eval-set-version">
              version
            </label>
            <input
              id="eval-set-version"
              data-testid="eval-set-version"
              className={fieldClass}
              value={setVersion}
              onChange={(e) => setSetVersion(e.target.value)}
              placeholder="0"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="eval-set-split">
              split
            </label>
            <input
              id="eval-set-split"
              data-testid="eval-set-split"
              className={fieldClass}
              value={setSplit}
              onChange={(e) => setSetSplit(e.target.value)}
              placeholder="dev | gold"
            />
          </div>
        </div>
        <button
          type="button"
          data-testid="eval-set-create"
          disabled={busy}
          onClick={() => void createSet()}
          className={btnClass}
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
          创建 set
        </button>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <h3 className="font-medium">已有评测集</h3>
        {loading && sets.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : sets.length === 0 ? (
          <p className="text-gray-500">暂无 set。可新建或导入黄金集。</p>
        ) : (
          <ul className="divide-y divide-gray-800">
            {sets.map((s, i) => {
              const id = setKey(s);
              const active = id && id === selectedId;
              return (
                <li key={id || i} className="py-2 flex justify-between gap-3 items-center">
                  <button
                    type="button"
                    data-testid="eval-set-row"
                    onClick={() => void loadTasks(id)}
                    className={`text-left truncate hover:underline ${
                      active ? 'text-blue-200' : 'text-blue-300'
                    }`}
                  >
                    {s.name || id || `set-${i}`}
                    {s.version ? <span className="text-gray-500 ml-2">v{s.version}</span> : null}
                    {s.split ? <span className="text-gray-600 ml-2">{s.split}</span> : null}
                  </button>
                  <span className="text-gray-500 shrink-0 text-xs">{s.updated_at || s.status || '—'}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {selectedId ? (
        <>
          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
            <h3 className="font-medium">
              Tasks · <code className="text-blue-300">{selectedId}</code>
            </h3>
            {tasksBusy ? (
              <p className="text-gray-500 inline-flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> 加载 tasks…
              </p>
            ) : tasks.length === 0 ? (
              <p className="text-gray-500">该 set 无 task，可在下方追加。</p>
            ) : (
              <ul className="divide-y divide-gray-800 max-h-80 overflow-auto" data-testid="eval-set-tasks">
                {tasks.map((t, i) => (
                  <li
                    key={t.id || i}
                    className="py-1.5 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-300"
                  >
                    <span className="truncate font-mono">{t.id || `task-${i}`}</span>
                    <span className="truncate text-gray-500">{t.source || '—'}</span>
                    <span className="truncate">
                      {(t.tags || []).slice(0, 3).join(', ') || '—'}
                    </span>
                    <span className="text-gray-500">
                      {t.hard_negative ? 'hard_neg' : t.created_at || '—'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] text-gray-600">展示上限 100 · 无改删接口</p>
          </div>

          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
            <h3 className="font-medium flex items-center gap-1.5">
              <Plus className="w-4 h-4" /> 追加 task
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div>
                <label className={labelClass} htmlFor="eval-task-source">
                  source
                </label>
                <input
                  id="eval-task-source"
                  data-testid="eval-task-source"
                  className={fieldClass}
                  value={taskSource}
                  onChange={(e) => setTaskSource(e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="eval-task-tags">
                  tags（逗号分隔）
                </label>
                <input
                  id="eval-task-tags"
                  data-testid="eval-task-tags"
                  className={fieldClass}
                  value={taskTags}
                  onChange={(e) => setTaskTags(e.target.value)}
                  placeholder="demo, smoke"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="inline-flex items-center gap-2 text-xs text-gray-300">
                  <input
                    type="checkbox"
                    data-testid="eval-task-hard-neg"
                    checked={taskHardNeg}
                    onChange={(e) => setTaskHardNeg(e.target.checked)}
                  />
                  hard_negative
                </label>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <label className={labelClass} htmlFor="eval-task-input">
                  input (JSON object)
                </label>
                <textarea
                  id="eval-task-input"
                  data-testid="eval-task-input"
                  className={`${fieldClass} font-mono min-h-[100px]`}
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="eval-task-expected">
                  expected (JSON object)
                </label>
                <textarea
                  id="eval-task-expected"
                  data-testid="eval-task-expected"
                  className={`${fieldClass} font-mono min-h-[100px]`}
                  value={taskExpected}
                  onChange={(e) => setTaskExpected(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className={labelClass} htmlFor="eval-task-rubric">
                rubric (可选 JSON)
              </label>
              <textarea
                id="eval-task-rubric"
                data-testid="eval-task-rubric"
                className={`${fieldClass} font-mono min-h-[60px]`}
                value={taskRubric}
                onChange={(e) => setTaskRubric(e.target.value)}
                placeholder="{}"
              />
            </div>
            <button
              type="button"
              data-testid="eval-task-create"
              disabled={busy}
              onClick={() => void createTask()}
              className={btnClass}
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              追加 task
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
