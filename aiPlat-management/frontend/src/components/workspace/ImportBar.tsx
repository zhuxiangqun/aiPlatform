import React, { useState } from 'react';
import { Button, Input, toast } from '../ui';

interface ImportBarProps {
  /** Called after successful installation so the parent page can refresh its list. */
  onImported: () => void;
  /** Which asset type the parent page manages (used for the primary fetch endpoint). */
  assetType: 'agents' | 'skills' | 'mcps' | 'workflows';
  /** Optional secondary types to also scan during preview. */
  alsoScan?: Array<'agents' | 'skills' | 'mcps' | 'workflows'>;
}

const ENDPOINTS: Record<string, { plan: string; install: string }> = {
  agents: {
    plan: '/api/core/workspace/agents/installer/plan',
    install: '/api/core/workspace/agents/installer/install',
  },
  skills: {
    plan: '/api/core/workspace/skills/installer/plan',
    install: '/api/core/workspace/skills/installer/install',
  },
  mcps: {
    plan: '/api/core/workspace/mcps/installer/plan',
    install: '/api/core/workspace/mcps/installer/install',
  },
  workflows: {
    plan: '/api/core/workflows/installer/plan',
    install: '/api/core/workflows/installer/install',
  },
};

const LABELS: Record<string, string> = {
  agents: 'Agents',
  skills: 'Skills',
  mcps: 'MCPs',
  workflows: 'Workflows',
};

const ImportBar: React.FC<ImportBarProps> = ({ onImported, assetType, alsoScan }) => {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('main');
  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [installing, setInstalling] = useState(false);

  const st = (url.includes('github') || url.startsWith('https://')) ? 'git' : 'path';

  const handlePreview = async () => {
    if (!url.trim()) return;
    setLoading(true); setPlan(null);
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
        if (items.length > 0) {
          combined[r.type] = items;
          total += items.length;
        }
      }
      if (total === 0) { toast.warning('未检测到可导入的资产'); return; }
      setPlan(combined);
    } catch (e: any) { toast.error(`预览失败：${e?.message || e}`); }
    finally { setLoading(false); }
  };

  const handleInstall = async () => {
    if (!plan) return;
    setInstalling(true);
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

  return (
    <>
      {!open ? (
        <Button variant="ghost" size="sm" onClick={() => setOpen(true)} className="text-xs">
          🔗 从开源仓库导入 {LABELS[assetType] || ''}
        </Button>
      ) : (
        <div className="rounded-xl border border-primary/30 bg-dark-card p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-medium text-gray-200">🔗 从开源仓库导入</div>
            <button onClick={() => { setOpen(false); setPlan(null); }} className="text-gray-500 hover:text-gray-300" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18 }}>✕</button>
          </div>
          <div className="flex gap-2 mb-2">
            <Input placeholder="Git URL 如 https://github.com/user/repo" value={url} onChange={(e: any) => setUrl(e.target.value)}
              className="flex-1" disabled={loading || installing} />
            <Input placeholder="ref (main/tag/commit)" value={ref} onChange={(e: any) => setRef(e.target.value)}
              style={{ width: 160 }} disabled={loading || installing} />
            <Button variant="secondary" onClick={handlePreview} loading={loading} disabled={installing}>🔍 预览</Button>
          </div>
          <div className="text-xs text-gray-500">
            支持 GitHub / Git 仓库。自动检测 Hermes/OpenClaw/Coze/Dify 格式并转换。导入后 status=draft，需在应用库测试、提交审核、上架后才会出现在商城。
          </div>
          {plan && (
            <div className="mt-3 p-3 rounded-lg border border-dark-border bg-dark-bg">
              <div className="text-xs font-medium text-gray-200 mb-2">将要导入：</div>
              {plan.agents && <div className="text-xs text-blue-300">🤖 Agents: {plan.agents.map((a: any) => a.name || a.id).join(', ')}</div>}
              {plan.skills && <div className="text-xs text-green-300">📋 Skills: {plan.skills.map((s: any) => s.name || s.skill_id).join(', ')}</div>}
              {plan.mcps && <div className="text-xs text-yellow-300">🔌 MCPs: {plan.mcps.map((m: any) => m.name || m.id).join(', ')}</div>}
              {plan.workflows && <div className="text-xs text-purple-300">🔀 Workflows: {plan.workflows.map((w: any) => w.name || w.id).join(', ')}</div>}
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
