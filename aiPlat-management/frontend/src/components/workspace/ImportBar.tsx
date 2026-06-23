import React, { useRef, useState } from 'react';
import { Button, Input, toast } from '../ui';

interface ImportBarProps {
  /** Called after successful installation so the parent page can refresh its list. */
  onImported: () => void;
  /** Which asset type the parent page manages (used for the primary fetch endpoint). */
  assetType: 'agents' | 'skills' | 'mcps' | 'workflows';
  /** Optional secondary types to also scan during preview. */
  alsoScan?: Array<'agents' | 'skills' | 'mcps' | 'workflows'>;
}

const ENDPOINTS: Record<string, { plan: string; install: string; uploadPlan?: string; uploadInstall?: string }> = {
  agents: {
    plan: '/api/core/workspace/agents/installer/plan',
    install: '/api/core/workspace/agents/installer/install',
    uploadPlan: '/api/core/workspace/agents/installer/upload-plan',
    uploadInstall: '/api/core/workspace/agents/installer/upload-install',
  },
  skills: {
    plan: '/api/core/workspace/skills/installer/plan',
    install: '/api/core/workspace/skills/installer/install',
    uploadPlan: '/api/core/workspace/skills/installer/upload-plan',
    uploadInstall: '/api/core/workspace/skills/installer/upload-install',
  },
  mcps: {
    plan: '/api/core/workspace/mcps/installer/plan',
    install: '/api/core/workspace/mcps/installer/install',
    uploadPlan: '/api/core/workspace/mcps/installer/upload-plan',
    uploadInstall: '/api/core/workspace/mcps/installer/upload-install',
  },
  workflows: {
    plan: '/api/core/workflows/installer/plan',
    install: '/api/core/workflows/installer/install',
    uploadPlan: '/api/core/workflows/installer/upload-plan',
    uploadInstall: '/api/core/workflows/installer/upload-install',
  },
};

const LABELS: Record<string, string> = {
  agents: 'Agents', skills: 'Skills', mcps: 'MCPs', workflows: 'Workflows',
};

type ImportMode = 'git' | 'zip' | 'local';

const ImportBar: React.FC<ImportBarProps> = ({ onImported, assetType, alsoScan }) => {
  const [open, setOpen] = useState(false);
  const [importMode, setImportMode] = useState<ImportMode>('git');
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('main');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [localPath, setLocalPath] = useState('~/agent-skills');
  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [installing, setInstalling] = useState(false);

  const st = importMode === 'zip' ? 'zip' : ((url.includes('github') || url.startsWith('https://')) ? 'git' : 'path');

  const handlePreview = async () => {
    if (importMode === 'git' && !url.trim()) return;
    if (importMode === 'zip' && !zipFile) return;
    setLoading(true); setPlan(null);

    // Zip upload path
    if (importMode === 'zip' && zipFile) {
      const ep = ENDPOINTS[assetType];
      if (!ep.uploadPlan) { toast.error(`${LABELS[assetType]} 暂不支持 Zip 上传`); setLoading(false); return; }
      try {
        const fd = new FormData();
        fd.append('file', zipFile);
        fd.append('auto_detect_subdir', 'true');
        const res = await fetch(ep.uploadPlan, { method: 'POST', body: fd });
        if (!res.ok) { const e = await res.json().catch(() => ({})); toast.error(`预览失败：${(e as any).detail || res.statusText}`); return; }
        const d = await res.json();
        const items = (d as any).skills || [];
        if (items.length === 0) { toast.warning('未检测到可导入的 Skill'); return; }
        setPlan({ skills: items });
      } catch (e: any) { toast.error(`预览失败：${e?.message || e}`); }
      finally { setLoading(false); }
      return;
    }

    // Git path
    const scanTypes = [assetType, ...(alsoScan || [])];
    const unique = [...new Set(scanTypes)];
    try {
      const promises = unique.map((t) => {
        const ep = ENDPOINTS[t];
        return fetch(ep.plan, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source_type: st, url, ref, auto_detect_subdir: true }),
        }).then(r => r.json()).then(d => ({ type: t, data: d }));
      });
      const results = await Promise.all(promises);
      const combined: any = {};
      let total = 0;
      for (const r of results) {
        const items = (r.data as any).agents || (r.data as any).skills || (r.data as any).mcps || (r.data as any).workflows || [];
        if (items.length > 0) { combined[r.type] = items; total += items.length; }
      }
      if (total === 0) { toast.warning('未检测到可导入的资产'); return; }
      setPlan(combined);
    } catch (e: any) { toast.error(`预览失败：${e?.message || e}`); }
    finally { setLoading(false); }
  };

  const handleInstall = async () => {
    if (!plan) return;
    setInstalling(true);

    // Zip upload path
    if (importMode === 'zip' && zipFile) {
      const ep = ENDPOINTS[assetType];
      if (!ep.uploadInstall) { toast.error(`${LABELS[assetType]} 暂不支持 Zip 安装`); setInstalling(false); return; }
      try {
        const fd = new FormData();
        fd.append('file', zipFile);
        fd.append('auto_detect_subdir', 'true');
        const res = await fetch(ep.uploadInstall, { method: 'POST', body: fd });
        if (!res.ok) { const e = await res.json().catch(() => ({})); toast.error(`安装失败：${(e as any).detail || res.statusText}`); return; }
        const d = await res.json();
        toast.success(`已导入 ${(d.installed || []).length} 个 Skill 到应用库`);
        setPlan(null); setZipFile(null); setOpen(false);
        onImported();
      } catch (e: any) { toast.error(`安装失败：${e?.message || e}`); }
      finally { setInstalling(false); }
      return;
    }

    // Git path
    try {
      let count = 0;
      for (const [type, _] of Object.entries(plan)) {
        const ep = ENDPOINTS[type];
        const res = await fetch(ep.install, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source_type: st, url, ref, auto_detect_subdir: true, allow_overwrite: false }),
        });
        const d = await res.json();
        count += (d.installed || []).length;
      }
      toast.success(`已导入 ${count} 个资产到应用库（status=draft，需测试审核后上架）`);
      setPlan(null); setUrl(''); setOpen(false);
      onImported();
    } catch (e: any) { toast.error(`安装失败：${e?.message || e}`); }
    finally { setInstalling(false); }
  };

  const handleLocalInstall = async () => {
    if (!localPath.trim()) return;
    setInstalling(true);
    try {
      const res = await fetch('/api/core/wiki/skills/install-from-directory', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search_path: localPath }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(`导入失败：${d.detail || res.statusText}`); return; }
      toast.success(`已从本地目录导入 ${d.installed} 个技能`);
      setOpen(false); setPlan(null);
      onImported();
    } catch (e: any) { toast.error(`导入失败：${e?.message || e}`); }
    finally { setInstalling(false); }
  };

  return (
    <>
      {!open ? (
        <Button variant="ghost" size="sm" onClick={() => setOpen(true)} className="text-xs">
          🔗 从开源仓库导入 {LABELS[assetType] || ''}
        </Button>
      ) : (
        <div className="rounded-xl border border-primary/30 bg-dark-card p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-medium text-gray-200">🔗 从开源仓库 / 本地 Zip 导入</div>
            <button onClick={() => { setOpen(false); setPlan(null); }} className="text-gray-500 hover:text-gray-300" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18 }}>✕</button>
          </div>

          {/* Import mode toggle */}
          <div className="flex items-center gap-2 mb-3">
            <button onClick={() => { setImportMode('git'); setZipFile(null); }}
              className={`text-xs px-3 py-1.5 rounded ${importMode === 'git' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>
              Git 仓库
            </button>
            <button onClick={() => { setImportMode('zip'); setUrl(''); }}
              className={`text-xs px-3 py-1.5 rounded ${importMode === 'zip' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>
              本地 Zip
            </button>
            <button onClick={() => { setImportMode('local'); }}
              className={`text-xs px-3 py-1.5 rounded ${importMode === 'local' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>
              本地目录
            </button>
          </div>

          {importMode === 'git' ? (
            <div className="flex gap-2 mb-2">
              <Input placeholder="Git URL 如 https://github.com/user/repo" value={url} onChange={(e: any) => setUrl(e.target.value)}
                className="flex-1" disabled={loading || installing} />
              <Input placeholder="ref (main/tag/commit)" value={ref} onChange={(e: any) => setRef(e.target.value)}
                style={{ width: 160 }} disabled={loading || installing} />
              <Button variant="secondary" onClick={handlePreview} loading={loading} disabled={installing}>🔍 预览</Button>
            </div>
          ) : (
            <div className="mb-2">
              <input ref={fileInputRef} type="file" accept=".zip" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) setZipFile(f); }} />
              <div onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-dark-border rounded-xl p-5 text-center cursor-pointer hover:border-primary/50 transition-colors">
                {zipFile ? (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">📦</span>
                      <div className="text-left">
                        <div className="text-sm text-gray-200">{zipFile.name}</div>
                        <div className="text-xs text-gray-500">{(zipFile.size / 1024).toFixed(0)} KB</div>
                      </div>
                    </div>
                    <Button variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); handlePreview(); }} loading={loading} disabled={installing}>🔍 预览</Button>
                  </div>
                ) : (
                  <div>
                    <div className="text-lg mb-1">📤</div>
                    <div className="text-sm text-gray-300">点击选择 .zip 文件或拖拽到此处</div>
                    <div className="text-xs text-gray-500 mt-1">自动探测子目录并提取 SKILL.md</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {importMode === 'local' && (
            <div className="flex gap-2 mb-2">
              <Input placeholder="本地目录路径 如 ~/agent-skills" value={localPath} onChange={(e: any) => setLocalPath(e.target.value)}
                className="flex-1" disabled={installing} />
              <Button variant="primary" onClick={handleLocalInstall} loading={installing}>⬇ 导入</Button>
            </div>
          )}

          <div className="text-xs text-gray-500">
            {importMode === 'git'
              ? '支持 GitHub / Git 仓库。自动检测格式并转换。导入后需测试审核后上架。'
              : importMode === 'local'
              ? '从本地目录导入 skills/*/SKILL.md。兼容 Google agent-skills 格式。一键导入全部技能。'
              : '上传包含 SKILL.md 的 zip 文件。支持 last30days、Claude Code Plugin 等格式。导入后需测试审核后上架。'}
          </div>
          {plan && (
            <div className="mt-3 p-3 rounded-lg border border-dark-border bg-dark-bg">
              <div className="text-xs font-medium text-gray-200 mb-2">将要导入：</div>
              {plan.agents && <div className="text-xs text-blue-300">🤖 Agents: {plan.agents.map((a: any) => a.name || a.id).join(', ')}</div>}
              {plan.skills && <div className="text-xs text-green-300">⚡ Skills: {plan.skills.map((s: any) => s.name || s.skill_id).join(', ')}</div>}
              {plan.mcps && <div className="text-xs text-yellow-300">🔌 MCPs: {plan.mcps.map((m: any) => m.name || m.id).join(', ')}</div>}
              {plan.workflows && <div className="text-xs text-purple-300">⚙️ Workflows: {plan.workflows.map((w: any) => w.name || w.id).join(', ')}</div>}
              <div className="mt-3">
                <Button variant="primary" onClick={handleInstall} loading={installing}>⬇ 导入到应用库</Button>
                <button onClick={() => setPlan(null)} className="ml-3 text-xs text-gray-500 hover:text-gray-300" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>取消</button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
};

export default ImportBar;
