import React, { useEffect, useRef, useState } from 'react';
import { Folder, File, ExternalLink, RefreshCw, Plus, Trash2, ChevronRight, ChevronDown, Play, Square, RotateCcw, Send, CheckSquare, MinusSquare, Square as SquareIcon, AlertTriangle } from 'lucide-react';
import { Button, Modal, Input, toast } from '../../../components/ui';

interface VaultEntry {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: VaultEntry[];
  size?: number;
  status?: string;  // 'ready' | 'wikified' | 'failed'
}

interface Vault {
  vault_id: string;
  vault_path: string;
  label: string;
  enabled: number;
  auto_index: number;
  last_indexed?: number;
  path_exists?: boolean;
}

interface IndexStatus {
  status: string;
  progress: number;
  last_error: string | null;
  cleaned?: number;
  wikified?: number;
}

const VaultBrowser: React.FC = () => {
  const [vaults, setVaults] = useState<Vault[]>([]);
  const [tree, setTree] = useState<VaultEntry[]>([]);
  const [selectedVault, setSelectedVault] = useState<Vault | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<{ name: string; content: string; frontmatter: any; path: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [indexStatuses, setIndexStatuses] = useState<Record<string, IndexStatus>>({});

  // ② Batch wiki: selected files
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [batchWikiLoading, setBatchWikiLoading] = useState(false);

  // ① Auto-wiki toggle per vault
  const [autoWikiVaults, setAutoWikiVaults] = useState<Set<string>>(new Set());

  // ⑤ Wiki backlinks for preview
  const [wikiBacklinks, setWikiBacklinks] = useState<any[]>([]);
  const [lastDocId, setLastDocId] = useState<string | null>(null);

  // Connect modal state
  const [connectOpen, setConnectOpen] = useState(false);
  const [connectPath, setConnectPath] = useState('');
  const [connectLabel, setConnectLabel] = useState('');
  const [connecting, setConnecting] = useState(false);

  const statusTimer = useRef<any>(null);

  const fetchVaults = async () => {
    try {
      const r = await fetch('/api/platform/kb/vault/list');
      const data = await r.json();
      setVaults(data.vaults || []);
    } catch { setVaults([]); }
  };

  useEffect(() => {
    fetchVaults();
    statusTimer.current = setInterval(async () => {
      try {
        const r = await fetch('/api/platform/kb/vault/list');
        const data = await r.json();
        setVaults(data.vaults || []);
        const newStatuses: Record<string, IndexStatus> = {};
        for (const v of (data.vaults || [])) {
          try {
            const sr = await fetch(`/api/platform/kb/vault/${v.vault_id}/index/status`);
            const sd = await sr.json();
            newStatuses[v.vault_id] = sd as IndexStatus;
          } catch { }
        }
        setIndexStatuses(newStatuses);
      } catch { }
    }, 10000);
    return () => clearInterval(statusTimer.current);
  }, []);

  const fetchTree = async (vault: Vault) => {
    setSelectedVault(vault);
    setPreview(null);
    setSelectedFiles(new Set());
    setExpanded(new Set());
    setWikiBacklinks([]);
    setLastDocId(null);
    setLoading(true);
    try {
      const r = await fetch(`/api/platform/kb/vault/${vault.vault_id}/tree`);
      const data = await r.json();
      setTree(data.entries || []);
    } catch { setTree([]); }
    finally { setLoading(false); }
  };

  const fetchIndexStatus = async (vaultId: string) => {
    try {
      const sr = await fetch(`/api/platform/kb/vault/${vaultId}/index/status`);
      const sd = await sr.json();
      setIndexStatuses(prev => ({ ...prev, [vaultId]: sd }));
    } catch { }
  };

  const handleConnect = async () => {
    if (!connectPath.trim()) return;
    setConnecting(true);
    try {
      const r = await fetch('/api/platform/kb/vault/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: connectPath.trim(), label: connectLabel.trim() }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error((data as any).detail || '连接失败');
      try {
        await fetch(`/api/platform/kb/vault/${data.vault_id}/index/start`, { method: 'POST' });
        toast.success(`已连接并启动索引：${connectLabel || connectPath.trim().split('/').pop()}`);
      } catch {
        toast.success(`已连接：${connectLabel || connectPath.trim().split('/').pop()}`);
      }
      setConnectOpen(false); setConnectPath(''); setConnectLabel('');
      fetchVaults();
    } catch (e: any) { toast.error(`连接失败：${e?.message}`); }
    finally { setConnecting(false); }
  };

  const handleDisconnect = async (vault: Vault) => {
    if (!confirm(`断开 ${vault.label} 的连接？`)) return;
    try {
      await fetch(`/api/platform/kb/vault/${vault.vault_id}`, { method: 'DELETE' });
      toast.success('已断开');
      fetchVaults();
      if (selectedVault?.vault_id === vault.vault_id) { setSelectedVault(null); setTree([]); setPreview(null); }
    } catch { toast.error('断开失败'); }
  };

  const handleRead = async (entry: VaultEntry) => {
    if (entry.type === 'file') {
      try {
        const r = await fetch(`/api/platform/kb/vault/${selectedVault!.vault_id}/read?path=${encodeURIComponent(entry.path)}`);
        const data = await r.json();
        setPreview({ name: data.name, content: data.content, frontmatter: data.frontmatter, path: entry.path });
        setWikiBacklinks([]); setLastDocId(null);
      } catch { toast.error('读取失败'); }
    }
  };

  const toggleExpand = (path: string) => {
    setExpanded(prev => { const n = new Set(prev); if (n.has(path)) n.delete(path); else n.add(path); return n; });
  };

  const toggleSelectFile = (path: string) => {
    setSelectedFiles(prev => { const n = new Set(prev); if (n.has(path)) n.delete(path); else n.add(path); return n; });
  };

  // Count selectable/selected files in a directory subtree
  const dirStats = (children: VaultEntry[]): { total: number; selected: number } => {
    let total = 0, selected = 0;
    const walk = (items: VaultEntry[]) => {
      for (const e of items) {
        if (e.type === 'file' && e.status !== 'wikified') { total++; if (selectedFiles.has(e.path)) selected++; }
        if (e.children) walk(e.children);
      }
    };
    walk(children);
    return { total, selected };
  };

  const toggleSelectDir = (entries: VaultEntry[]) => {
    setSelectedFiles(prev => {
      const n = new Set(prev);
      const walk = (items: VaultEntry[]) => {
        for (const e of items) {
          if (e.type === 'file' && e.status !== 'wikified') n.add(e.path);
          if (e.children) walk(e.children);
        }
      };
      // Recursive check: are ALL non-wikified files in the entire subtree selected?
      const allFilesRecursive = (items: VaultEntry[]): boolean => {
        for (const e of items) {
          if (e.type === 'file' && e.status !== 'wikified' && !prev.has(e.path)) return false;
          if (e.children && !allFilesRecursive(e.children)) return false;
        }
        return true;
      };
      if (allFilesRecursive(entries)) {
        for (const e of entries) {
          if (e.type === 'file') n.delete(e.path);
          const unWalk = (items: VaultEntry[]) => {
            for (const c of items) {
              if (c.type === 'file') n.delete(c.path);
              if (c.children) unWalk(c.children);
            }
          };
          if (e.children) unWalk(e.children);
        }
      } else {
        walk(entries);
      }
      return n;
    });
  };

  const openInObsidian = (filePath: string) => {
    const vaultName = encodeURIComponent(selectedVault?.label || '');
    const fileName = encodeURIComponent(filePath.split('/').pop()?.replace('.md', '') || '');
    window.open(`obsidian://open?vault=${vaultName}&file=${fileName}`, '_blank');
  };

  // ④ Derive collection name from subdirectory relative to vault root
  const deriveCollectionId = (filePath: string): string => {
    const vaultPath = (selectedVault?.vault_path || '').replace(/\/$/, '');
    if (!vaultPath || !filePath.startsWith(vaultPath)) return '';
    const relative = filePath.slice(vaultPath.length).replace(/^\//, '');
    const parts = relative.split('/');
    if (parts.length <= 1) return ''; // root-level file
    return parts.slice(0, -1).join('_').replace(/[^a-zA-Z0-9_\u4e00-\u9fff-]/g, '_').slice(0, 60);
  };

  const sendToWiki = async (filePath: string): Promise<{ok: boolean; category?: string; schemaValid?: boolean}> => {
    try {
      const collectionId = deriveCollectionId(filePath);
      const r = await fetch('/api/platform/kb/vault/wiki', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: filePath,
          collection_id: collectionId,
          vault_id: selectedVault?.vault_id || '',
        }),
      });
      if (!r.ok) return { ok: false };
      const data = await r.json();
      const ok = data?.status === 'created' || data?.status === 'skipped';
      const category = (data?.category || '') as string;
      const schemaValid = data?.schema_valid as boolean | undefined;
      // ⑤ Query backlinks after conversion
      if (ok && data?.doc_id) {
        setLastDocId(data.doc_id);
        try {
          const br = await fetch(`/api/platform/kb/vault/wiki/backlinks?doc_id=${encodeURIComponent(data.doc_id)}`);
          const bd = await br.json();
          setWikiBacklinks(bd.pages || []);
        } catch { setWikiBacklinks([]); }
      }
      // Tree refresh deferred to batch handler to prevent flickering
      return { ok, category, schemaValid };
      return { ok, category, schemaValid };
    } catch { return { ok: false }; }
  };

  const handleBatchWiki = async () => {
    if (selectedFiles.size === 0) { toast.error('请先选择文件'); return; }
    setBatchWikiLoading(true);
    let ok = 0; let fail = 0; let schemaOk = 0;
    const categories: string[] = [];
    for (const fp of selectedFiles) {
      const res = await sendToWiki(fp);
      if (res.ok) {
        ok++;
        if (res.category) categories.push(res.category);
        if (res.schemaValid === true) schemaOk++;
      } else { fail++; }
    }
    setBatchWikiLoading(false);
    const catSummary = categories.length > 0 ? ` (${[...new Set(categories)].join(', ')})` : '';
    const schemaSummary = ok > 0 ? ` · schema: ${schemaOk}/${ok}` : '';
    if (fail === 0) toast.success(`已发送 ${ok} 个文件到 Wiki${catSummary}${schemaSummary}`);
    else toast.warning(`发送完成：${ok} 成功${schemaSummary}, ${fail} 失败`);
    if (ok > 0 && selectedVault) { fetchTree(selectedVault); setSelectedFiles(new Set()); }
  };

  const countFilesOnly = (items: VaultEntry[]): number => {
    let count = 0;
    for (const e of items) {
      if (e.type === 'file') count++;
      if (e.children) count += countFilesOnly(e.children);
    }
    return count;
  };

  const renderTree = (entries: VaultEntry[], depth: number = 0): React.ReactNode => {
    return entries.map((e) => {
      const isExpanded = expanded.has(e.path);
      const isDir = e.type === 'directory';
      const isSelected = selectedFiles.has(e.path);
      return (
        <div key={e.path}>
          <div
            onClick={() => { if (isDir) toggleExpand(e.path); handleRead(e); }}
            className={`flex items-center gap-1 px-2 py-1 cursor-pointer rounded text-sm hover:bg-dark-hover ${preview?.path === e.path ? 'bg-primary/10 text-primary' : 'text-gray-300'}`}
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
          >
            {/* ② Checkbox for files */}
            {!isDir && (
              <button onClick={(ev) => {
                ev.stopPropagation();
                if (e.status !== 'wikified') toggleSelectFile(e.path);
              }}
                className={`p-0.5 rounded ${e.status === 'wikified' ? 'text-gray-700 cursor-not-allowed' : isSelected ? 'text-primary' : 'text-gray-600'}`}
                title={e.status === 'wikified' ? '已转换，不可选' : '选择'}>
                {isSelected ? <CheckSquare size={14} /> : <SquareIcon size={14} />}
              </button>
            )}
            {/* Directory checkbox — show ✅ if all files fully converted, else interactive checkbox */}
            {isDir && e.children && e.children.length > 0 && (
              (() => {
                const stats = dirStats(e.children);
                const fileCount = countFilesOnly(e.children);
                if (fileCount > 0 && stats.total === 0) {
                  return <span className="text-[10px] text-gray-500 px-1" title="全部已转换">✓ 全部</span>;
                }
                if (fileCount === 0) {
                  return <span className="text-[10px] text-gray-600 px-1" title="无文件">—</span>;
                }
                const isAllSel = stats.total > 0 && stats.selected >= stats.total;
                const isPartial = stats.selected > 0 && stats.selected < stats.total;
                return (
                  <button onClick={(ev) => { ev.stopPropagation(); toggleSelectDir(e.children!); }}
                    className={`p-0.5 rounded ${isAllSel ? 'text-primary' : isPartial ? 'text-amber-400' : 'text-gray-600'} hover:text-primary`}
                    title={`全选/取消目录 (${stats.selected}/${stats.total})`}>
                    {isAllSel ? <CheckSquare size={14} /> : isPartial ? <MinusSquare size={14} /> : <SquareIcon size={14} />}
                  </button>
                );
              })()
            )}
            {isDir ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : (!isDir && <span className="w-3.5" />)}
            <span className="flex items-center gap-1 flex-1 truncate">
              {isDir ? <Folder size={14} className="text-amber-400" /> : <File size={14} className="text-blue-400" />}
              <span className="truncate">{e.name}</span>
            </span>
            {!isDir && (
              <div className="flex items-center gap-0.5">
                {e.status === 'wikified' ? (
                  <span className="text-[10px] text-gray-500 px-1 rounded" title="已生成知识页面">已转换</span>
                ) : e.status === 'failed' ? (
                  <span className="text-[11px] text-red-500/80 px-1 rounded" title="转换失败，可重试">❌</span>
                ) : (
                  <span className="text-[10px] text-gray-600 px-1 rounded" title="就绪，待转换">⬤</span>
                )}
                <button onClick={async (ev) => {
                  ev.stopPropagation();
                  handleRead(e);
                  const res = await sendToWiki(e.path);
                  const cid = deriveCollectionId(e.path);
                  const cat = res.category ? ` · ${res.category}` : '';
                  res.ok ? toast.success('已发送到 Wiki' + (cid ? ` (${cid})` : '') + cat)
                         : toast.error('发送失败');
                }} className="p-0.5 rounded hover:bg-dark-border text-gray-500 hover:text-green-400" title="发送到 Wiki">
                  <Send size={10} />
                </button>
                <button onClick={(ev) => { ev.stopPropagation(); openInObsidian(e.path); }}
                  className="p-0.5 rounded hover:bg-dark-border text-gray-500 hover:text-gray-200" title="在 Obsidian 中打开">
                  <ExternalLink size={10} />
                </button>
              </div>
            )}
          </div>
          {isDir && isExpanded && e.children && renderTree(e.children, depth + 1)}
        </div>
      );
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-200">Vault 浏览器</h2>
          <p className="text-xs text-gray-500">直接连接本地 Obsidian Vault，浏览→选择→发送到 Wiki</p>
        </div>
        <div className="flex items-center gap-2">
          {selectedFiles.size > 0 && (
            <Button variant="primary" size="sm" icon={<Send size={14} />}
              onClick={handleBatchWiki} loading={batchWikiLoading}>
              批量发送 ({selectedFiles.size})
            </Button>
          )}
          <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setConnectOpen(true)}>
            连接 Vault
          </Button>
          <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />} onClick={fetchVaults} loading={loading} />
        </div>
      </div>

      {vaults.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">
          暂未连接任何 Vault。点击「连接 Vault」添加。
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Vault list */}
          <div className="border border-dark-border rounded-lg bg-dark-card p-3 space-y-2">
            <div className="text-xs font-medium text-gray-400 mb-2">Vault 列表</div>
            {vaults.map((v) => {
              const st = indexStatuses[v.vault_id];
              const isIndexing = st?.status === 'running';
              const isDisconnected = v.path_exists === false;
              return (
              <div key={v.vault_id} className="mb-2">
                <div
                  onClick={() => { if (!isDisconnected) fetchTree(v); }}
                  className={`flex items-center justify-between p-2 rounded cursor-pointer text-xs ${
                    selectedVault?.vault_id === v.vault_id ? 'bg-primary/10 border border-primary/20'
                    : isDisconnected ? 'bg-red-900/20 border border-red-800'
                    : 'hover:bg-dark-hover'
                  }`}>
                  <div className="truncate flex-1">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-200 font-medium">{v.label}</span>
                      {isDisconnected && <AlertTriangle size={10} className="text-red-400" />}
                      {isIndexing && <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" title="索引中" />}
                    </div>
                    <div className="text-gray-500 truncate text-[10px]">{v.vault_path}</div>
                    {isDisconnected && (
                      <div className="text-[10px] text-red-400 mt-0.5">路径不可达</div>
                    )}
                    {st && (
                      <div className="text-[10px] mt-0.5">
                        {isIndexing ? (
                          <span className="text-green-400">{st.progress > 0 ? `索引中 · ${st.progress} 文件` : '索引中...'}
                          {st.wikified ? ` · ${st.wikified} Wiki` : ''}</span>
                        ) : st.status === 'error' ? (
                          <span className="text-red-400">{st.last_error || '错误'}</span>
                        ) : st.progress > 0 ? (
                          <span className="text-blue-400">上次: {st.progress} 文件{st.wikified ? `, ${st.wikified} Wiki` : ''}</span>
                        ) : st.status === 'idle' ? (
                          <span className="text-gray-500">待索引</span>
                        ) : null}
                      </div>
                    )}
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); handleDisconnect(v); }}
                    className="p-1 rounded hover:bg-dark-border text-gray-500 hover:text-red-400 ml-1" title="断开">
                    <Trash2 size={12} />
                  </button>
                </div>
                {/* ① Auto-wiki + Index controls */}
                <div className="flex items-center gap-1 px-2 py-0.5">
                  <button onClick={async (e) => {
                    e.stopPropagation();
                    if (isDisconnected) { toast.error('Vault 路径不可达'); return; }
                    const autoWiki = autoWikiVaults.has(v.vault_id);
                    setAutoWikiVaults(prev => { const n = new Set(prev); if (n.has(v.vault_id)) n.delete(v.vault_id); else n.add(v.vault_id); return n; });
                    try {
                      await fetch(`/api/platform/kb/vault/${v.vault_id}/index/start`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ auto_wiki: !autoWiki }),
                      });
                      fetchIndexStatus(v.vault_id);
                      toast.success('索引已启动' + (!autoWiki ? ' (自动 Wiki)' : ''));
                      fetchVaults();
                    } catch { toast.error('启动索引失败'); }
                  }} className={`p-0.5 rounded text-[10px] ${isDisconnected ? 'text-gray-700 cursor-not-allowed' : autoWikiVaults.has(v.vault_id) ? 'text-green-400' : 'text-gray-500 hover:text-green-400'}`} title={autoWikiVaults.has(v.vault_id) ? '自动 Wiki 已开启' : '开始/重启索引'} disabled={isDisconnected}>
                    <Play size={10} />
                  </button>
                  <button onClick={async (e) => {
                    e.stopPropagation();
                    if (isDisconnected) { toast.error('Vault 路径不可达'); return; }
                    try { await fetch(`/api/platform/kb/vault/${v.vault_id}/index/stop`, { method: 'POST' }); fetchIndexStatus(v.vault_id); fetchVaults(); toast.success('已停止'); }
                    catch { toast.error('停止失败'); }
                  }} className={`p-0.5 rounded text-[10px] ${isDisconnected ? 'text-gray-700 cursor-not-allowed' : 'text-gray-500 hover:text-amber-400'}`} title="停止索引" disabled={isDisconnected}>
                    <Square size={10} />
                  </button>
                  <button onClick={async (e) => {
                    e.stopPropagation();
                    if (isDisconnected) { toast.error('Vault 路径不可达'); return; }
                    if (!confirm('重建索引将清除现有索引数据并重新扫描全部文件，确定继续？')) return;
                    try {
                      const r = await fetch(`/api/platform/kb/vault/${v.vault_id}/reindex`, { method: 'POST' });
                      const data = await r.json();
                      toast.success(`已清除 ${data.cleared} 个旧索引，开始重建 ${data.queued} 个文件`);
                      fetchIndexStatus(v.vault_id);
                      fetchVaults();
                    } catch { toast.error('重建失败'); }
                  }} className={`p-0.5 rounded text-[10px] ${isDisconnected ? 'text-gray-700 cursor-not-allowed' : 'text-gray-500 hover:text-blue-400'}`} title="重建全部索引" disabled={isDisconnected}>
                    <RotateCcw size={10} />
                  </button>
                </div>
              </div>
            )})}
          </div>

          {/* File tree */}
          <div className="border border-dark-border rounded-lg bg-dark-card p-3 max-h-96 overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-400">目录</span>
              {selectedFiles.size > 0 && (
                <button onClick={() => setSelectedFiles(new Set())} className="text-xs text-gray-500 hover:text-gray-300">
                  清除 ({selectedFiles.size})
                </button>
              )}
            </div>
            {loading ? <div className="text-xs text-gray-500">加载中...</div> : renderTree(tree)}
          </div>

          {/* Preview */}
          <div className="md:col-span-2 border border-dark-border rounded-lg bg-dark-card p-3 max-h-96 overflow-y-auto">
            <div className="text-xs font-medium text-gray-400 mb-2">预览</div>
            {preview ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-200">{preview.name}</span>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" icon={<Send size={12} />}
                      onClick={async () => {
                        const res = await sendToWiki(preview.path);
                        const cid = deriveCollectionId(preview.path);
                        const cat = res.category ? ` · ${res.category}` : '';
                        res.ok ? toast.success('已发送到 Wiki' + (cid ? ` (${cid})` : '') + cat) : toast.error('发送失败');
                      }}>
                      发送到 Wiki
                    </Button>
                    <Button variant="ghost" size="sm" icon={<ExternalLink size={12} />}
                      onClick={() => openInObsidian(preview.path)}>
                      在 Obsidian 中打开
                    </Button>
                  </div>
                </div>
                {/* ⑤ Wiki reverse link + frontmatter */}
                {preview.frontmatter && Object.keys(preview.frontmatter).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {preview.frontmatter.tags && (Array.isArray(preview.frontmatter.tags) ? preview.frontmatter.tags : [preview.frontmatter.tags]).map((t: string) => (
                      <span key={t} className="px-1.5 py-0.5 rounded text-xs bg-dark-hover text-gray-400">{t}</span>
                    ))}
                    {preview.frontmatter.title && (
                      <span className="px-1.5 py-0.5 rounded text-xs bg-dark-hover text-gray-400">title: {preview.frontmatter.title}</span>
                    )}
                  </div>
                )}
                <div className="text-xs text-gray-500 font-mono truncate" title={preview.path}>
                  📁 {preview.path}
                </div>
                {/* ④ Collection hint */}
                {(() => { const cid = deriveCollectionId(preview.path); return cid ? (
                  <div className="text-xs text-blue-400 mt-1">
                    集合: {cid}
                  </div>
                ) : null; })()}
                {/* ⑤ Wiki reverse links */}
                {lastDocId && (
                  <div className="mt-2 p-2 rounded bg-dark-hover">
                    <div className="text-xs font-medium text-gray-400 mb-1">
                      Wiki 反向链接
                      {wikiBacklinks.length > 0 && <span className="text-gray-600 ml-1">({wikiBacklinks.length})</span>}
                    </div>
                    {wikiBacklinks.length > 0 ? (
                      wikiBacklinks.map((p: any, i: number) => (
                        <div key={i} className="flex items-center gap-1 text-xs py-0.5">
                          <span className="text-primary font-medium">{p.title || p.name || '?'}</span>
                          <span className="text-gray-600">({p.category || ''})</span>
                          {p.summary && <span className="text-gray-500 truncate">- {String(p.summary).slice(0, 120)}</span>}
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-gray-600">暂无反向链接（新文档将在下次重建时建立）</div>
                    )}
                  </div>
                )}
                <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {preview.content.slice(0, 3000)}
                  {preview.content.length > 3000 && '\n\n... (内容过长，在 Obsidian 中查看完整内容)'}
                </pre>
              </div>
            ) : (
              <div className="text-xs text-gray-500 text-center py-8">
                选择 vault 和文件进行预览。勾选多个文件可批量发送到 Wiki。
              </div>
            )}
          </div>
        </div>
      )}

      {/* Connect Modal */}
      <Modal open={connectOpen} onClose={() => setConnectOpen(false)} title="连接 Vault" width={460}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setConnectOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleConnect} loading={connecting}
              disabled={!connectPath.trim()}>连接</Button>
          </div>
        }>
        <div className="space-y-3">
          <Input label="Vault 路径" value={connectPath}
            onChange={(e: any) => setConnectPath(e.target.value)}
            placeholder="/Users/apple/Documents/Obsidian Vault" />
          <Input label="显示名称（可选）" value={connectLabel}
            onChange={(e: any) => setConnectLabel(e.target.value)}
            placeholder="自动使用文件夹名" />
          <p className="text-xs text-gray-500">连接后不会复制文件，直接读取原文件内容。支持 Markdown (.md) 文件。</p>
        </div>
      </Modal>
    </div>
  );
};

export default VaultBrowser;
