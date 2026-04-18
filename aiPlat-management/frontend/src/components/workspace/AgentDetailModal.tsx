import React, { useState, useEffect } from 'react';
import { Modal, Button } from '../ui';
import { workspaceAgentApi } from '../../services/coreApi';
import type { Agent } from '../../services';

interface AgentDetailModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const typeLabels: Record<string, string> = {
  base: '基础',
  react: 'ReAct',
  plan: '规划型',
  tool: '工具型',
  rag: 'RAG',
  conversational: '对话型',
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
  useEffect(() => {
    if (open && agent) {
      setLoading(true);
      workspaceAgentApi.get(agent.id).then((res: any) => {
        setDetail(res);
      }).catch(() => {
        setDetail(null);
      }).finally(() => {
        setLoading(false);
      });
    } else {
      setDetail(null);
    }
  }, [open, agent]);

  if (!agent) return null;

  const statusCfg = statusConfig[agent.status] || { color: 'text-gray-400', text: agent.status };
  const skills = detail?.skills || agent.skills || [];
  const tools = detail?.tools || agent.tools || [];
  const config = detail?.config || {};
  const configStr = config && Object.keys(config).length > 0 ? JSON.stringify(config, null, 2) : null;
  const memoryConfig = (detail as any)?.memory_config || (agent as any)?.memory_config || null;
  const memoryConfigStr = memoryConfig ? JSON.stringify(memoryConfig, null, 2) : null;
  const description = String((detail as any)?.metadata?.description || (agent as any)?.metadata?.description || '');

  return (
    <Modal open={open} onClose={onClose} title={agent.name} width={700} footer={<Button onClick={onClose}>关闭</Button>}>
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-400">加载中...</div>
        </div>
      ) : (
        <div className="space-y-5">
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

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">绑定技能 ({skills.length})</div>
            {skills.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {skills.map((skillId: string) => (
                  <span key={skillId} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-blue-500/15 text-blue-300 border border-blue-500/25">
                    {skillId}
                  </span>
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-500 py-2">暂未绑定技能</div>
            )}
          </div>

          <div>
            <div className="text-sm text-gray-400 mb-2 font-medium">绑定工具 ({tools.length})</div>
            {tools.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {tools.map((toolId: string) => (
                  <span key={toolId} className="inline-flex px-2.5 py-1 rounded-md text-xs font-medium bg-purple-500/15 text-purple-300 border border-purple-500/25">
                    {toolId}
                  </span>
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-500 py-2">暂未绑定工具</div>
            )}
          </div>

          {configStr && (
            <div>
              <div className="text-sm text-gray-400 mb-1 font-medium">配置</div>
              <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto" style={{ maxHeight: 200 }}>
                {configStr}
              </pre>
            </div>
          )}

          {description && (
            <div>
              <div className="text-sm text-gray-400 mb-1 font-medium">描述</div>
              <div className="text-sm text-gray-300 whitespace-pre-wrap">{description}</div>
            </div>
          )}

          {memoryConfigStr && (
            <div>
              <div className="text-sm text-gray-400 mb-1 font-medium">memory_config</div>
              <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto" style={{ maxHeight: 200 }}>
                {memoryConfigStr}
              </pre>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default AgentDetailModal;
