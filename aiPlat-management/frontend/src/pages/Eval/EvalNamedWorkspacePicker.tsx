/**
 * Named workspace selector — local Agent/eval_results partition + remote Core profiles.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import {
  NAMED_WORKSPACE_BOUNDARY,
  REMOTE_CORE_BOUNDARY,
  getStoredNamedWorkspaceId,
  getStoredNamedWorkspaceKind,
  setStoredNamedWorkspaceId,
  type NamedWorkspaceKind,
} from './namedWorkspace';

type WsItem = {
  id: string;
  label?: string;
  kind?: string;
  base_url_host?: string | null;
  active?: boolean;
};

type Props = {
  onChange?: (workspaceId: string, kind?: NamedWorkspaceKind) => void;
};

export default function EvalNamedWorkspacePicker({ onChange }: Props) {
  const [items, setItems] = useState<WsItem[]>([]);
  const [value, setValue] = useState(() => getStoredNamedWorkspaceId());
  const [boundary, setBoundary] = useState(NAMED_WORKSPACE_BOUNDARY);
  const [remoteBoundary, setRemoteBoundary] = useState(REMOTE_CORE_BOUNDARY);
  const [err, setErr] = useState('');
  const [creating, setCreating] = useState(false);
  const [remoteBase, setRemoteBase] = useState('http://127.0.0.1:8000');
  const abortRef = useRef<AbortController | null>(null);

  const kindOf = (id: string, list: WsItem[]): NamedWorkspaceKind => {
    const row = list.find((x) => x.id === id);
    return row?.kind === 'remote' ? 'remote' : 'local';
  };

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const res = await apiClient.get<{
        items?: WsItem[];
        current_workspace_id?: string;
        phase1_boundary?: string;
        remote_boundary?: string;
      }>('/core/workspaces', { signal: ac.signal });
      if (ac.signal.aborted) return;
      const list = Array.isArray(res?.items) ? res.items : [];
      setItems(list);
      if (res?.phase1_boundary) setBoundary(String(res.phase1_boundary));
      if (res?.remote_boundary) setRemoteBoundary(String(res.remote_boundary));
      const cur = getStoredNamedWorkspaceId();
      if (list.length && !list.some((x) => x.id === cur)) {
        const next = list[0].id;
        const k = kindOf(next, list);
        setStoredNamedWorkspaceId(next, k);
        setValue(next);
        onChange?.(next, k);
      } else {
        const k = kindOf(cur, list);
        setStoredNamedWorkspaceId(cur, k);
        setValue(cur);
      }
      setErr('');
    } catch (e: unknown) {
      if (ac.signal.aborted) return;
      setErr(e instanceof Error ? e.message : String(e));
      setItems([{ id: 'default', label: 'Default', kind: 'local' }]);
    }
  }, [onChange]);

  useEffect(() => {
    void load();
    return () => abortRef.current?.abort();
  }, [load]);

  const pick = (id: string) => {
    abortRef.current?.abort();
    const k = kindOf(id, items);
    setStoredNamedWorkspaceId(id, k);
    setValue(id);
    onChange?.(id, k);
  };

  const createLocal = async () => {
    const id = `ws_${Date.now().toString(36).slice(-6)}`;
    setCreating(true);
    try {
      setStoredNamedWorkspaceId(getStoredNamedWorkspaceId() || 'default', 'local');
      await apiClient.post('/core/workspaces', {
        workspace_id: id,
        label: id,
        kind: 'local',
      });
      setStoredNamedWorkspaceId(id, 'local');
      setValue(id);
      onChange?.(id, 'local');
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  const createRemote = async () => {
    const id = `remote_${Date.now().toString(36).slice(-6)}`;
    const base = remoteBase.trim();
    if (!base) {
      setErr('远程 Core 需要 base_url');
      return;
    }
    setCreating(true);
    try {
      setStoredNamedWorkspaceId('default', 'local');
      await apiClient.post('/core/workspaces', {
        workspace_id: id,
        label: id,
        kind: 'remote',
        base_url: base,
      });
      setStoredNamedWorkspaceId(id, 'remote');
      setValue(id);
      onChange?.(id, 'remote');
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  const selectedKind = kindOf(value, items) || getStoredNamedWorkspaceKind();

  return (
    <div
      className="rounded-lg border border-sky-800/40 bg-sky-950/20 px-3 py-2 text-xs text-sky-100/90 space-y-2"
      data-testid="eval-named-workspace-picker"
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="space-y-1 flex-1 min-w-[12rem]">
          <span className="text-[11px] text-sky-200/70">命名工作区 / 远程 Core</span>
          <select
            data-testid="eval-named-workspace-select"
            className="w-full h-9 rounded border border-sky-700/50 bg-gray-950 px-2 text-xs text-gray-200"
            value={value}
            onChange={(e) => pick(e.target.value)}
          >
            {items.length === 0 ? <option value="default">default</option> : null}
            {items.map((w) => (
              <option key={w.id} value={w.id}>
                {w.kind === 'remote' ? '[remote] ' : ''}
                {w.label || w.id}
                {w.kind === 'remote' && w.base_url_host
                  ? ` · ${w.base_url_host}`
                  : ''}{' '}
                ({w.id})
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={creating}
          onClick={() => void createLocal()}
          className="h-9 px-3 rounded border border-sky-600/60 text-sky-100 hover:bg-sky-950/50 disabled:opacity-50"
        >
          {creating ? '创建中…' : '新建本机空工作区'}
        </button>
      </div>
      <details className="rounded border border-sky-800/40 bg-black/20 p-2">
        <summary className="cursor-pointer text-sky-100/90">登记远程 Core 档案</summary>
        <div className="mt-2 flex flex-wrap gap-2 items-center">
          <input
            data-testid="eval-remote-base-url"
            className="h-8 flex-1 min-w-[14rem] rounded border border-gray-600 bg-gray-950 px-2 text-xs"
            placeholder="http(s)://remote-core-host:port"
            value={remoteBase}
            onChange={(e) => setRemoteBase(e.target.value)}
          />
          <button
            type="button"
            data-testid="eval-remote-register"
            disabled={creating}
            onClick={() => void createRemote()}
            className="h-8 px-3 rounded border border-amber-600/60 text-amber-100 hover:bg-amber-950/40 disabled:opacity-50"
          >
            登记远程（私网需 AIPLAT_REMOTE_CORE_ALLOW_PRIVATE=1）
          </button>
        </div>
      </details>
      <p className="text-[11px] text-sky-100/70 leading-relaxed">{boundary}</p>
      {selectedKind === 'remote' ? (
        <p className="text-[11px] text-amber-100/80 leading-relaxed" data-testid="eval-remote-boundary">
          {remoteBoundary}
        </p>
      ) : null}
      <p className="text-[11px] text-sky-100/50">
        工作区 ≠ 租户、≠ git 仓。切换后会清空 Agent/报告选择并重载；远程失败不会静默回退本机。
      </p>
      {err ? <p className="text-amber-300">{err}</p> : null}
    </div>
  );
}
