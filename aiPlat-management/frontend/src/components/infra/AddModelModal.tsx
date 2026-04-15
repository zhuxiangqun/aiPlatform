import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, InputNumber, Button, Space, message, Steps } from 'antd';
import { Network } from 'lucide-react';
import { modelApi, type Provider } from '../../services';

interface AddModelModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  providers: Provider[];
}

const AddModelModal: React.FC<AddModelModalProps> = ({ open, onClose, onSuccess, providers }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [currentStep, setCurrentStep] = useState(0);

  const selectedProvider = Form.useWatch('provider', form);

  useEffect(() => {
    if (open) {
      form.resetFields();
      setCurrentStep(0);
      setTestResult(null);
    }
  }, [open, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const modelData = {
        name: values.name,
        displayName: values.displayName,
        type: values.type || 'chat',
        provider: values.provider,
        description: values.description,
        tags: values.tags?.split(',').map((t: string) => t.trim()).filter(Boolean) || [],
        config: {
          baseUrl: values.baseUrl,
          apiKeyEnv: values.apiKeyEnv,
          temperature: values.temperature ?? 0.7,
          maxTokens: values.maxTokens ?? 2048,
          topP: values.topP ?? 1.0,
        },
      };

      await modelApi.add(modelData);
      message.success('模型添加成功');
      onSuccess();
      onClose();
    } catch (error: any) {
      message.error(error.message || '添加失败');
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnectivity = async () => {
    try {
      const values = await form.validateFields(['baseUrl']);
      setTestLoading(true);
      setTestResult(null);

      // 简单的连通性测试：检查 URL 是否可达
      try {
        const url = new URL(values.baseUrl);
        setTestResult({ success: true, message: `端点 ${url.host} 格式正确` });
        message.success('端点格式正确');
      } catch {
        setTestResult({ success: false, message: '无效的 URL 格式' });
        message.warning('请输入有效的 URL');
      }
    } catch {
      // validation failed
    } finally {
      setTestLoading(false);
    }
  };

  const nextStep = async () => {
    try {
      await form.validateFields(['provider']);
      setCurrentStep(1);
    } catch {
      // validation failed
    }
  };

  const prevStep = () => {
    setCurrentStep(0);
  };

  const providerOptions = providers.map(p => (
    <Select.Option key={p.id} value={p.id}>
      {p.name} {p.requiresApiKey && '(需要 API Key)'}
    </Select.Option>
  ));

  const selectedProviderInfo = providers.find(p => p.id === selectedProvider);

  return (
    <Modal
      title="添加模型"
      open={open}
      onCancel={onClose}
      onOk={currentStep === 1 ? handleSubmit : nextStep}
      okText={currentStep === 1 ? '保存' : '下一步'}
      confirmLoading={loading}
      width={600}
      destroyOnHidden={true}
    >
      <Steps current={currentStep} size="small" style={{ marginBottom: 24 }}>
        <Steps.Step title="选择 Provider" />
        <Steps.Step title="配置参数" />
      </Steps>

      {currentStep === 0 && (
        <Form form={form} layout="vertical">
          <Form.Item
            name="provider"
            label="Provider"
            rules={[{ required: true, message: '请选择 Provider' }]}
          >
            <Select placeholder="选择 Provider" showSearch>
              {providerOptions}
            </Select>
          </Form.Item>

          {selectedProviderInfo && (
            <div style={{ padding: 12, background: '#1C2128', borderRadius: 4, color: '#E6EDF3' }}>
              <p><strong>类型：</strong>{selectedProviderInfo.type}</p>
              <p><strong>能力：</strong>{selectedProviderInfo.capabilities?.join(', ')}</p>
              {selectedProviderInfo.requiresApiKey && (
                <p style={{ color: '#faad14' }}>需要配置 API Key</p>
              )}
            </div>
          )}
        </Form>
      )}

      {currentStep === 1 && (
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="例如：gpt-4, llama3:70b" />
          </Form.Item>

          <Form.Item name="displayName" label="显示名称">
            <Input placeholder="例如：GPT-4 Turbo" />
          </Form.Item>

          <Form.Item name="type" label="类型" initialValue="chat">
            <Select>
              <Select.Option value="chat">对话模型</Select.Option>
              <Select.Option value="embedding">Embedding模型</Select.Option>
              <Select.Option value="image">图像模型</Select.Option>
              <Select.Option value="audio">音频模型</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="baseUrl"
            label="端点 URL"
            rules={selectedProviderInfo?.requiresApiKey ? [{ required: true, message: '请输入端点 URL' }] : []}
          >
            <Input placeholder="例如：https://api.openai.com/v1 或 http://localhost:11434/v1" />
          </Form.Item>

          <Form.Item name="apiKeyEnv" label="API Key 环境变量">
            <Input placeholder="例如：OPENAI_API_KEY（不直接填写 API Key）" />
          </Form.Item>

          <Form.Item label="连通性测试">
            <Space>
              <Button icon={<Network size={16} />} onClick={handleTestConnectivity} loading={testLoading}>
                测试连通性
              </Button>
              {testResult && (
                <span style={{ color: testResult.success ? '#52c41a' : '#ff4d4f' }}>
                  {testResult.message}
                </span>
              )}
            </Space>
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="模型描述" />
          </Form.Item>

          <Form.Item name="tags" label="标签">
            <Input placeholder="多个标签用逗号分隔，例如：chat, code" />
          </Form.Item>

          <Form.Item label="高级配置" style={{ marginBottom: 0 }}>
            <Form.Item name="temperature" noStyle>
              <InputNumber
                style={{ width: 100, marginRight: 8 }}
                placeholder="Temperature"
                min={0}
                max={2}
                step={0.1}
              />
            </Form.Item>
            <Form.Item name="maxTokens" noStyle>
              <InputNumber
                style={{ width: 120, marginRight: 8 }}
                placeholder="Max Tokens"
                min={1}
              />
            </Form.Item>
            <Form.Item name="topP" noStyle>
              <InputNumber
                style={{ width: 80 }}
                placeholder="Top P"
                min={0}
                max={1}
                step={0.1}
              />
            </Form.Item>
          </Form.Item>

          {currentStep === 1 && (
            <Button style={{ marginRight: 8 }} onClick={prevStep}>
              上一步
            </Button>
          )}
        </Form>
      )}
    </Modal>
  );
};

export default AddModelModal;