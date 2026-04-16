import React, { useEffect, useMemo, useState } from 'react';
import { agentApi, skillApi, toolApi } from '../../services';
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

interface AddAgentModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const AddAgentModal: React.FC<AddAgentModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('base');
  const [name, setName] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [configText, setConfigText] = useState('');
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);

  useEffect(() => {
    if (open) {
      setSelectedType('base');
      setName('');
      setSkills([]);
      setTools([]);
      setConfigText(JSON.stringify(AGENT_TYPE_TEMPLATES.base.config, null, 2));
      fetchOptions();
    }
  }, [open]);

  const fetchOptions = async () => {
    try {
      const [skillRes, toolRes] = await Promise.all([
        skillApi.list({ limit: 100 }),
        toolApi.list({ limit: 100 }),
      ]);
      setSkillOptions((skillRes.skills || []).map((s: any) => ({ value: s.id, label: s.name })));
      setToolOptions((toolRes.tools || []).map((t: any) => ({ value: t.name, label: t.description || t.name })));
    } catch {
      setSkillOptions([]);
      setToolOptions([]);
    }
  };

  const handleTypeChange = (type: string) => {
    setSelectedType(type);
    const template = AGENT_TYPE_TEMPLATES[type];
    if (template) {
      setConfigText(JSON.stringify(template.config, null, 2));
    }
  };

  const handleSubmit = async () => {
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

      await agentApi.create({
        name: name.trim(),
        agent_type: selectedType || 'base',
        config,
        skills,
        tools,
      });
      toast.success(`Agent "${name.trim()}" 创建成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.message) {
        toast.error('创建失败', String(error.message || ''));
      }
    } finally {
      setLoading(false);
    }
  };

  const template = AGENT_TYPE_TEMPLATES[selectedType];
  const configHint = useMemo(() => `以下是 ${template?.name || ''} 的配置示例，可直接复制修改：`, [template?.name]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="创建 Agent"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            创建
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：数据分析助手" />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">类型</div>
            <select
              value={selectedType}
              onChange={(e) => handleTypeChange(e.target.value)}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              <option value="base">基础 - 简单对话</option>
              <option value="react">ReAct - 推理+行动</option>
              <option value="plan">规划型 - 任务分解</option>
              <option value="tool">工具型 - 工具调用</option>
            </select>
          </div>

          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">绑定技能（多选）</div>
            <select
              multiple
              value={skills}
              onChange={(e) => setSkills(Array.from(e.target.selectedOptions).map((o) => o.value))}
              className="w-full h-28 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              {skillOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <div className="text-xs text-gray-500 mt-1">按住 Ctrl/Cmd 可多选</div>
          </div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">绑定工具（多选）</div>
          <select
            multiple
            value={tools}
            onChange={(e) => setTools(Array.from(e.target.selectedOptions).map((o) => o.value))}
            className="w-full h-28 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            {toolOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {template && (
          <Alert type="info" title={template.name}>
            {template.description}
          </Alert>
        )}

        <Textarea
          label="配置（JSON）"
          value={configText}
          onChange={(e: any) => setConfigText(e.target.value)}
          placeholder='{"model":"gpt-4","temperature":0.7}'
          rows={10}
        />
        <div className="text-xs text-gray-500">{configHint}</div>
      </div>
    </Modal>
  );
};

export default AddAgentModal;
