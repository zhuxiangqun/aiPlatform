/**
 * BranchPanel — 本体分支管理面板 (Palantir Global Branching 对齐)
 *
 * 功能:
 *   - 列出域的所有分支 (main + 实验分支)
 *   - 派生新分支 (fork)
 *   - 对比两个分支的差异 (diff)
 *   - 合并分支 (merge, 三级策略: auto/warn/blocked)
 *   - 删除分支
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button, Input, toast } from '../../components/ui';
import {
  GitBranch, GitMerge, GitFork, GitCommit, Plus, Trash2, ChevronDown, ChevronRight,
  ArrowRightLeft, RefreshCw, AlertTriangle, CheckCircle, XCircle,
} from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

// ── Types ────────────────────────────────────────────────────────────────

interface BranchInfo {
  domain_id: string;
  branch_name: string;
  created_at: number;
  base_snapshot_id?: number;
  base_version?: string;
  description: string;
  last_modified: number;
  commit_count: number;
}

interface DiffData {
  merge_level: string;
  diff_summary: string;
  added_entities: string[];
  removed_entities: string[];
  modified_entities: Array<{ entity_id: string; changes: Record<string, any> }>;
  added_relations: Array<{ source: string; target: string; relation: string }>;
  removed_relations: Array<{ source: string; target: string; relation: string }>;
  conflicts: string[];
}

interface MergeData {
  success: boolean;
  merge_level: string;
  summary: string;
  conflict_details: string[];
}

// ── Component ─────────────────────────────────────────────────────────────

const BranchPanel: React.FC = () => {
  const [domainId, setDomainId] = useState('fde-delivery');
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [newBranchName, setNewBranchName] = useState('');
  const [newBranchDesc, setNewBranchDesc] = useState('');
  const [diffSource, setDiffSource] = useState('');
  const [diffTarget, setDiffTarget] = useState('main');
  const [diffResult, setDiffResult] = useState<DiffData | null>(null);
  const [mergeResult, setMergeResult] = useState<MergeData | null>(null);
  const [showFork, setShowFork] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => { loadBranches(); }, [domainId]);

  const loadBranches = async () => {
    try {
      const r = await fetch(`${API_BASE}/branches/${domainId}`);
      const d = await r.json();
      setBranches(d.branches || []);
    } catch { setBranches([]); }
  };

  const handleFork = async () => {
    if (!newBranchName.trim()) return;
    try {
      const r = await fetch(`${API_BASE}/branches/${domainId}/fork`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_name: newBranchName.trim(), description: newBranchDesc }),
      });
      if (r.ok) { setShowFork(false); setNewBranchName(''); setNewBranchDesc(''); loadBranches(); toast?.success?.('分支已创建'); }
      else { const d = await r.json(); toast?.error?.(d.detail || '创建失败'); }
    } catch (e: any) { toast?.error?.(e?.message || '创建失败'); }
  };

  const handleDelete = async (branchName: string) => {
    if (!confirm(`确认删除分支 "${branchName}"?`)) return;
    try {
      await fetch(`${API_BASE}/branches/${domainId}/${branchName}`, { method: 'DELETE' });
      loadBranches();
      toast?.info?.('分支已删除');
    } catch (e: any) { toast?.error?.(e?.message || '删除失败'); }
  };

  const handleDiff = async () => {
    if (!diffSource || !diffTarget) return;
    try {
      const r = await fetch(`${API_BASE}/branches/${domainId}/diff?source=${diffSource}&target=${diffTarget}`);
      setDiffResult(await r.json());
      setMergeResult(null);
    } catch (e: any) { toast?.error?.(e?.message || '对比失败'); }
  };

  const handleMerge = async (source: string, autoApply: boolean = false) => {
    try {
      const r = await fetch(`${API_BASE}/branches/${domainId}/merge`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, target: 'main', auto_apply: autoApply }),
      });
      setMergeResult(await r.json());
      loadBranches();
    } catch (e: any) { toast?.error?.(e?.message || '合并失败'); }
  };

  const timeAgo = (ts: number) => {
    if (!ts) return '';
    const diff = Date.now() / 1000 - ts;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
  };

  const levelColor = (level: string) => {
    switch (level) {
      case 'auto': return 'text-green-400';
      case 'warn': return 'text-yellow-400';
      case 'blocked': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">本体分支</h2>
          <p className="text-xs text-gray-500 mt-0.5">Git-like 分支管理: fork / diff / merge</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1 w-36"
            value={domainId}
            onChange={e => setDomainId(e.target.value)}
            placeholder="domain_id"
          />
          <Button variant="ghost" size="sm" onClick={loadBranches}><RefreshCw className="w-3 h-3" /></Button>
          <Button variant="default" size="sm" onClick={() => setShowFork(true)}>
            <Plus className="w-3 h-3 mr-1" />新建分支
          </Button>
        </div>
      </div>

      {/* Branch list */}
      <Card className="border-gray-700/50">
        <CardHeader><span className="text-sm font-medium text-gray-200">{branches.length} 个分支</span></CardHeader>
        <CardContent>
          <div className="space-y-2">
            {branches.map(b => (
              <div key={b.branch_name} className="flex items-center justify-between p-2.5 rounded bg-gray-800/50 border border-gray-700/30">
                <div className="flex items-center gap-2">
                  {b.branch_name === 'main'
                    ? <GitBranch className="w-4 h-4 text-green-400" />
                    : <GitFork className="w-4 h-4 text-blue-400" />}
                  <div>
                    <span className="text-sm text-gray-200 font-medium">{b.branch_name}</span>
                    {b.description && <span className="text-[10px] text-gray-500 ml-2">{b.description}</span>}
                    {b.commit_count > 0 && <span className="text-[10px] text-gray-600 ml-1">{b.commit_count} commits</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-600">{timeAgo(b.last_modified)}</span>
                  {b.branch_name !== 'main' && (
                    <>
                      <Button variant="ghost" size="sm" className="text-purple-400 text-[10px] py-0 h-6"
                        onClick={() => { setDiffSource(b.branch_name); setDiffTarget('main'); setShowDiff(true); handleDiff(); }}>
                        对比
                      </Button>
                      <Button variant="ghost" size="sm" className="text-green-400 text-[10px] py-0 h-6"
                        onClick={() => handleMerge(b.branch_name)}>
                        合并→main
                      </Button>
                      <Button variant="ghost" size="sm" className="text-red-400 text-[10px] py-0 h-6"
                        onClick={() => handleDelete(b.branch_name)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Diff result */}
      {diffResult && (
        <Card className={`border ${diffResult.merge_level === 'auto' ? 'border-green-500/20' : diffResult.merge_level === 'warn' ? 'border-yellow-500/20' : 'border-red-500/20'}`}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-200">
                对比: {diffSource} ↔ {diffTarget}
              </span>
              <span className={`text-xs font-medium ${levelColor(diffResult.merge_level)}`}>
                {diffResult.merge_level === 'auto' ? '✓ 可自动合并' : diffResult.merge_level === 'warn' ? '⚠ 需审核' : '✗ 被阻止'}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-gray-400 mb-3">{diffResult.diff_summary}</div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <div className="text-green-400 font-medium">+{diffResult.added_entities.length} 新增实体</div>
                {diffResult.added_entities.slice(0, 10).map((e, i) => (
                  <div key={i} className="text-green-300/80 pl-2">+ {e}</div>
                ))}
              </div>
              <div>
                <div className="text-red-400 font-medium">-{diffResult.removed_entities.length} 删除实体</div>
                {diffResult.removed_entities.slice(0, 10).map((e, i) => (
                  <div key={i} className="text-red-300/80 pl-2">- {e}</div>
                ))}
              </div>
            </div>
            {diffResult.conflicts.length > 0 && (
              <div className="mt-3 p-2 rounded bg-yellow-500/5 border border-yellow-500/20">
                <div className="text-xs text-yellow-400 font-medium">冲突</div>
                {diffResult.conflicts.map((c, i) => (
                  <div key={i} className="text-[10px] text-yellow-300/80 mt-0.5"><AlertTriangle className="w-3 h-3 inline mr-1" />{c}</div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Merge result */}
      {mergeResult && (
        <div className={`p-3 rounded text-sm ${
          mergeResult.success ? 'bg-green-500/10 border border-green-500/20 text-green-400' :
          mergeResult.merge_level === 'warn' ? 'bg-yellow-500/10 border border-yellow-500/20 text-yellow-400' :
          'bg-red-500/10 border border-red-500/20 text-red-400'
        }`}>
          {mergeResult.success ? <CheckCircle className="w-4 h-4 inline mr-1" /> : <AlertTriangle className="w-4 h-4 inline mr-1" />}
          {mergeResult.summary}
          {mergeResult.conflict_details.length > 0 && (
            <div className="mt-1 text-xs space-y-0.5">
              {mergeResult.conflict_details.map((d, i) => <div key={i}>• {d}</div>)}
            </div>
          )}
          {!mergeResult.success && mergeResult.merge_level === 'warn' && (
            <Button variant="default" size="sm" className="mt-2" onClick={() => handleMerge(diffSource, true)}>
              强制合并
            </Button>
          )}
        </div>
      )}

      {/* Fork modal */}
      {showFork && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm mx-4 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200">新建分支</h3>
              <button onClick={() => setShowFork(false)} className="text-gray-500 hover:text-gray-300"><XCircle className="w-4 h-4" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400">分支名称 *</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={newBranchName} onChange={e => setNewBranchName(e.target.value)} placeholder="experiment-v2" />
              </div>
              <div>
                <label className="text-xs text-gray-400">描述</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={newBranchDesc} onChange={e => setNewBranchDesc(e.target.value)} placeholder="测试新的本体结构" />
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowFork(false)} className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-gray-700 text-gray-400 hover:text-white">取消</button>
              <button onClick={handleFork} disabled={!newBranchName.trim()}
                className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BranchPanel;
