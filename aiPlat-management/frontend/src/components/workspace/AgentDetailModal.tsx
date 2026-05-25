import React, { useState, useEffect } from 'react';
import { Modal, Button, Input, toast } from '../ui';
import { workspaceAgentApi, skillApi, toolApi, packagesApi } from '../../services';
import type { Agent } from '../../services';

interface AgentDetailModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const typeLabels: Record<string, string> = {
  base: '基础', react: 'ReAct', plan: '规划型', tool: '工具型', rag: 'RAG', conversational: '对话型',
};

const statusConfig: Record<string, { color: string; text: string }> = {
  running: { color: 'text-green-300', text: '运行中' },
  idle: { color: 'text-yellow-300', text: '空闲' },
  stopped: { color: 'text-red-300', text: '已停止' },
  error: { color: 'text-red-300', text: '错误' },
  pending: { color: 'text-gray-400', text: '待启动' },
  ready: { color: 'text-gray-300', text: '就绪' },
};

const AgentDetailModal: React.FC<AgentDetailModalProps> = ({ open, agent, onClose }) => {
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const [skillMap, setSkillMap] = useState<Record<string, string>>({});
  const [toolMap, setToolMap] = useState<Record<string, string>>({});
  const [sop, setSop] = useState<string | null>(null);
  const [sopLoading, setSopLoading] = useState(false);
  const [versions, setVersions] = useState<any[] | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [history, setHistory] = useState<any[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [pubName, setPubName] = useState('');
  const [pubLoading, setPubLoading] = useState(false);

  useEffect(() => {
    if (open && agent) {
      setLoading(true);
      Promise.all([
        workspaceAgentApi.get(agent.id),
        skillApi.list({ limit: 500 }).catch(() => ({ skills: [] })),
        toolApi.list({ limit: 200 }).catch(() => ({ tools: [] })),
      ]).then(([res, skillList, toolList]: [any, any, any]) => {
        setDetail(res);
        const sItems = skillList?.skills || skillList?.items || skillList || [];
        if (Array.isArray(sItems)) {
          const map: Record<string, string> = {};
          sItems.forEach((s: any) => { map[s.id] = s.name || s.id; });
          setSkillMap(map);
        }
        const tItems = toolList?.tools || toolList?.items || toolList || [];
        if (Array.isArray(tItems)) {
          const map: Record<string, string> = {};
          tItems.forEach((t: any) => { map[t.name] = t.description || t.name; });
          setToolMap(map);
        }
      }).catch(() => setDetail(null)).finally(() => setLoading(false));
      setSop(null);
      setVersions(null);
    } else {
      setDetail(null);
      setSop(null);
      setVersions(null);
    }
  }, [open, agent]);

  const loadSop = () => {
    if (!agent) return;
    setSopLoading(true);
    workspaceAgentApi.getSop(agent.id).then((r: any) => setSop(r?.sop || '(无内容)')).catch(() => setSop('(加载失败)')).finally(() => setSopLoading(false));
  };

  const loadVersions = () => {
    if (!agent) return;
    setVersionsLoading(true);
    workspaceAgentApi.getVersions(agent.id).then((r: any) => setVersions(r?.versions || [])).catch(() => setVersions([])).finally(() => setVersionsLoading(false));
  };

  const handleRollback = async (version: string) => {
    if (!agent || !confirm(`回滚到版本 ${version}？`)) return;
    try { await workspaceAgentApi.rollbackVersion(agent.id, version); setVersions(null); loadVersions(); }
    catch (e: any) { alert('回滚失败: ' + (e?.message || 'unknown')); }
  };

  const loadHistory = () => {
    if (!agent) return;
    setHistoryLoading(true);
    workspaceAgentApi.getHistory(agent.id).then((r: any) => setHistory(r?.history || [])).catch(() => setHistory([])).finally(() => setHistoryLoading(false));
  };

  if (!agent) return null;

  const statusCfg = statusConfig[agent.status] || { color: 'text-gray-400', text: agent.status };
  const skills = detail?.skills || agent.skills || [];
  const tools = detail?.tools || agent.tools || [];
  const mcpIds = (detail?.mcp_ids || (agent as any)?.mcp_ids || []) as string[];
  const workflowIds = (detail?.workflow_ids || (agent as any)?.workflow_ids || []) as string[];
  const boundAgentIds = (detail?.agent_ids || (agent as any)?.agent_ids || []) as string[];
  const config = detail?.config || {};
  const displayName = detail?.display_name || agent.name;
  const description = detail?.description || '';
  const category = detail?.category || '';
  const tags: string[] = detail?.tags || [];
  const phase = detail?.phase || '';

  const resolveSkillName = (id: string) => skillMap[id] || id;
  const resolveToolName = (id: string) => toolMap[id] || id;

  const handlePublish = async () => {
    if (!agent || !pubName.trim()) { toast.error('请输入包名称'); return; }
    setPubLoading(true);
    try {
      await packagesApi.publish(pubName.trim(), { source_path: `~/.aiplat/workspace/agents/${agent.id}` });
      toast.success(`已发布 ${pubName.trim()}`);
      setPublishOpen(false); setPubName('');
    } catch (e: any) { toast.error(`发布失败：${e?.message || e}`); }
    finally { setPubLoading(false); }
  };

  return (<>
    <Modal open={open} onClose={onClose} title={displayName} width={700}
      footer={<>
        <Button variant="secondary" onClick={() => setPublishOpen(true)}>发布到商城</Button>
        <Button onClick={onClose}>关闭</Button>
      </>}>
      {loading ? (
        <div className="flex items-center justify-center py-8"><div className="text-gray-400">加载中...</div></div>
      ) : (
        <div className="space-y-5">
          {description && <div className="text-sm text-gray-300 leading-relaxed">{description}</div>}

          <div className="grid grid-cols-3 gap-4">
            <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
              <div className="text-xs text-gray-400 mb-1">ID</div>
              <div className="text-sm text-gray-100 font-mono">{agent.id}</div>
            </div>
            <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
              <div className="text-xs text-gray-400 mb-1">类型</div>
              <div className="text-sm text-gray-100">{typeLabels[agent.agent_type] || agent.agent_type}</div>
            </div>
            <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
              <div className="text-xs text-gray-400 mb-1">状态</div>
              <div className={`text-sm font-medium ${statusCfg.color}`}>{statusCfg.text}</div>
            </div>
          </div>

          {(category || phase || tags.length > 0) && (
            <div className="flex flex-wrap items-center gap-2">
              {category && <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/25">{category}</span>}
              {phase && <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-amber-500/15 text-amber-300 border border-amber-500/25">{phase}</span>}
              {tags.map((t: string) => <span key={t} className="inline-flex px-2 py-0.5 rounded text-xs bg-gray-500/15 text-gray-400 border border-gray-500/25">{t}</span>)}
            </div>
          )}

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">绑定技能 ({skills.length})</div>
            {skills.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {skills.map((id: string) => <span key={id} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-blue-500/15 text-blue-300 border border-blue-500/25" title={id}>{resolveSkillName(id)}</span>)}
              </div>
            ) : <div className="text-sm text-gray-500 py-2">暂未绑定技能</div>}
          </div>

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">绑定工具 ({tools.length})</div>
            {tools.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {tools.map((id: string) => <span key={id} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-purple-500/15 text-purple-300 border border-purple-500/25" title={id}>{resolveToolName(id)}</span>)}
              </div>
            ) : <div className="text-sm text-gray-500 py-2">暂未绑定工具</div>}
          </div>

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">绑定 MCP ({mcpIds.length})</div>
            {mcpIds.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {mcpIds.map((id: string) => <span key={id} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/25">{id}</span>)}
              </div>
            ) : <div className="text-sm text-gray-500 py-2">暂未绑定 MCP</div>}
          </div>

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">绑定 Workflow ({workflowIds.length})</div>
            {workflowIds.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {workflowIds.map((id: string) => <span key={id} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-orange-500/15 text-orange-300 border border-orange-500/25">{id}</span>)}
              </div>
            ) : <div className="text-sm text-gray-500 py-2">暂未绑定 Workflow</div>}
          </div>

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">子 Agent ({boundAgentIds.length})</div>
            {boundAgentIds.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {boundAgentIds.map((id: string) => <span key={id} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-rose-500/15 text-rose-300 border border-rose-500/25">{id}</span>)}
              </div>
            ) : <div className="text-sm text-gray-500 py-2">未绑定子 Agent</div>}
          </div>

          {config && Object.keys(config).length > 0 && (
            <div>
              <div className="text-sm text-gray-400 mb-1 font-medium">配置</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(config).map(([k,v]) => (
                  <span key={k} className="text-xs px-2 py-0.5 rounded bg-dark-bg border border-dark-border text-gray-400">{k}: <span className="text-gray-200">{String(v)}</span></span>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-gray-400 font-medium">AGENT.md</div>
              {sop === null ? <button onClick={loadSop} disabled={sopLoading} className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600">{sopLoading ? '加载中...' : '查看内容'}</button>
              : <button onClick={() => setSop(null)} className="text-xs text-gray-500 hover:text-gray-400">收起</button>}
            </div>
            {sop !== null && <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto whitespace-pre-wrap" style={{ maxHeight: 300 }}>{sop}</pre>}
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-gray-400 font-medium">版本历史</div>
              {versions === null ? <button onClick={loadVersions} disabled={versionsLoading} className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600">{versionsLoading ? '加载中...' : '查看历史'}</button>
              : <button onClick={() => setVersions(null)} className="text-xs text-gray-500 hover:text-gray-400">收起</button>}
            </div>
            {versions !== null && versions.length > 0 && (
              <div className="space-y-1 max-h-40 overflow-auto">
                {versions.map((v, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-dark-card border border-dark-border">
                    <span className="text-gray-300">{v.version}</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs ${v.status === 'current' ? 'bg-green-900/50 text-green-300' : 'bg-gray-700/50 text-gray-400'}`}>{v.status || 'past'}</span>
                    <span className="text-gray-500">{v.created_at?.slice(0,19) || ''}</span>
                    {v.status !== 'current' && <button onClick={() => handleRollback(v.version)} className="text-amber-400 hover:text-amber-300 ml-2">回滚</button>}
                  </div>
                ))}
              </div>
            )}
            {versions !== null && versions.length === 0 && <div className="text-xs text-gray-500">暂无版本记录</div>}
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-gray-400 font-medium">执行历史</div>
              {history === null ? (
                <button onClick={loadHistory} disabled={historyLoading} className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600">{historyLoading ? '加载中...' : '查看历史'}</button>
              ) : (
                <button onClick={() => setHistory(null)} className="text-xs text-gray-500 hover:text-gray-400">收起</button>
              )}
            </div>
            {history !== null && history.length > 0 && (
              <div className="space-y-2 max-h-60 overflow-auto">
                {history.slice(0, 10).map((h: any, i: number) => (
                  <div key={i} className="p-2 rounded bg-dark-card border border-dark-border text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-500 font-mono">{h.id?.slice(0,20)}...</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${h.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>{h.status}</span>
                    </div>
                    <div className="text-gray-400 truncate">{typeof h.input === 'string' ? h.input.slice(0, 100) : JSON.stringify(h.input)?.slice(0, 100)}</div>
                  </div>
                ))}
              </div>
            )}
            {history !== null && history.length === 0 && <div className="text-xs text-gray-500">暂无执行记录</div>}
          </div>
        </div>
      )}
    </Modal>

    <Modal open={publishOpen} onClose={() => setPublishOpen(false)} title="发布到商城" width={440}
      footer={<>
        <Button variant="secondary" onClick={() => setPublishOpen(false)}>取消</Button>
        <Button variant="primary" loading={pubLoading} onClick={handlePublish}>发布</Button>
      </>}>
      <div className="space-y-4">
        <div className="text-sm text-gray-300">将当前 Agent (<span className="text-primary">{agent?.name}</span>) 打包发布到商城。</div>
        <Input label="包名称" value={pubName} onChange={e => setPubName(e.target.value)} placeholder={agent?.id || 'my-agent-package'} />
        <div className="text-xs text-gray-500">发布后可在商城的「已发布包」Tab 中查看和安装</div>
      </div>
    </Modal>
    </>
  );
};

export default AgentDetailModal;
