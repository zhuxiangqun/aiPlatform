import { useEffect, useMemo, useState } from 'react';
import { toolApi, workspaceToolApi } from '../../services';
import type { ToolInfo } from '../../services';
import { detectSkillBindIntent, toolMatchesIntent } from './skillBindingIntent';

function hintFor(name: string): string {
  const n = name.toLowerCase();
  if (n.includes('upload') || n.includes('oss') || n.includes('s3') || n.includes('storage'))
    return '对象存储 / 上传';
  if (n.includes('file')) return '读写本地/工作区文件';
  if (n.includes('http') || n.includes('fetch') || n.includes('request')) return 'HTTP GET/文本，不是对象存储 PUT';
  if (n.includes('browser')) return '浏览器自动化';
  if (n.includes('search')) return '检索';
  return '';
}

export function SkillBoundToolsPicker({
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
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [showAll, setShowAll] = useState(false);

  const intent = useMemo(() => detectSkillBindIntent(intentText || ''), [intentText]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');
    Promise.all([
      toolApi.list({ limit: 200 }).catch(() => ({ tools: [] as ToolInfo[] })),
      workspaceToolApi.list({ limit: 200 }).catch(() => ({ tools: [] as ToolInfo[] })),
    ])
      .then(([a, b]) => {
        if (cancelled) return;
        const map = new Map<string, ToolInfo>();
        for (const t of [...(a.tools || []), ...(b.tools || [])]) {
          const name = String(t?.name || '').trim();
          if (!name) continue;
          if (!map.has(name)) map.set(name, t);
        }
        setTools(Array.from(map.values()));
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e?.message || e || '加载 Tool 失败'));
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
      tools.filter((t) =>
        toolMatchesIntent(String(t.name), String(t.description || ''), intent),
      ),
    [tools, intent],
  );

  const ordered = useMemo(() => {
    const sel = new Set(selected);
    const pool = showAll ? tools : matching;
    const names = Array.from(
      new Set([...selected.filter((n) => tools.some((t) => t.name === n)), ...pool.map((t) => t.name)]),
    );
    return names
      .map((n) => tools.find((t) => t.name === n))
      .filter((t): t is ToolInfo => !!t)
      .sort((a, b) => Number(sel.has(b.name)) - Number(sel.has(a.name)) || a.name.localeCompare(b.name));
  }, [tools, matching, selected, showAll]);

  const toggle = (name: string) => {
    if (selected.includes(name)) onChange(selected.filter((x) => x !== name));
    else onChange([...selected, name]);
  };

  const emptyMatch = intent !== 'generic' && matching.length === 0 && !showAll;
  const matchNames = new Set(matching.map((t) => t.name));

  return (
    <div className="rounded-xl border border-dark-border p-4 space-y-3">
      <div className="text-sm text-gray-200 font-medium">用哪个已有 Tool 干活？（不要手写 handler.py）</div>
      <div className="text-xs text-gray-500">
        {intent === 'upload'
          ? '这里只出现能做对象存储上传的 Tool（名字里要有 upload / oss / s3 / storage）。没有就不会列计算器、写本地文件、sysgraph——那些勾了也传不上去。'
          : '只列出和当前描述匹配的已注册 Tool。'}
      </div>
      {emptyMatch ? (
        <div className="text-xs text-amber-300">
          当前没有可用的{intent === 'upload' ? '上传' : '匹配'} Tool。请到{' '}
          <a
            href={
              intent === 'upload'
                ? `/workspace/tools?create=1&hint=upload${returnSkillId ? `&return_skill=${encodeURIComponent(returnSkillId)}` : ''}`
                : '/workspace/tools?create=1'
            }
            className="text-primary underline underline-offset-2"
          >
            工作区 → Tool
          </a>{' '}
          安装/创建
          {returnSkillId ? '（创建成功会回到本 Skill 并预勾，再点保存）' : '后再回到本页勾选'}
          。本页不会编 handler.py。
        </div>
      ) : requiredHint && selected.length === 0 ? (
        <div className="text-xs text-amber-300">请勾选下面匹配的 Tool，或改勾 MCP。</div>
      ) : null}
      {loading ? <div className="text-xs text-gray-500">正在加载 Tool 目录…</div> : null}
      {err ? <div className="text-xs text-red-400">{err}</div> : null}
      {!loading && !emptyMatch && ordered.length === 0 ? (
        <div className="text-xs text-gray-500">没有可勾选项。</div>
      ) : null}
      {!loading && ordered.length > 0 && !emptyMatch ? (
        <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
          {ordered.map((t) => {
            const name = String(t.name);
            const extra = hintFor(name) || String(t.description || '').slice(0, 80);
            const ok = intent === 'generic' || matchNames.has(name) || selected.includes(name);
            return (
              <label
                key={name}
                className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                  ok ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed'
                } ${
                  selected.includes(name)
                    ? 'border-primary/40 bg-primary/5'
                    : 'border-dark-border hover:border-gray-600'
                }`}
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  disabled={!ok}
                  checked={selected.includes(name)}
                  onChange={() => ok && toggle(name)}
                />
                <span>
                  <span className="text-sm text-gray-100 block">
                    <code className="text-gray-200">{name}</code>
                    {t.scope === 'workspace' ? (
                      <span className="ml-2 text-[10px] text-gray-500">工作区</span>
                    ) : t.scope === 'engine' ? (
                      <span className="ml-2 text-[10px] text-gray-500">引擎</span>
                    ) : null}
                    {!ok ? <span className="ml-2 text-[10px] text-amber-400">与本 Skill 不匹配</span> : null}
                  </span>
                  {extra ? <span className="text-[11px] text-gray-500">{extra}</span> : null}
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
          {showAll ? '只显示匹配项' : '显示全部目录（高级，多数与本 Skill 无关）'}
        </button>
      ) : (
        <details className="text-[11px] text-gray-500">
          <summary className="cursor-pointer hover:text-gray-300">为什么不列出引擎里那一长串 Tool？</summary>
          <p className="mt-1 leading-relaxed">
            引擎目录是通用能力（写本地文件、搜索、sysgraph…），不能完成「上传到对象存储并返回 play_url」。
            列出来供勾选会造成假绑定。装好上传 Tool 后，匹配项会自动出现在上方。
          </p>
        </details>
      )}
    </div>
  );
}
