import React, { useEffect, useState } from 'react';
import { Button, Card, CardContent, CardHeader, Input, Modal, toast } from '../../../components/ui';
import { packagesApi } from '../../../services';

interface PkgInfo { name: string; versions: number; installed: boolean; }
interface InstallEntry { name: string; version: string; installed_at: number; }

const PackagesPage: React.FC = () => {
  const [packages, setPackages] = useState<PkgInfo[]>([]);
  const [installs, setInstalls] = useState<InstallEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [pubName, setPubName] = useState('');
  const [pubPath, setPubPath] = useState('');
  const [pubLoading, setPubLoading] = useState(false);
  const [instLoading, setInstLoading] = useState<string | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [pkgs, inst] = await Promise.all([packagesApi.list(), packagesApi.listInstalls()]);
      setPackages((pkgs as any).packages || []);
      setInstalls((inst as any).installs || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const handlePublish = async () => {
    if (!pubName.trim() || !pubPath.trim()) { toast.error('名称和路径必填'); return; }
    setPubLoading(true);
    try {
      await packagesApi.publish(pubName.trim(), { source_path: pubPath.trim() });
      toast.success(`已发布 ${pubName.trim()}`);
      setPublishOpen(false); setPubName(''); setPubPath('');
      await fetchAll();
    } catch (e: any) { toast.error(`发布失败：${e?.message || e}`); }
    finally { setPubLoading(false); }
  };

  const handleInstall = async (name: string) => {
    setInstLoading(name);
    try {
      await packagesApi.install(name, {});
      toast.success(`已安装 ${name}`);
      await fetchAll();
    } catch (e: any) { toast.error(`安装失败：${e?.message || e}`); }
    finally { setInstLoading(null); }
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`确认卸载 ${name}？`)) return;
    try {
      await packagesApi.uninstall(name);
      toast.success(`已卸载 ${name}`);
      await fetchAll();
    } catch (e: any) { toast.error(`卸载失败：${e?.message || e}`); }
  };

  const installedSet = new Set(installs.map(i => i.name));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-100">包管理</h1>
        <Button variant="primary" size="sm" onClick={() => setPublishOpen(true)}>发布新包</Button>
      </div>

      <Card>
        <CardHeader><div className="font-semibold text-gray-100">可用包</div></CardHeader>
        <CardContent>
          {loading ? <div className="text-sm text-gray-500 py-4 text-center">加载中...</div> :
           packages.length === 0 ? <div className="text-sm text-gray-500 py-8 text-center">暂无包，点击"发布新包"创建</div> :
           <div className="space-y-1">
             {packages.map((pkg) => (
               <div key={pkg.name} className="flex items-center justify-between py-2 px-3 rounded-lg border border-dark-border bg-dark-card/50">
                 <div>
                   <span className="text-sm text-gray-200 font-medium">{pkg.name}</span>
                   <span className="ml-2 text-xs text-gray-500">{pkg.versions} 版本</span>
                   {installedSet.has(pkg.name) && <span className="ml-2 text-xs text-green-400">已安装</span>}
                 </div>
                 <div className="flex gap-2">
                   {!installedSet.has(pkg.name) ? (
                     <Button variant="primary" size="sm" loading={instLoading === pkg.name} onClick={() => handleInstall(pkg.name)}>安装</Button>
                   ) : (
                     <Button variant="ghost" size="sm" onClick={() => handleUninstall(pkg.name)}>卸载</Button>
                   )}
                 </div>
               </div>
             ))}
           </div>
          }
        </CardContent>
      </Card>

      <Card>
        <CardHeader><div className="font-semibold text-gray-100">已安装</div></CardHeader>
        <CardContent>
          {installs.length === 0 ? <div className="text-sm text-gray-500 py-4 text-center">暂无安装记录</div> :
           <div className="space-y-1">
             {installs.map((inst) => (
               <div key={inst.name} className="flex items-center justify-between py-2 px-3 rounded-lg border border-dark-border bg-dark-card/50">
                 <span className="text-sm text-gray-200">{inst.name} <span className="text-xs text-gray-500">v{inst.version}</span></span>
                 <Button variant="ghost" size="sm" onClick={() => handleUninstall(inst.name)}>卸载</Button>
               </div>
             ))}
           </div>
          }
        </CardContent>
      </Card>

      <Modal open={publishOpen} onClose={() => setPublishOpen(false)} title="发布新包" width={480}
        footer={<>
          <Button variant="secondary" onClick={() => setPublishOpen(false)}>取消</Button>
          <Button variant="primary" loading={pubLoading} onClick={handlePublish}>发布</Button>
        </>}>
        <div className="space-y-4">
          <Input label="包名称" value={pubName} onChange={e => setPubName(e.target.value)} placeholder="my-agent-package" />
          <Input label="源路径" value={pubPath} onChange={e => setPubPath(e.target.value)} placeholder="~/.aiplat/workspace/agents/my-agent" />
          <div className="text-xs text-gray-500">包目录结构：agents/&#123;name&#125;/AGENT.md, skills/&#123;name&#125;/SKILL.md, mcp/&#123;name&#125;/manifest.yaml, hooks/&#123;name&#125;/hook.yaml</div>
        </div>
      </Modal>
    </div>
  );
};

export default PackagesPage;
