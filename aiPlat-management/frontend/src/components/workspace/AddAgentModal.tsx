import React, { useEffect, useMemo, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi } from '../../services/coreApi';
import { toolApi } from '../../services';
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
    config: { model: 'gpt-4', temperature: 0.7, max_tokens: 2048, system_prompt: '你是一个有帮助的AI助手。' },
  },
  react: {
    name: 'ReAct Agent',
    description: '使用ReAct（Reasoning + Acting）模式，具备推理和工具调用能力',
    config: { model: 'gpt-4', temperature: 0.0, max_tokens: 4096, reasoning_steps: 3, system_prompt: '你是一个使用ReAct模式的推理Agent。' },
  },
  plan: {
    name: '规划型Agent',
    description: '具备任务分解和规划能力，适合复杂多步骤任务',
    config: { model: 'gpt-4', temperature: 0.1, max_tokens: 8192, planning_enabled: true, max_subtasks: 10, system_prompt: '你是一个任务规划Agent。' },
  },
  tool: {
    name: '工具型Agent',
    description: '专注于工具调用和自动化执行的Agent',
    config: { model: 'gpt-4', temperature: 0.0, max_tokens: 2048, system_prompt: '你是一个工具型Agent。' },
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
  const [description, setDescription] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [configText, setConfigText] = useState('');
  const [memoryConfigText, setMemoryConfigText] = useState('{\n  "type": "short_term",\n  "recall_count": 5\n}');
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);

  useEffect(() => {
    if (open) {
      setSelectedType('base');
      setName('');
      setDescription('');
      setSkills([]);
      setTools([]);
      setConfigText(JSON.stringify(AGENT_TYPE_TEMPLATES.base.config, null, 2));
      setMemoryConfigText('{\n  "type": "short_term",\n  "recall_count": 5\n}');
      fetchOptions();
    }
  }, [open]);

  const fetchOptions = async () => {
    try {
      const [skillRes, toolRes] = await Promise.all([
        workspaceSkillApi.list({ limit: 200 }),
        toolApi.list({ limit: 200 } as any),
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
    if (template) setConfigText(JSON.stringify(template.config, null, 2));
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

      let memory_config: Record<string, unknown> | undefined;
      if (memoryConfigText?.trim()) {
        try {
          memory_config = JSON.parse(memoryConfigText);
        } catch {
          toast.error('memory_config JSON 格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      const metadata: Record<string, unknown> = {};
      if (description.trim()) metadata.description = description.trim();

      await workspaceAgentApi.create({ name: name.trim(), agent_type: selectedType, config, skills, tools, memory_config, metadata });
      toast.success('创建成功');
      onSuccess();
      onClose();
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
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
      title="创建应用库 Agent"
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
        <Input label="描述（可选）" value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="这个 Agent 的职责边界与适用场景" />

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
              onChange={(e) => setSkills(Array.from(e.target.selectedOptions).map((o) => (o as any).value))}
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
            onChange={(e) => setTools(Array.from(e.target.selectedOptions).map((o) => (o as any).value))}
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

        <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => setConfigText(e.target.value)} rows={10} />
        <Textarea label="memory_config（JSON，可选）" value={memoryConfigText} onChange={(e: any) => setMemoryConfigText(e.target.value)} rows={6} />
        <div className="text-xs text-gray-500">{configHint}</div>
      </div>
    </Modal>
  );
};

export default AddAgentModal;
