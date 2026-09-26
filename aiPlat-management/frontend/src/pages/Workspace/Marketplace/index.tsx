import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, toast } from '../../../components/ui';
import {
  workspaceSkillInstallerApi, workspaceAgentApi,
  toolApi, workspaceMcpApi, workspaceSkillApi, packagesApi,
  workflowTemplateApi,
} from '../../../services';

type TabKey = 'skills' | 'agents' | 'tools' | 'mcp' | 'workflows' | 'published';

interface CatalogEntry {
  name: string;
  label?: string;
  description?: string;
  category?: string;
  installed?: boolean;
  source?: string;
  version?: string;
  /** Extra capability hints for distinguishing similar items */
  capabilities?: string[];
}

function pickDescription(...candidates: unknown[]): string {
  for (const c of candidates) {
    const s = typeof c === 'string' ? c.trim() : '';
    if (s) return s;
  }
  return '';
}

function DescBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > 160 || text.includes('\n');

  useEffect(() => {
    setExpanded(false);
  }, [text]);

  if (!text) {
    return <div className="text-xs text-gray-600 mt-1 italic">暂无功能说明</div>;
  }

  return (
    <div className="mt-2">
      <div
        className={`text-xs text-gray-400 whitespace-pre-wrap break-words leading-relaxed ${
          expanded || !long ? '' : 'line-clamp-4'
        }`}
      >
        {text}
      </div>
      {long && (
        <button
          type="button"
          className="text-[11px] text-primary/90 hover:text-primary mt-1"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '收起' : '展开全部说明'}
        </button>
      )}
    </div>
  );
}

const MarketplacePage: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('skills');

  // Skills
  const [skillCatalog, setSkillCatalog] = useState<CatalogEntry[]>([]);
  const [skillLoading, setSkillLoading] = useState(false);
  const [skillInstLoading, setSkillInstLoading] = useState<string | null>(null);

  // Agents
  const [agentItems, setAgentItems] = useState<CatalogEntry[]>([]);
  const [agentLoading, setAgentLoading] = useState(false);

  // Tools
  const [toolItems, setToolItems] = useState<CatalogEntry[]>([]);
  const [toolLoading, setToolLoading] = useState(false);

  // MCP
  const [mcpItems, setMcpItems] = useState<CatalogEntry[]>([]);
  const [mcpLoading, setMcpLoading] = useState(false);

  // Workflows
  const [workflowItems, setWorkflowItems] = useState<CatalogEntry[]>([]);
  const [workflowLoading, setWorkflowLoading] = useState(false);

  // Published packages
  const [pubPackages, setPubPackages] = useState<CatalogEntry[]>([]);
  const [pubLoading, setPubLoading] = useState(false);
  const [pubInstLoading, setPubInstLoading] = useState<string | null>(null);

  // Deploy history
  const [deployFiles, setDeployFiles] = useState<Array<{ name: string; path: string; size_mb: number; created: string }>>([]);

  const fetchDeployHistory = async () => {
    try {
      const res = await fetch('/api/deploy/history');
      const data = await res.json();
      setDeployFiles(data.files || []);
    } catch { /* ignore */ }
  };

  // Deploy
  const [deployLog, setDeployLog] = useState<string[]>([]);
  const [zipPath, setZipPath] = useState('');
  const [deployingId, setDeployingId] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleSingleDeploy = useCallback(async (name: string, tabType: string) => {
    const prefixMap: Record<string, string> = { agents: 'agent', skills: 'skill', tools: 'tool', mcp: 'mcp', workflows: 'workflow' };
    const ids = (prefixMap[tabType] || 'agent') + ':' + encodeURIComponent(name);
    setDeployingId(name);
    try {
      const res = await fetch('/api/deploy/build?ids=' + ids, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        toast.success(`「${name}」发行构建已启动`);
        pollRef.current = setInterval(async () => {
          try {
            const sr = await fetch('/api/deploy/status');
            const sd = await sr.json();
            setDeployLog(sd.log || []);
            if (sd.zip_path) setZipPath(sd.zip_path);
            if (!sd.running) {
              if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
              setDeployingId('');
            }
          } catch { /* ignore */ }
        }, 2000);
      } else { toast.error(data.message || '启动失败'); setDeployingId(''); }
    } catch { toast.error('构建失败'); setDeployingId(''); }
  }, []);

  const fetchPublished = async () => {
    setPubLoading(true);
    try {
      const [pkgs, inst] = await Promise.all([packagesApi.list(), packagesApi.listInstalls()]);
      const instList = ((inst as any).installs || []) as Array<{ name: string }>;
      const instNames = new Set(instList.map((i: any) => i.name));
      setPubPackages(
        ((pkgs as any).packages || []).map((p: any) => ({
          name: p.name, label: p.name,
          description: pickDescription(p.description, p.summary, `${p.versions || '?'} 个版本`),
          category: 'package',
          version: p.version, installed: instNames.has(p.name),
        }))
      );
    } catch { setPubPackages([]); }
    finally { setPubLoading(false); }
  };

  const fetchSkills = async () => {
    setSkillLoading(true);
    try {
      const installed = await workspaceSkillApi.list({ limit: 500 });
      const skills = (installed as any).skills || [];
      setSkillCatalog(
        skills.filter((s: any) => s.status === 'listed').map((s: any) => ({
          name: s.id || s.name,
          label: s.display_name || s.name,
          description: pickDescription(s.description, s.summary, (s.metadata || {}).description),
          category: s.category || 'skill',
          installed: true,
          capabilities: [
            s.execution_type ? `执行:${s.execution_type}` : '',
            ...(Array.isArray(s.tags) ? s.tags.slice(0, 4).map(String) : []),
          ].filter(Boolean),
        }))
      );
    } catch { setSkillCatalog([]); }
    finally { setSkillLoading(false); }
  };

  const fetchAgents = async () => {
    setAgentLoading(true);
    try {
      const wsRes = await workspaceAgentApi.list({ limit: 200 });
      const ws = (wsRes as any).agents || [];
      setAgentItems(
        ws.filter((a: any) => a.status === 'listed').map((a: any) => {
          const skills = (a.skills || []).filter(Boolean).map(String);
          const tools = (a.tools || []).filter(Boolean).map(String);
          const mcps = (a.mcp_ids || []).filter(Boolean).map(String);
          return {
            name: a.id || a.name,
            label: a.display_name || a.name,
            // Never use agent_type as description — that hid real capability text
            description: pickDescription(
              a.description,
              (a.metadata || {}).description,
              (a.config || {}).system_prompt,
            ),
            category: a.category || a.agent_type || a.type || 'agent',
            installed: true,
            capabilities: [
              ...skills.slice(0, 4).map((s: string) => `Skill:${s}`),
              ...tools.slice(0, 3).map((t: string) => `Tool:${t}`),
              ...mcps.slice(0, 2).map((m: string) => `MCP:${m}`),
            ],
          };
        })
      );
    } catch { setAgentItems([]); }
    finally { setAgentLoading(false); }
  };

  const fetchTools = async () => {
    setToolLoading(true);
    try {
      const res = await toolApi.list({ limit: 500 } as any);
      const tools = (res as any).tools || [];
      setToolItems(
        tools.filter((t: any) => t.status === 'listed').map((t: any) => ({
          name: t.name,
          label: t.name,
          description: pickDescription(t.description, (t.provenance || {}).source),
          category: t.category || t.scope || 'general',
          installed: t.available !== false,
          capabilities: [
            t.scope ? `范围:${t.scope}` : '',
            t.category ? String(t.category) : '',
          ].filter(Boolean),
        }))
      );
    } catch { setToolItems([]); }
    finally { setToolLoading(false); }
  };

  const fetchMCP = async () => {
    setMcpLoading(true);
    try {
      const res = await workspaceMcpApi.listServers();
      const servers = (res as any).servers || [];
      setMcpItems(
        servers.filter((s: any) => s.status === 'listed').map((s: any) => {
          const toolCount = Array.isArray(s.tools) ? s.tools.length : (s.tool_count || 0);
          return {
            name: s.name || s.id,
            label: s.display_name || s.name || s.id,
            description: pickDescription(s.description, s.summary),
            category: s.transport || 'mcp',
            installed: s.enabled !== false,
            capabilities: [
              s.transport ? `传输:${s.transport}` : '',
              toolCount ? `${toolCount} 个工具` : '',
            ].filter(Boolean),
          };
        })
      );
    } catch { setMcpItems([]); }
    finally { setMcpLoading(false); }
  };

  const fetchWorkflows = async () => {
    setWorkflowLoading(true);
    try {
      const res = await (workflowTemplateApi as any).list({ limit: 200 });
      const workflows = (res as any).workflows || (res as any).items || (res as any).templates || [];
      setWorkflowItems(
        workflows.filter((w: any) => w.status === 'listed').map((w: any) => {
          const nodes = Array.isArray(w.nodes) ? w.nodes.length : (w.node_count || 0);
          return {
            name: w.id || w.name,
            label: w.display_name || w.name,
            description: pickDescription(w.description, w.summary, (w.metadata || {}).description),
            category: w.category || 'workflow',
            installed: true,
            capabilities: [
              nodes ? `${nodes} 节点` : '',
              w.app ? `App:${w.app}` : '',
            ].filter(Boolean),
          };
        })
      );
    } catch { setWorkflowItems([]); }
    finally { setWorkflowLoading(false); }
  };

  useEffect(() => {
    if (tab === 'skills') fetchSkills();
    else if (tab === 'agents') fetchAgents();
    else if (tab === 'tools') fetchTools();
    else if (tab === 'mcp') fetchMCP();
    else if (tab === 'workflows') fetchWorkflows();
    else if (tab === 'published') { fetchPublished(); fetchDeployHistory(); }
  }, [tab]);

  const handleInstallSkill = async (name: string) => {
    setSkillInstLoading(name);
    try {
      const entry = skillCatalog.find(e => e.name === name);
      const sourceType = entry?.source?.startsWith('http') || entry?.source?.includes('github') ? 'git' : 'local_path';
      const plan = await workspaceSkillInstallerApi.plan({ source_type: sourceType as any, url: entry?.source || name, ref: 'main' });
      await workspaceSkillInstallerApi.install({ source_type: sourceType as any, plan_id: (plan as any).plan_id, confirm: true });
      toast.success(`已安装 ${name}`);
      await fetchSkills();
    } catch (e: any) { toast.error(`安装失败：${e?.message || e}`); }
    finally { setSkillInstLoading(null); }
  };

  const tabs: Array<{ key: TabKey; label: string; count: number }> = [
    { key: 'skills', label: 'Skills', count: skillCatalog.length },
    { key: 'agents', label: 'Agents', count: agentItems.length },
    { key: 'tools', label: 'Tools', count: toolItems.length },
    { key: 'mcp', label: 'MCP', count: mcpItems.length },
    { key: 'workflows', label: 'Workflows', count: workflowItems.length },
    { key: 'published', label: '已发布包', count: pubPackages.length },
  ];

  const handleInstallPackage = async (name: string) => {
    setPubInstLoading(name);
    try {
      await packagesApi.install(name, {});
      toast.success(`已安装 ${name}`);
      await fetchPublished();
    } catch (e: any) { toast.error(`安装失败：${e?.message || e}`); }
    finally { setPubInstLoading(null); }
  };

  const renderList = (items: CatalogEntry[], loading: boolean, onAction?: (name: string) => void, actionLabel?: string, actionLoading?: string | null, tabType?: string) => (
    loading ? <div className="text-sm text-gray-500 py-8 text-center">加载中...</div> :
    items.length === 0 ? <div className="text-sm text-gray-500 py-8 text-center">暂无可用项</div> :
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      {items.map((item) => (
        <div key={item.name} className="rounded-xl border border-dark-border bg-dark-card p-4 hover:border-gray-600 transition-colors flex flex-col">
          <div className="flex items-start justify-between mb-1">
            <div className="flex-1 min-w-0 pr-2">
              <div className="text-sm font-medium text-gray-200" title={item.label || item.name}>
                {item.label || item.name}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                {item.category && <span className="text-[10px] text-gray-500">{item.category}</span>}
                {item.version && <span className="text-[10px] text-gray-600">v{item.version}</span>}
                <span className="text-[10px] text-gray-600 font-mono truncate max-w-[140px]" title={item.name}>{item.name}</span>
              </div>
            </div>
            {item.installed ? (
              <div style={{ display: 'flex', gap: 4, flexShrink: 0, marginLeft: 8 }}>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/15 text-green-400 border border-green-500/25">已安装</span>
                {tabType && (
                  <Button variant="secondary" size="sm" loading={deployingId === item.name}
                    onClick={() => handleSingleDeploy(item.name, tabType)}
                    title="构建独立发行包">
                    📦
                  </Button>
                )}
              </div>
            ) : (
              onAction && (
                <Button variant="primary" size="sm" loading={actionLoading === item.name} onClick={() => onAction(item.name)} className="flex-shrink-0 ml-2">
                  {actionLabel || '安装'}
                </Button>
              )
            )}
          </div>
          <DescBlock text={item.description || ''} />
          {!!item.capabilities?.length && (
            <div className="flex flex-wrap gap-1 mt-2">
              {item.capabilities.slice(0, 8).map((c) => (
                <span
                  key={c}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-400 border border-dark-border max-w-full truncate"
                  title={c}
                >
                  {c}
                </span>
              ))}
            </div>
          )}
          {item.source && <div className="text-[10px] text-gray-600 mt-2 truncate" title={item.source}>{item.source}</div>}
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">商城</h1>
        <p className="text-xs text-gray-500 mt-1">每张卡片展示完整功能说明；说明过长可点「展开全部说明」。能力标签帮助快速分辨绑定的 Skill / Tool / MCP。</p>
      </div>

      <div className="flex gap-1 border-b border-dark-border pb-2">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded-t text-sm transition-colors ${
              tab === t.key ? 'bg-dark-hover text-primary border-b-2 border-primary -mb-[2px]' : 'text-gray-400 hover:text-gray-200'
            }`}>
            {t.label} {t.count > 0 && <span className="text-[10px] opacity-50 ml-1">{t.count}</span>}
          </button>
        ))}
      </div>

      {tab === 'skills' && renderList(skillCatalog, skillLoading, handleInstallSkill, '安装', skillInstLoading, 'skills')}
      {tab === 'agents' && renderList(agentItems, agentLoading, undefined, undefined, undefined, 'agents')}
      {tab === 'tools' && renderList(toolItems, toolLoading, undefined, undefined, undefined, 'tools')}
      {tab === 'mcp' && renderList(mcpItems, mcpLoading, undefined, undefined, undefined, 'mcp')}
      {tab === 'workflows' && renderList(workflowItems, workflowLoading, undefined, undefined, undefined, 'workflows')}
      {tab === 'published' && (
        <>
          <div className="text-sm font-medium text-gray-300 mb-3">📦 部署包</div>
          {deployFiles.length === 0 ? (
            <div className="text-sm text-gray-500 py-4 text-center">暂无部署包，点击各 Tab 中的 📦 按钮生成</div>
          ) : (
            <div className="grid grid-cols-1 gap-2 mb-6">
              {deployFiles.map((f, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-dark-border bg-dark-card px-4 py-3">
                  <div>
                    <div className="text-sm text-gray-200 font-mono">{f.name}</div>
                    <div className="text-xs text-gray-500">{f.size_mb} MB · {f.created.slice(0, 19).replace('T', ' ')}</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <a href={'/api/deploy/download?path=' + encodeURIComponent(f.path)}
                      download className="text-sm text-blue-400 hover:text-blue-300 cursor-pointer">
                      ⬇ 下载
                    </a>
                    <button onClick={async () => {
                      if (!confirm(`确定删除 ${f.name}？`)) return;
                      try {
                        const res = await fetch('/api/deploy/delete?path=' + encodeURIComponent(f.path), { method: 'DELETE' });
                        const data = await res.json();
                        if (data.ok) { toast.success('已删除'); fetchDeployHistory(); }
                        else { toast.error(data.detail || '删除失败'); }
                      } catch { toast.error('删除失败'); }
                    }} className="text-sm text-red-400 hover:text-red-300" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                      🗑
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="text-sm font-medium text-gray-300 mb-3">📋 已安装包</div>
          {renderList(pubPackages, pubLoading, handleInstallPackage, '安装', pubInstLoading)}
        </>
      )}
      {(deployLog.length > 0 || zipPath) && (
        <div style={{ position: 'fixed', bottom: 16, right: 16, width: 620, maxHeight: 'calc(100vh - 32px)', background: '#0d0d1a', border: '1px solid #333', borderRadius: 10, padding: 16, zIndex: 100, boxShadow: '0 8px 40px rgba(0,0,0,0.6)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            {zipPath ? (
              <div style={{ color: '#4ade80', fontSize: 14, fontWeight: 600 }}>✅ 构建完成 — 去「已发布包」Tab 下载</div>
            ) : (
              <div style={{ color: '#f59e0b', fontSize: 14, fontWeight: 600 }}>⏳ 正在构建部署包...</div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button onClick={() => { setDeployLog([]); setZipPath(''); }}
                style={{ background: 'none', border: 'none', color: '#666', fontSize: 18, cursor: 'pointer', lineHeight: 1, padding: '0 4px' }}
                title="关闭">
                ✕
              </button>
            </div>
          </div>
          {deployLog.length > 0 && (
            <div style={{ color: '#0f0', fontSize: 12, fontFamily: 'monospace', maxHeight: 400, overflow: 'auto', background: '#050510', borderRadius: 6, padding: 10, lineHeight: 1.6 }}>
              {deployLog.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MarketplacePage;
