import { useEffect, useMemo, useState } from 'react';
import { workspaceMcpApi } from '../../services';
import type { McpServer } from '../../services';
import { detectSkillBindIntent, mcpMatchesIntent } from './skillBindingIntent';

export function SkillBoundMcpsPicker({
  selected,
  onChange,
  requiredHint,
  intentText,
  returnSkillId,
}: {
  selected: string[];
  onChange: (next: string[]) => void;
  requiredHint?: boolean;
  intentText?: string;
  returnSkillId?: string;
}) {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [showAll, setShowAll] = useState(false);
  const intent = useMemo(() => detectSkillBindIntent(intentText || ''), [intentText]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');
    workspaceMcpApi
      .listServers()
      .then((res) => {
        if (cancelled) return;
        setServers(Array.isArray(res.servers) ? res.servers : []);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e?.message || e || '加载 MCP 失败'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const matching = useMemo(
    () =>
      servers.filter((s) => {
        const name = String(s?.name || (s as any)?.id || '');
        const tools = Array.isArray(s.allowed_tools) ? s.allowed_tools.map(String) : [];
        return mcpMatchesIntent(name, tools, String((s as any).description || ''), intent);
      }),
    [servers, intent],
  );

  const ordered = useMemo(() => {
    const pool = showAll ? servers : matching;
    const names = Array.from(
      new Set([
        ...selected,
        ...pool.map((s) => String(s?.name || (s as any)?.id || '').trim()).filter(Boolean),
      ]),
    );
    return names
      .map((n) => servers.find((s) => String(s?.name || (s as any)?.id || '') === n))
      .filter((s): s is McpServer => !!s);
  }, [servers, matching, selected, showAll]);

  const toggle = (name: string) => {
    if (selected.includes(name)) onChange(selected.filter((x) => x !== name));
    else onChange([...selected, name]);
  };

  const emptyMatch = intent === 'upload' && matching.length === 0 && !showAll;

  return (
    <div className="rounded-xl border border-dark-border p-4 space-y-3">
      <div className="text-sm text-gray-200 font-medium">用哪个已有 MCP 干活？（外部系统不要手写程序）</div>
      <div className="text-xs text-gray-500">
        {intent === 'upload'
          ? '只列出名称或工具像 OSS/上传的 MCP。浏览器、计算器 MCP 办不了对象存储 PUT。'
          : '只列出和当前描述匹配的已注册 MCP。'}
      </div>
      {emptyMatch ? (
        <div className="text-xs text-amber-300">
          没有上传/对象存储 MCP。到{' '}
          <a
            href={
              intent === 'upload'
                ? `/workspace/mcp?create=1&hint=upload${returnSkillId ? `&return_skill=${encodeURIComponent(returnSkillId)}` : ''}`
                : '/workspace/mcp?create=1'
            }
            className="text-primary underline underline-offset-2"
          >
            工作区 → MCP
          </a>{' '}
          安装
          {returnSkillId ? '（创建成功会回到本 Skill 并预勾，再点保存）' : '后再勾选'}
          。浏览器类 MCP 请不要勾。
        </div>
      ) : requiredHint && selected.length === 0 ? (
        <div className="text-xs text-amber-300">外部能力请勾匹配的 MCP；没有就去工作区安装。</div>
      ) : null}
      {loading ? <div className="text-xs text-gray-500">正在加载 MCP 目录…</div> : null}
      {err ? <div className="text-xs text-red-400">{err}</div> : null}
      {!loading && !emptyMatch && ordered.length === 0 ? (
        <div className="text-xs text-gray-500">没有可勾选项。</div>
      ) : null}
      {!loading && ordered.length > 0 && !emptyMatch ? (
        <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
          {ordered.map((s) => {
            const name = String(s.name || (s as any).id || '');
            const extra = String((s as any).description || s.source || '').slice(0, 80);
            const tools = Array.isArray(s.allowed_tools) ? s.allowed_tools.map(String).slice(0, 4) : [];
            return (
              <label
                key={name}
                className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                  selected.includes(name)
                    ? 'border-primary/40 bg-primary/5'
                    : 'border-dark-border hover:border-gray-600'
                }`}
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={selected.includes(name)}
                  onChange={() => toggle(name)}
                />
                <span>
                  <span className="text-sm text-gray-100 block">
                    <code className="text-gray-200">{name}</code>
                    {s.source === 'internal' ? (
                      <span className="ml-2 text-[10px] text-gray-500">内部</span>
                    ) : (
                      <span className="ml-2 text-[10px] text-gray-500">MCP</span>
                    )}
                  </span>
                  {extra ? <span className="text-[11px] text-gray-500 block">{extra}</span> : null}
                  {tools.length ? (
                    <span className="text-[11px] text-gray-500">工具：{tools.join(', ')}</span>
                  ) : null}
                </span>
              </label>
            );
          })}
        </div>
      ) : null}
      {intent !== 'upload' ? (
        <button
          type="button"
          className="text-[11px] text-gray-500 hover:text-gray-300"
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? '只显示匹配项' : '显示全部 MCP（高级）'}
        </button>
      ) : (
        <details className="text-[11px] text-gray-500">
          <summary className="cursor-pointer hover:text-gray-300">为什么不列出浏览器 / 计算器 MCP？</summary>
          <p className="mt-1 leading-relaxed">
            那些 Server 没有对象存储 PUT。列出来供勾选会让审核误以为「已经有上传能力」。装好 OSS/上传 MCP 后会出现在上方。
          </p>
        </details>
      )}
    </div>
  );
}
