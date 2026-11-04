/**
 * UI-3 — Sets browser: list eval sets + expand tasks for selected set.
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
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

export default function EvalSetsPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sets, setSets] = useState<EvalSet[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [tasks, setTasks] = useState<EvalTask[]>([]);
  const [tasksBusy, setTasksBusy] = useState(false);

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

  const setKey = (s: EvalSet) => String(s.id || s.set_id || '');

  return (
    <div className="space-y-4 text-sm" data-testid="eval-sets-panel">
      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">评测集</h2>
          <button
            type="button"
            onClick={() => void loadSets()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {loading && sets.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : sets.length === 0 ? (
          <p className="text-gray-500">暂无 set。</p>
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
        <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
          <h3 className="font-medium">
            Tasks · <code className="text-blue-300">{selectedId}</code>
          </h3>
          {tasksBusy ? (
            <p className="text-gray-500 inline-flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> 加载 tasks…
            </p>
          ) : tasks.length === 0 ? (
            <p className="text-gray-500">该 set 无 task（或未返回）。</p>
          ) : (
            <ul className="divide-y divide-gray-800 max-h-80 overflow-auto" data-testid="eval-set-tasks">
              {tasks.map((t, i) => (
                <li key={t.id || i} className="py-1.5 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-300">
                  <span className="truncate font-mono">{t.id || `task-${i}`}</span>
                  <span className="truncate text-gray-500">{t.source || '—'}</span>
                  <span className="truncate">
                    {(t.tags || []).slice(0, 3).join(', ') || '—'}
                  </span>
                  <span className="text-gray-500">{t.hard_negative ? 'hard_neg' : t.created_at || '—'}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-[11px] text-gray-600">展示上限 100 · 只读</p>
        </div>
      ) : null}
    </div>
  );
}
