import React, { useEffect, useMemo, useState } from 'react';
import { agentApi } from '../../services';
import type { Agent } from '../../services';
import { Alert, Button, Input, Modal, Textarea, toast } from '../ui';

interface AgentConfigTemplate {
  name: string;
  description: string;
  config: Record<string, unknown>;
}

const AGENT_TYPE_TEMPLATES: Record<string, AgentConfigTemplate> = {
  base: {
    name: '基础Agent',
    description: '最基础的对话Agent，适用于简单问答场景',
    config: {
      model: 'gpt-4',
      temperature: 0.7,
      max_tokens: 2048,
      system_prompt: '你是一个有帮助的AI助手。',
    },
  },
  react: {
    name: 'ReAct Agent',
    description: '使用ReAct（Reasoning + Acting）模式，具备推理和工具调用能力',
    config: {
      model: 'gpt-4',
      temperature: 0.0,
      max_tokens: 4096,
      reasoning_steps: 3,
      tools: ['search', 'calculator', 'code_interpreter'],
      system_prompt: '你是一个使用ReAct模式的推理Agent。对于每个问题，你需要：1) Thought - 思考需要做什么 2) Action - 执行动作 3) Observation - 观察结果。',
    },
  },
  plan: {
    name: '规划型Agent',
    description: '具备任务分解和规划能力，适合复杂多步骤任务',
    config: {
      model: 'gpt-4',
      temperature: 0.1,
      max_tokens: 8192,
      planning_enabled: true,
      max_subtasks: 10,
      system_prompt: '你是一个任务规划Agent。分析用户需求，将其分解为可执行的子任务，逐步完成。',
    },
  },
  tool: {
    name: '工具型Agent',
    description: '专注于工具调用和自动化执行的Agent',
    config: {
      model: 'gpt-4',
      temperature: 0.0,
      max_tokens: 2048,
      tools: [
        { name: 'web_search', description: '网络搜索', parameters: { query: 'string' } },
        { name: 'code_execute', description: '代码执行', parameters: { code: 'string', language: 'string' } },
        { name: 'file_read', description: '读取文件', parameters: { path: 'string' } },
        { name: 'file_write', description: '写入文件', parameters: { path: 'string', content: 'string' } },
        { name: 'database_query', description: '数据库查询', parameters: { sql: 'string' } },
      ],
      system_prompt: '你是一个工具型Agent。根据用户需求选择合适的工具完成任务。',
    },
  },
};

interface EditAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditAgentModal: React.FC<EditAgentModalProps> = ({ open, agent, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [configText, setConfigText] = useState('');

  useEffect(() => {
    if (open && agent) {
      setName(agent.name || '');
      setConfigText(agent.metadata?.config ? JSON.stringify(agent.metadata.config, null, 2) : '');
    }
  }, [open, agent]);

  const handleSubmit = async () => {
    if (!agent) return;
    try {
      if (!name.trim()) {
        toast.error('请输入 Agent 名称');
        return;
      }
      setLoading(true);

      let config: Record<string, unknown> = {};
      if (configText?.trim()) {
        try {
          config = JSON.parse(configText);
        } catch {
          toast.error('配置 JSON 格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      await agentApi.update(agent.id, { config });
      toast.success(`Agent "${agent.name}" 更新成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.message) {
        toast.error('更新失败', String(error.message || ''));
      }
    } finally {
      setLoading(false);
    }
  };

  const currentTemplate = agent ? AGENT_TYPE_TEMPLATES[agent.agent_type] : null;
  const configHint = useMemo(() => `以下是 ${currentTemplate?.name || ''} 的配置示例，可直接复制修改：`, [currentTemplate?.name]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="编辑 Agent"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} />

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">类型</div>
          <div className="text-sm text-gray-100 bg-dark-bg border border-dark-border rounded-lg px-3 h-10 flex items-center">
            {agent?.agent_type || '-'}
          </div>
        </div>

        {currentTemplate && (
          <Alert type="info" title={currentTemplate.name}>
            {currentTemplate.description}
          </Alert>
        )}

        <Textarea
          label="配置（JSON）"
          value={configText}
          onChange={(e: any) => setConfigText(e.target.value)}
          rows={10}
        />
        {currentTemplate && <div className="text-xs text-gray-500">{configHint}</div>}
      </div>
    </Modal>
  );
};

export default EditAgentModal;
