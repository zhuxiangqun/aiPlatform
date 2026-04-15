import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, message, Divider, Typography, Alert } from 'antd';
import { agentApi, skillApi, toolApi } from '../../services';

const { Text } = Typography;

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
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('base');
  const [skillOptions, setSkillOptions] = useState<{ value: string; label: string }[]>([]);
  const [toolOptions, setToolOptions] = useState<{ value: string; label: string }[]>([]);

  useEffect(() => {
    if (open) {
      form.resetFields();
      setSelectedType('base');
      fetchOptions();
    }
  }, [open, form]);

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
      form.setFieldsValue({ config: JSON.stringify(template.config, null, 2) });
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      let config: Record<string, unknown> = {};
      if (values.config?.trim()) {
        try {
          config = JSON.parse(values.config);
        } catch {
          message.error('配置JSON格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      await agentApi.create({
        name: values.name,
        agent_type: values.agent_type || 'base',
        config,
        skills: values.skills || [],
        tools: values.tools || [],
      });
      message.success(`Agent "${values.name}" 创建成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.message) {
        message.error('创建失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const template = AGENT_TYPE_TEMPLATES[selectedType];

  return (
    <Modal
      title="创建Agent"
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="创建"
      cancelText="取消"
      confirmLoading={loading}
      destroyOnHidden
      width={640}
    >
      <Form form={form} layout="vertical" initialValues={{ agent_type: 'base' }}>
        <Form.Item
          name="name"
          label="名称"
          rules={[{ required: true, message: '请输入Agent名称' }]}
        >
          <Input placeholder="例如：数据分析助手" />
        </Form.Item>
        <Form.Item name="agent_type" label="类型">
          <Select onChange={handleTypeChange}
            options={[
              { value: 'base', label: '基础 - 简单对话' },
              { value: 'react', label: 'ReAct - 推理+行动' },
              { value: 'plan', label: '规划型 - 任务分解' },
              { value: 'tool', label: '工具型 - 工具调用' },
            ]}
          />
        </Form.Item>
        <Form.Item name="skills" label="绑定技能">
          <Select
            mode="multiple"
            placeholder="选择要绑定的技能"
            options={skillOptions}
            allowClear
          />
        </Form.Item>
        <Form.Item name="tools" label="绑定工具">
          <Select
            mode="multiple"
            placeholder="选择要绑定的工具"
            options={toolOptions}
            allowClear
          />
        </Form.Item>
      </Form>

      {template && (
        <>
          <Divider orientation="left" plain style={{ margin: '12px 0 8px' }}>
            {template.name} 配置示例
          </Divider>
          <Alert
            message={template.description}
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            以下是 {template.name} 的配置示例，可直接复制修改：
          </Text>
          <pre style={{
            background: '#1C2128',
            border: '1px solid #30363D',
            borderRadius: 6,
            padding: 12,
            fontSize: 12,
            color: '#E6EDF3',
            maxHeight: 200,
            overflow: 'auto',
            marginTop: 8,
          }}>
            {JSON.stringify(template.config, null, 2)}
          </pre>
        </>
      )}

      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        <Form.Item name="config" label="配置 (JSON)" extra="上方展示所选类型的配置示例，请根据需求修改后填入">
          <Input.TextArea rows={6} placeholder='{"model": "gpt-4", "temperature": 0.7}' />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default AddAgentModal;