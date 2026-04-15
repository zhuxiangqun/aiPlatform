import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, message, Divider, Typography, Alert } from 'antd';
import { agentApi } from '../../services';
import type { Agent } from '../../services';

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

interface EditAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditAgentModal: React.FC<EditAgentModalProps> = ({ open, agent, onClose, onSuccess }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && agent) {
      form.resetFields();
      form.setFieldsValue({
        name: agent.name,
        agent_type: agent.agent_type,
        config: agent.metadata?.config ? JSON.stringify(agent.metadata.config, null, 2) : '',
      });
    }
  }, [open, agent, form]);

  const handleSubmit = async () => {
    if (!agent) return;
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

      await agentApi.update(agent.id, { config });
      message.success(`Agent "${agent.name}" 更新成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.message) {
        message.error('更新失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const currentTemplate = agent ? AGENT_TYPE_TEMPLATES[agent.agent_type] : null;

  return (
    <Modal
      title="编辑Agent"
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      confirmLoading={loading}
      destroyOnHidden
      width={640}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="名称"
          rules={[{ required: true, message: '请输入Agent名称' }]}
        >
          <Input placeholder="例如：数据分析助手" />
        </Form.Item>
        <Form.Item name="agent_type" label="类型">
          <Select
            disabled
            options={[
              { value: 'base', label: '基础 - 简单对话' },
              { value: 'react', label: 'ReAct - 推理+行动' },
              { value: 'plan', label: '规划型 - 任务分解' },
              { value: 'tool', label: '工具型 - 工具调用' },
            ]}
          />
        </Form.Item>
      </Form>

      {currentTemplate && (
        <>
          <Divider orientation="left" plain style={{ margin: '12px 0 8px' }}>
            {currentTemplate.name} 配置示例
          </Divider>
          <Alert
            message={currentTemplate.description}
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            以下是 {currentTemplate.name} 的配置示例，可直接复制修改：
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
            {JSON.stringify(currentTemplate.config, null, 2)}
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

export default EditAgentModal;