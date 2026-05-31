import React, { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Box, Download, Trash2, RefreshCw, Package, Wrench, Bot, Sparkles, Plug, GitBranch, Upload, Rocket } from 'lucide-react';
import { Button, Modal, toast, Badge } from '../../components/ui';
import { packageApi } from '../../services';
import { toastGateError } from '../../components/ui';

interface PackageInfo {
  name: string;
  version?: string;
  description?: string;
  scope?: string;
  installed?: boolean;
  resources?: { kind: string; id: string; bundled: boolean }[];
  versions?: number;
}

const RESOURCE_ICONS: Record<string, { icon: React.ReactNode; label: string }> = {
  agent: { icon: <Bot className="w-3 h-3" />, label: 'Agent' },
  skill: { icon: <Sparkles className="w-3 h-3" />, label: 'Skill' },
  mcp: { icon: <Plug className="w-3 h-3" />, label: 'MCP' },
  tool: { icon: <Wrench className="w-3 h-3" />, label: 'Tool' },
  workflow: { icon: <GitBranch className="w-3 h-3" />, label: 'Workflow' },
  hook: { icon: <Box className="w-3 h-3" />, label: 'Hook' },
};

const Plugins: React.FC = () => {
  const [installed, setInstalled] = useState<PackageInfo[]>([]);
  const [marketplace, setMarketplace] = useState<PackageInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState<string | null>(null);
  const [detailPkg, setDetailPkg] = useState<PackageInfo | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [exportModal, setExportModal] = useState(false);
  const [exportName, setExportName] = useState('');
  const [exportDesc, setExportDesc] = useState('');
  const [exportVersion, setExportVersion] = useState('0.1.0');
  const [exportAssets, setExportAssets] = useState<{ kind: string; id: string; label: string }[]>([]);
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);

  const fetchExportAssets = useCallback(async () => {
    const assets: { kind: string; id: string; label: string }[] = [];
    try {
      // Load workspace agents, skills, mcps
      const [agentsRes, skillsRes, mcpsRes] = await Promise.all([
        fetch('/api/core/workspace/agents').then(r => r.json()).catch(() => ({ items: [] })),
        fetch('/api/core/workspace/skills').then(r => r.json()).catch(() => ({ items: [] })),
        fetch('/api/core/workspace/mcp/servers').then(r => r.json()).catch(() => ({ servers: [] })),
      ]);
      (agentsRes.items || []).forEach((a: any) => assets.push({ kind: 'agent', id: a.name || a.id, label: a.display_name || a.name || a.id }));
      (skillsRes.items || []).forEach((s: any) => assets.push({ kind: 'skill', id: s.name || s.id, label: s.display_name || s.name || s.id }));
      (mcpsRes.servers || []).forEach((m: any) => assets.push({ kind: 'mcp', id: m.name, label: m.name }));
    } catch {}
    setExportAssets(assets);
  }, []);

  const handleExport = async () => {
    if (!exportName.trim()) { toast.error('请输入插件名称'); return; }
    if (selectedAssets.size === 0) { toast.error('请选择至少一个资源'); return; }
    setExporting(true);
    try {
      const resources = exportAssets
        .filter(a => selectedAssets.has(`${a.kind}:${a.id}`))
        .map(a => ({ kind: a.kind, id: a.id }));

      const res = await fetch('/api/core/workspace/packages/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: exportName.trim(),
          description: exportDesc.trim(),
          version: exportVersion.trim() || '0.1.0',
          resources,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Export failed' }));
        toast.error(err.detail || '导出失败');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${exportName.trim().replace(/\s+/g, '_')}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setExportModal(false);
      toast.success('插件已导出');
    } catch (e: any) {
      toast.error(`导出失败: ${e?.message || ''}`);
    } finally {
      setExporting(false);
    }
  };

  const toggleAsset = (key: string) => {
    setSelectedAssets(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [wsRes, mpRes] = await Promise.all([
        packageApi.listWorkspace().catch(() => ({ items: [] })),
        packageApi.listMarketplace().catch(() => ({ packages: [] })),
      ]);
      const wsPackages = ((wsRes as any)?.items || []).map((p: any) => ({ ...p, installed: true }));
      const mpPackages = ((mpRes as any)?.packages || []).filter(
        (p: any) => !wsPackages.some((w: any) => w.name === p.name)
      );
      setInstalled(wsPackages);
      setMarketplace(mpPackages);
    } catch {
      setInstalled([]);
      setMarketplace([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleInstall = async (pkgName: string) => {
    setInstalling(pkgName);
    try {
      await packageApi.install(pkgName);
      toast.success(`插件 "${pkgName}" 已安装`);
      fetchAll();
    } catch (e: any) {
      toastGateError(e, '安装失败');
    } finally {
      setInstalling(null);
    }
  };

  const handleInstallMarketplace = async (pkgName: string) => {
    setInstalling(pkgName);
    try {
      await packageApi.installMarketplace(pkgName);
      toast.success(`插件 "${pkgName}" 已从市场安装`);
      fetchAll();
    } catch (e: any) {
      toastGateError(e, '安装失败');
    } finally {
      setInstalling(null);
    }
  };

  const handlePublish = async (pkgName: string) => {
    const version = prompt('发布版本号:', '0.1.0');
    if (!version) return;
    setInstalling(pkgName);
    try {
      const res = await fetch(`/api/core/packages/${pkgName}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version, require_approval: false }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || '发布失败');
        return;
      }
      if (data.status === 'approval_required') {
        toast.success('已提交审批');
      } else {
        toast.success(`插件 "${pkgName}" 已发布到市场`);
      }
      fetchAll();
    } catch (e: any) {
      toast.error(`发布失败: ${e?.message || ''}`);
    } finally {
      setInstalling(null);
    }
  };

  const handleUninstall = async (pkgName: string) => {
    if (!window.confirm(`确定要卸载插件 "${pkgName}" 吗？`)) return;
    setInstalling(pkgName);
    try {
      await packageApi.uninstall(pkgName);
      toast.success(`插件 "${pkgName}" 已卸载`);
      fetchAll();
    } catch (e: any) {
      toastGateError(e, '卸载失败');
    } finally {
      setInstalling(null);
    }
  };

  const showDetail = async (pkg: PackageInfo) => {
    try {
      const detail = await packageApi.get(pkg.name);
      setDetailPkg(detail as any);
    } catch {
      setDetailPkg(pkg);
    }
    setDetailOpen(true);
  };

  const renderPkgCard = (pkg: PackageInfo, isInstalled: boolean) => {
    const resources = (pkg as any).resources || [];
    return (
      <motion.div
        key={pkg.name}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="p-4 rounded-xl bg-dark-card border border-dark-border hover:border-primary/30 transition-colors"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Box className="w-5 h-5 text-blue-400" />
            <span className="text-sm font-medium text-gray-100">{pkg.name}</span>
            {pkg.version && <span className="text-[10px] text-gray-500 font-mono">v{pkg.version}</span>}
            {isInstalled && <Badge variant="success" className="text-[10px]">已安装</Badge>}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => showDetail(pkg)}
              className="p-1.5 rounded hover:bg-dark-hover text-gray-400"
              title="查看详情"
            >
              <Package className="w-4 h-4" />
            </button>
            {isInstalled && (
              <button
                onClick={() => handlePublish(pkg.name)}
                className="p-1.5 rounded hover:bg-dark-hover text-purple-400"
                title="发布到市场"
                disabled={installing === pkg.name}
              >
                <Rocket className="w-4 h-4" />
              </button>
            )}
            {isInstalled ? (
              <button
                onClick={() => handleUninstall(pkg.name)}
                className="p-1.5 rounded text-red-400 hover:bg-red-400/10"
                title="卸载"
                disabled={installing === pkg.name}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={() => handleInstallMarketplace(pkg.name)}
                className="p-1.5 rounded text-green-400 hover:bg-green-400/10"
                title="从市场安装"
                disabled={installing === pkg.name}
              >
                <Download className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        {(pkg as any).description && (
          <div className="text-xs text-gray-500 mb-2">{(pkg as any).description}</div>
        )}
        {resources.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {(() => {
              const counts: Record<string, number> = {};
              resources.forEach((r: any) => { counts[r.kind] = (counts[r.kind] || 0) + 1; });
              return Object.entries(counts).map(([kind, cnt]) => {
                const info = RESOURCE_ICONS[kind];
                return (
                  <span key={kind} className="flex items-center gap-1 text-[10px] text-gray-400 bg-dark-bg px-1.5 py-0.5 rounded">
                    {info?.icon} {info?.label || kind} ×{cnt}
                  </span>
                );
              });
            })()}
          </div>
        )}
      </motion.div>
    );
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">插件管理</h1>
          <p className="text-sm text-gray-400 mt-1">安装和管理 aiPlat 插件 — 打包了 Agent、Skill、Tool、MCP、Workflow 的功能模块</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            icon={<Upload className="w-4 h-4" />}
            onClick={() => { fetchExportAssets(); setExportModal(true); }}
          >
            导出插件
          </Button>
          <Button icon={<RefreshCw className="w-4 h-4" />} onClick={fetchAll} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : (
        <>
          {/* Installed */}
          <div>
            <div className="text-sm font-semibold text-gray-200 mb-3">
              已安装 ({installed.length})
            </div>
            {installed.length === 0 ? (
              <div className="text-center py-8 text-gray-500 border border-dashed border-dark-border rounded-xl">
                <Box className="w-10 h-10 mx-auto mb-3 text-gray-600" />
                <p className="text-sm">暂无已安装的插件</p>
                <p className="text-xs text-gray-600 mt-1">从下方插件市场安装，或通过导入功能添加</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {installed.map(p => renderPkgCard(p, true))}
              </div>
            )}
          </div>

          {/* Marketplace */}
          <div>
            <div className="text-sm font-semibold text-gray-200 mb-3 mt-6">
              插件市场 ({marketplace.length})
            </div>
            {marketplace.length === 0 ? (
              <div className="text-center py-8 text-gray-500 border border-dashed border-dark-border rounded-xl">
                <Package className="w-10 h-10 mx-auto mb-3 text-gray-600" />
                <p className="text-sm">暂无可用插件</p>
                <p className="text-xs text-gray-600 mt-1">插件市场目前为空 — 使用下方的导入功能或发布新插件</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {marketplace.map(p => renderPkgCard(p, false))}
              </div>
            )}
          </div>
        </>
      )}

      {/* Detail Modal */}
      <Modal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={`插件详情: ${detailPkg?.name || ''}`}
        width={700}
        footer={<Button onClick={() => setDetailOpen(false)}>关闭</Button>}
      >
        {detailPkg && (
          <div className="space-y-3 text-sm text-gray-300">
            <div className="flex gap-3">
              <span className="text-gray-500 w-16 text-xs">名称</span>
              <span className="text-gray-200">{detailPkg.name}</span>
            </div>
            {(detailPkg as any).version && (
              <div className="flex gap-3">
                <span className="text-gray-500 w-16 text-xs">版本</span>
                <span className="text-gray-200 font-mono">v{(detailPkg as any).version}</span>
              </div>
            )}
            {(detailPkg as any).description && (
              <div className="flex gap-3">
                <span className="text-gray-500 w-16 text-xs">描述</span>
                <span className="text-gray-200">{(detailPkg as any).description}</span>
              </div>
            )}
            <div className="flex gap-3">
              <span className="text-gray-500 w-16 text-xs">作用域</span>
              <Badge variant="default">{(detailPkg as any).scope || 'workspace'}</Badge>
            </div>
            {((detailPkg as any).resources || []).length > 0 && (
              <div>
                <div className="text-xs text-gray-500 mb-2">资源清单</div>
                <div className="space-y-1">
                  {((detailPkg as any).resources || []).map((r: any) => {
                    const info = RESOURCE_ICONS[r.kind];
                    return (
                      <div key={`${r.kind}-${r.id}`} className="flex items-center gap-2 text-xs bg-dark-bg rounded px-3 py-1.5">
                        {info?.icon}
                        <span className="text-gray-400">{info?.label || r.kind}</span>
                        <span className="text-gray-200 font-mono">{r.id}</span>
                        {r.bundled && <Badge variant="default" className="text-[10px]">bundle</Badge>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Export Plugin Modal */}
      <Modal
        open={exportModal}
        onClose={() => { setExportModal(false); setSelectedAssets(new Set()); }}
        title="导出插件"
        width={650}
        footer={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => { setExportModal(false); setSelectedAssets(new Set()); }}>取消</Button>
            <Button variant="primary" onClick={handleExport} loading={exporting} disabled={selectedAssets.size === 0}>导出下载</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">插件名称</div>
              <input value={exportName} onChange={e => setExportName(e.target.value)} placeholder="my-plugin" className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-sm text-gray-200" />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">版本</div>
              <input value={exportVersion} onChange={e => setExportVersion(e.target.value)} placeholder="0.1.0" className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-sm text-gray-200" />
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">描述</div>
            <input value={exportDesc} onChange={e => setExportDesc(e.target.value)} placeholder="插件功能描述" className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-sm text-gray-200" />
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-2">
              选择资源 ({selectedAssets.size}/{exportAssets.length})
            </div>
            {exportAssets.length === 0 ? (
              <div className="text-xs text-gray-500 py-4 text-center">暂无 workspace 资产</div>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {exportAssets.map(a => {
                  const key = `${a.kind}:${a.id}`;
                  const info = RESOURCE_ICONS[a.kind];
                  const sel = selectedAssets.has(key);
                  return (
                    <div key={key}
                      onClick={() => toggleAsset(key)}
                      className={`flex items-center gap-2 px-3 py-2 rounded cursor-pointer transition-colors ${
                        sel ? 'bg-primary/10 border border-primary/30' : 'bg-dark-bg border border-dark-border hover:border-dark-border/80'
                      }`}
                    >
                      <input type="checkbox" checked={sel} onChange={() => toggleAsset(key)} className="accent-primary" />
                      <span className="text-xs">{info?.icon}</span>
                      <span className="text-xs text-gray-300 flex-1">{a.label}</span>
                      <Badge variant="default" className="text-[10px]">{a.kind}</Badge>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Plugins;
