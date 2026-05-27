import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, GitBranch, CheckCircle2, XCircle, Clock, ShieldCheck } from 'lucide-react';
import { Button, toast } from '../../../components/ui';
import ImportBar from '../../../components/workspace/ImportBar';
import { workflowApi, appApi, workflowTemplateApi } from '../../../services';

const WorkflowsPage: React.FC = () => {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [lastRuns, setLastRuns] = useState<Record<string, any>>({});
  const [pubApps, setPubApps] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r: any = await workflowApi.list();
      const wfs = r.workflows || [];
      setWorkflows(wfs);
      const runsMap: Record<string, any> = {};
      wfs.forEach((wf: any) => { if (wf.last_run) runsMap[wf.id] = wf.last_run; });
      setLastRuns(runsMap);
      try {
        const ar: any = await appApi.list();
        const pubMap: Record<string, any> = {};
        (ar.apps || []).forEach((a: any) => { pubMap[a.workflow_id] = a; });
        setPubApps(pubMap);
      } catch {}
    } catch { toast.error('加载失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleDelete = async (id: string) => {
    if (!window.confirm('确认删除此 workflow？')) return;
    try {
      await workflowApi.delete(id);
      toast.success('已删除');
      refresh();
    } catch (e: any) { toast.error('删除失败', e?.detail || ''); }
  };

  const handleSubmitForReview = async (wf: any) => {
    try {
      await workflowTemplateApi.submitForReview(wf.name);
      toast.success(`Workflow "${wf.name}" 已提交审批`);
      refresh();
    } catch (e: any) { toast.error('提交失败', e?.message || String(e)); }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Workflow</h1>
          <p className="text-xs text-gray-500 mt-1">管理你的 AI Workflow，拖拽节点构建流水线</p>
        </div>
        <Button icon={<Plus className="w-4 h-4" />} variant="primary" onClick={() => navigate('/core/workflows/new')}>
          新建 Workflow
        </Button>
      </div>

      <ImportBar assetType="workflows" alsoScan={['agents', 'skills', 'mcps']} onImported={() => refresh()} />

      {loading ? (
        <div className="text-center py-16 text-gray-500 text-sm">加载中...</div>
      ) : workflows.length === 0 ? (
        <div className="text-center py-16 space-y-4">
          <GitBranch className="w-12 h-12 mx-auto text-gray-700" />
          <div className="text-gray-500 text-sm">暂无 Workflow</div>
          <Button variant="secondary" onClick={() => navigate('/core/workflows/new')}>创建第一个 Workflow</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflows.map((wf: any) => {
            const nodeCount = (wf.nodes || []).length;
            const edgeCount = (wf.edges || []).length;
            const updated = wf.updated_at ? new Date(wf.updated_at * 1000).toLocaleDateString() : '';
            const lastRun = lastRuns[wf.id];
            const pubApp = pubApps[wf.id];
            const runPhase = lastRun?.phase || '';
            const wfEnabled = wf.enabled !== false; // default true
            return (
              <div key={wf.id} className={`rounded-xl border bg-dark-card hover:border-blue-500/30 transition-colors cursor-pointer ${wfEnabled ? 'border-dark-border' : 'border-dark-border opacity-70'}`} onClick={() => navigate(`/core/workflows/${wf.id}/edit`)}>
                <div className="p-4 pb-3">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <h3 className="text-sm font-semibold text-gray-100 truncate">{wf.name || '未命名'}</h3>
                    <div className="flex items-center gap-1">
                      {(wf.status && wf.status !== 'draft') ? (
                        <span className={`text-[8px] px-1 py-0 rounded border ${
                          wf.status === 'listed' ? 'text-green-400 border-green-500/30 bg-green-500/5' :
                          wf.status === 'published' ? 'text-blue-400 border-blue-500/30 bg-blue-500/5' :
                          wf.status === 'ready' ? 'text-amber-400 border-amber-500/30 bg-amber-500/5' :
                          'text-gray-400 border-gray-500/30'
                        }`}>
                          {wf.status === 'listed' ? '已上架' : wf.status === 'published' ? '已发布' : wf.status === 'ready' ? '待审核' : wf.status === 'deprecated' ? '已废弃' : wf.status}
                        </span>
                      ) : null}
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${wfEnabled ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-dark-bg text-gray-600 border border-dark-border'}`}>
                        {wfEnabled ? '已启用' : '已禁用'}
                      </span>
                    </div>
                  </div>
                  {wf.description && <p className="text-xs text-gray-500 mb-2 line-clamp-2">{wf.description}</p>}
                  {pubApp && <div className="mb-1"><span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/5 border border-blue-500/20 text-blue-400">已绑定 App: {pubApp.name}</span></div>}
                  <div className="flex items-center gap-3 text-[10px] text-gray-600">
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-blue-500/60" />{nodeCount} 节点</span>
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-purple-500/60" />{edgeCount} 连线</span>
                    {updated && <span className="text-gray-700">{updated}</span>}
                  </div>
                  <div className="flex items-center gap-3 mt-2 pt-2 border-t border-dark-border/20 text-[10px]">
                    {lastRun ? (
                      <span className="flex items-center gap-1">
                        {runPhase === 'done' ? <CheckCircle2 className="w-3 h-3 text-green-400" /> : runPhase === 'failed' ? <XCircle className="w-3 h-3 text-red-400" /> : <Clock className="w-3 h-3 text-amber-400" />}
                        <span className="text-gray-500">{runPhase === 'done' ? '上次执行成功' : runPhase === 'failed' ? '上次执行失败' : '执行中'}</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-gray-700"><Clock className="w-3 h-3" />暂无运行记录</span>
                    )}
                    <span className="text-gray-700 text-[9px] font-mono ml-auto">{wf.id.slice(0,8)}</span>
                  </div>
                </div>
                <div className="flex border-t border-dark-border/30 divide-x divide-dark-border/30">
                  <button onClick={e => { e.stopPropagation(); workflowApi.toggleEnabled(wf.id).then((r: any) => toast.success(r.enabled ? '已启用' : '已禁用')).catch(() => toast.error('切换失败')); refresh(); }}
                    className={`flex-1 flex items-center justify-center gap-1 py-2 text-[10px] transition-colors rounded-bl-xl ${wfEnabled ? 'text-green-400 hover:text-green-300 hover:bg-green-500/5' : 'text-gray-500 hover:text-gray-300 hover:bg-dark-hover'}`}>
                    {wfEnabled ? '✓ 已启用' : '✗ 已禁用'}
                  </button>
                  <button onClick={e => { e.stopPropagation(); navigate('/app/apps'); }}
                    className="flex-1 flex items-center justify-center gap-1 py-2 text-[10px] text-gray-500 hover:text-blue-400 hover:bg-dark-hover transition-colors">
                    📱 App
                  </button>
                  <button onClick={e => { e.stopPropagation(); handleDelete(wf.id); }}
                    className="flex-1 flex items-center justify-center gap-1 py-2 text-[10px] text-gray-500 hover:text-red-400 hover:bg-dark-hover rounded-br-xl transition-colors">
                    <Trash2 className="w-3 h-3" /> 删除
                  </button>
                  {(wf.status || '').toLowerCase() === 'draft' || !wf.status ? (
                    <button onClick={e => { e.stopPropagation(); handleSubmitForReview(wf); }}
                      className="flex-1 flex items-center justify-center gap-1 py-2 text-[10px] text-amber-400 hover:text-amber-300 hover:bg-amber-400/5 transition-colors">
                      <ShieldCheck className="w-3 h-3" /> 提交审批
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
};

export default WorkflowsPage;
