import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, Code, Webhook, Trash2, ExternalLink, Plus, Sparkles, Layers, FolderOpen } from 'lucide-react';
import { toast } from '../../../components/ui';
import { appApi, workflowApi } from '../../../services';

const MODE_ICONS: Record<string, React.FC<any>> = { chat: MessageSquare, api: Code, webhook: Webhook, studio: ExternalLink };
const MODE_LABELS: Record<string, string> = { chat: 'Chat 对话', api: 'API 端点', webhook: 'Webhook', studio: '独立应用', dashboard: '应用工厂' };
const MODE_COLORS: Record<string, string> = { chat: 'border-blue-500/20 bg-blue-500/5 text-blue-400', api: 'border-green-500/20 bg-green-500/5 text-green-400', webhook: 'border-purple-500/20 bg-purple-500/5 text-purple-400', studio: 'border-purple-500/20 bg-purple-500/5 text-purple-400', dashboard: 'border-amber-500/20 bg-amber-500/5 text-amber-400' };

type AppFilter = 'all' | 'workflow' | 'studio' | 'factory';

const AppsPage: React.FC = () => {
  const navigate = useNavigate();
  const [apps, setApps] = useState<any[]>([]);
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newWfId, setNewWfId] = useState('');
  const [newMode, setNewMode] = useState('chat');
  const [filter, setFilter] = useState<AppFilter>('all');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r: any = await appApi.list();
      setApps(r.apps || []);
      const wr: any = await workflowApi.list();
      setWorkflows((wr.workflows || []).filter((w: any) => w.enabled !== false));
    } catch { toast.error('加载失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleDelete = async (id: string) => {
    if (deleting) return;
    if (!window.confirm('确认删除此 App？')) return;
    setDeleting(id);
    try { await appApi.delete(id); toast.success('已删除'); refresh(); }
    catch (e: any) { toast.error('删除失败', e?.detail || ''); }
    finally { setDeleting(null); }
  };

  const handleOpen = (app: any) => {
    if (app.mode === 'dashboard' || app.capability_type === 'factory') {
      const url = app.app_url;
      if (url) window.open(url, '_blank');
      else navigate(`/app/apps/${app.capability_id}`);
    } else if (app.mode === 'studio' || app.capability_type === 'studio') {
      const url = app.app_url || (app.description || '').replace('Studio 生成 · ', '');
      if (url) window.open(url, '_blank');
    } else if (app.mode === 'chat') navigate(`/app/apps/${app.id}/chat`);
    else if (app.mode === 'api') navigate(`/app/apps/${app.id}/api`);
    else navigate(`/app/apps/${app.id}/webhook`);
  };

  const filteredApps = filter === 'all'
    ? apps
    : filter === 'studio'
      ? apps.filter((a: any) => a.capability_type === 'studio' || a.mode === 'studio')
      : filter === 'factory'
        ? apps.filter((a: any) => a.capability_type === 'factory' || a.mode === 'dashboard')
        : apps.filter((a: any) => a.capability_type !== 'studio' && a.capability_type !== 'factory' && a.mode !== 'studio' && a.mode !== 'dashboard');

  return (
    <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-gray-100">已部署应用</h1>
            <p className="text-xs text-gray-500 mt-1">AI 应用工厂 + Workflow 发布 + Studio 生成的已部署应用</p>
          </div>
          <button onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-blue-500/20 border border-blue-500/30 text-blue-300 hover:bg-blue-500/30 transition-colors text-xs">
            <Plus className="w-3.5 h-3.5" /> 新建 App
          </button>
        </div>

        {/* Type filter tabs */}
        <div className="flex gap-2">
          {[
            { key: 'all' as AppFilter, label: '全部', icon: Layers },
            { key: 'factory' as AppFilter, label: '应用工厂', icon: FolderOpen },
            { key: 'workflow' as AppFilter, label: 'Workflow 发布', icon: Code },
            { key: 'studio' as AppFilter, label: 'Studio 生成', icon: Sparkles },
          ].map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors ${
                filter === key
                  ? 'bg-blue-500/20 border-blue-500/30 text-blue-300'
                  : 'bg-dark-bg border-dark-border text-gray-500 hover:text-gray-300'
              }`}
            >
              <Icon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
        </div>

      {loading ? (
        <div className="text-center py-16 text-gray-500 text-sm">加载中...</div>
      ) : filteredApps.length === 0 ? (
        <div className="text-center py-16 space-y-4">
          <ExternalLink className="w-12 h-12 mx-auto text-gray-700" />
          <div className="text-gray-500 text-sm">
            {filter === 'studio' ? '暂无 Studio 生成的已部署应用' : filter === 'workflow' ? '暂无 Workflow 发布的 App' : '暂无已部署的应用'}
          </div>
          <p className="text-xs text-gray-600">
            {filter === 'studio' ? '在 App Studio 中生成应用并部署后，会出现在这里。' : '在 Workflow 列表中找到你的工作流，点击"发布"按钮来创建 App'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredApps.map((app: any) => {
            const isStudio = app.capability_type === 'studio' || app.mode === 'studio';
            const Icon = MODE_ICONS[app.mode] || MessageSquare;
            const appUrl = app.app_url || (app.description || '').replace('Studio 生成 · ', '');
            return (
              <div key={app.id} className="rounded-xl border border-dark-border bg-dark-card hover:border-blue-500/30 transition-colors">
                <div className="p-4 pb-3 cursor-pointer" onClick={() => handleOpen(app)}>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <h3 className="text-sm font-semibold text-gray-100 truncate">{app.name}</h3>
                      {isStudio && (
                        <span className="flex-shrink-0 text-[9px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 border border-purple-500/30">Studio</span>
                      )}
                    </div>
                    <span className={`flex-shrink-0 text-[9px] px-1.5 py-0.5 rounded border ${MODE_COLORS[app.mode] || ''}`}>{MODE_LABELS[app.mode] || app.mode}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-gray-600">
                    {isStudio ? (
                      <span className="truncate">{appUrl || app.project_id || app.id?.slice(0, 12)}</span>
                    ) : (
                      <span>源: {app.workflow_name || app.workflow_id?.slice(0, 12)}</span>
                    )}
                  </div>
                  {app.description && !isStudio && <p className="text-[10px] text-gray-500 mt-1 line-clamp-1">{app.description}</p>}
                </div>
                <div className="flex border-t border-dark-border/30 divide-x divide-dark-border/30">
                  <button onClick={e => { e.stopPropagation(); handleOpen(app); }}
                    className="flex-1 flex items-center justify-center gap-1 py-2 text-[10px] text-gray-500 hover:text-blue-400 hover:bg-dark-hover rounded-bl-xl transition-colors">
                    <Icon className="w-3 h-3" /> {isStudio ? '打开' : '打开'}
                  </button>
                  <button onClick={e => { e.stopPropagation(); handleDelete(app.id); }} disabled={!!deleting}
                    className="flex-1 flex items-center justify-center gap-1 py-2 text-[10px] text-gray-500 hover:text-red-400 hover:bg-dark-hover rounded-br-xl transition-colors disabled:opacity-40">
                    <Trash2 className="w-3 h-3" /> 删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {createOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setCreateOpen(false)}>
          <div className="bg-dark-card border border-dark-border rounded-xl p-6 w-[400px] space-y-4" onClick={e => e.stopPropagation()}>
            <h2 className="text-sm font-semibold text-gray-100">新建 App</h2>
            <div><div className="text-xs text-gray-500 mb-1">名称</div><input value={newName} onChange={e => setNewName(e.target.value)} className="w-full h-10 px-3 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100" placeholder="App 名称" /></div>
            <div><div className="text-xs text-gray-500 mb-1">选择 Workflow</div>
              <select value={newWfId} onChange={e => setNewWfId(e.target.value)} className="w-full h-10 px-3 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100">
                <option value="">选择已启用的 Workflow...</option>
                {workflows.map((wf: any) => <option key={wf.id} value={wf.id}>{wf.name || wf.id.slice(0,12)} ({wf.nodes?.length || 0} 节点)</option>)}
              </select>
            </div>
            <div><div className="text-xs text-gray-500 mb-1">类型</div>
              <div className="flex gap-2">
                {['chat','api','webhook'].map(m => <button key={m} onClick={() => setNewMode(m)}
                  className={`flex-1 py-2 rounded-lg text-xs border transition-colors ${newMode===m ? 'bg-blue-500/20 border-blue-500/30 text-blue-300' : 'bg-dark-bg border-dark-border text-gray-500'}`}>
                  {m==='chat'?'💬 Chat':m==='api'?'⚡ API':'🪝 Webhook'}
                </button>)}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setCreateOpen(false)} className="px-3 py-1.5 rounded text-xs text-gray-500 hover:text-gray-300">取消</button>
              <button onClick={async () => {
                if (!newName.trim() || !newWfId) { toast.error('请输入名称并选择 Workflow'); return; }
                try { await appApi.create({ name: newName.trim(), workflow_id: newWfId, mode: newMode }); toast.success('创建成功'); setCreateOpen(false); setNewName(''); setNewWfId(''); refresh(); }
                catch (e: any) { toast.error('创建失败', e?.detail || ''); }
              }} className="px-3 py-1.5 rounded text-xs bg-blue-500/20 text-blue-300 hover:bg-blue-500/30">创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AppsPage;
