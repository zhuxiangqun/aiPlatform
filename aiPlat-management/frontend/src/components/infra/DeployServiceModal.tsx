import React from 'react';
import { Modal, Form, Input, Select, InputNumber, Steps, Button, Space, Alert, Switch } from 'antd';
import { Plus } from 'lucide-react';

const { Option } = Select;

interface DeployServiceModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: ServiceFormValues) => void;
}

interface ServiceFormValues {
  name: string;
  namespace: string;
  type: string;
  image: string;
  imageTag: string;
  replicas: number;
  gpuCount: number;
  gpuType: string;
  model: string;
  maxTokens: number;
  temperature: number;
  enableIngress: boolean;
  ingressHost: string;
}

const DeployServiceModal: React.FC<DeployServiceModalProps> = ({ open, onCancel, onOk }) => {
  const [form] = Form.useForm();
  const [currentStep, setCurrentStep] = React.useState(0);

  const steps = [
    { title: '选择镜像', description: '镜像和版本' },
    { title: '配置资源', description: 'CPU、内存、GPU' },
    { title: '模型参数', description: '推理参数配置' },
    { title: '网络配置', description: '服务暴露方式' },
    { title: '确认', description: '确认部署配置' },
  ];

  const handleNext = async () => {
    try {
      await form.validateFields();
      setCurrentStep(currentStep + 1);
    } catch {
      // validation failed
    }
  };

  const handlePrev = () => {
    setCurrentStep(currentStep - 1);
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onOk(values);
      form.resetFields();
      setCurrentStep(0);
    } catch {
      // validation failed
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setCurrentStep(0);
    onCancel();
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <>
            <Form.Item
              name="name"
              label="服务名称"
              rules={[{ required: true, message: '请输入服务名称' }]}
            >
              <Input placeholder="例如: gpt4-api" />
            </Form.Item>
            <Form.Item
              name="namespace"
              label="命名空间"
              initialValue="ai-prod"
              rules={[{ required: true, message: '请选择命名空间' }]}
            >
              <Select>
                <Option value="ai-prod">ai-prod</Option>
                <Option value="ai-dev">ai-dev</Option>
                <Option value="default">default</Option>
              </Select>
            </Form.Item>
            <Form.Item
              name="type"
              label="服务类型"
              rules={[{ required: true, message: '请选择服务类型' }]}
            >
              <Select placeholder="选择服务类型">
                <Option value="LLM">LLM 推理服务</Option>
                <Option value="Embed">Embedding 服务</Option>
                <Option value="Vector">向量数据库</Option>
                <Option value="Cache">缓存服务</Option>
                <Option value="DB">数据库</Option>
              </Select>
            </Form.Item>
            <Form.Item
              name="image"
              label="镜像名称"
              rules={[{ required: true, message: '请输入镜像名称' }]}
            >
              <Input placeholder="例如: vllm/vllm-openai" />
            </Form.Item>
            <Form.Item
              name="imageTag"
              label="镜像标签"
              initialValue="latest"
              rules={[{ required: true, message: '请输入镜像标签' }]}
            >
              <Input placeholder="例如: latest" />
            </Form.Item>
          </>
        );
      case 1:
        return (
          <>
            <Form.Item
              name="replicas"
              label="副本数"
              rules={[{ required: true, message: '请输入副本数' }]}
              initialValue={2}
            >
              <InputNumber min={1} max={20} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="gpuCount"
              label="GPU 数量"
              rules={[{ required: true, message: '请输入 GPU 数量' }]}
              initialValue={1}
            >
              <InputNumber min={1} max={8} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="gpuType"
              label="GPU 类型"
              rules={[{ required: true, message: '请选择 GPU 类型' }]}
            >
              <Select placeholder="选择 GPU 类型">
                <Option value="A100">NVIDIA A100</Option>
                <Option value="H100">NVIDIA H100</Option>
                <Option value="V100">NVIDIA V100</Option>
                <Option value="A10">NVIDIA A10</Option>
                <Option value="T4">NVIDIA T4</Option>
              </Select>
            </Form.Item>
            <Alert
              message="资源预估"
              description={`预估成本: 2副本 × 1卡A100 = 约 ¥XX/小时`}
              type="info"
              showIcon
              style={{ marginTop: 16 }}
            />
          </>
        );
      case 2:
        return (
          <>
            <Form.Item name="model" label="模型名称">
              <Input placeholder="例如: meta-llama/Llama-3-70b" />
            </Form.Item>
            <Form.Item
              name="maxTokens"
              label="最大Token数"
              initialValue={4096}
            >
              <InputNumber min={256} max={32000} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="temperature"
              label="温度参数"
              initialValue={0.7}
            >
              <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
          </>
        );
      case 3:
        return (
          <>
            <Form.Item
              name="enableIngress"
              label="创建 Ingress"
              valuePropName="checked"
              initialValue={true}
            >
              <Switch />
            </Form.Item>
            <Form.Item
              name="ingressHost"
              label="域名"
              rules={[{ required: form.getFieldValue('enableIngress'), message: '请输入域名' }]}
            >
              <Input placeholder="例如: api.example.com/gpt4" />
            </Form.Item>
          </>
        );
      case 4:
        const values = form.getFieldsValue();
        return (
          <>
            <Alert
              message="确认部署"
              description="请确认以上配置信息无误后点击确定开始部署。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Form.Item label="服务名称">
              <span>{values.name}</span>
            </Form.Item>
            <Form.Item label="镜像">
              <span>{values.image}:{values.imageTag}</span>
            </Form.Item>
            <Form.Item label="资源配置">
              <span>{values.replicas} 副本 × {values.gpuCount} 卡 {values.gpuType}</span>
            </Form.Item>
            <Form.Item label="模型参数">
              <span>max_tokens: {values.maxTokens || 4096}, temperature: {values.temperature || 0.7}</span>
            </Form.Item>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <Modal
      title="部署新服务"
      open={open}
      onCancel={handleCancel}
      width={700}
      footer={null}
    >
      <Steps current={currentStep} items={steps} style={{ marginBottom: 24 }} size="small" />

      <Form form={form} layout="vertical">
        {renderStepContent()}
      </Form>

      <div style={{ marginTop: 24, textAlign: 'right' }}>
        <Space>
          {currentStep > 0 && <Button onClick={handlePrev}>上一步</Button>}
          {currentStep < 4 && <Button type="primary" onClick={handleNext}>下一步</Button>}
          {currentStep === 4 && (
            <Button type="primary" icon={<Plus size={16} />} onClick={handleOk}>
              开始部署
            </Button>
          )}
          <Button onClick={handleCancel}>取消</Button>
        </Space>
      </div>
    </Modal>
  );
};

export default DeployServiceModal;