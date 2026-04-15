import React from 'react';
import { Modal, Form, Input, Select, InputNumber, Steps, Button, Space, Alert } from 'antd';

const { Option } = Select;

interface AddNodeModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: NodeFormValues) => void;
}

interface NodeFormValues {
  name: string;
  ip: string;
  provider: string;
  instanceType: string;
  gpuModel: string;
  gpuCount: number;
  driverVersion: string;
  labels: Record<string, string>;
}

const AddNodeModal: React.FC<AddNodeModalProps> = ({ open, onCancel, onOk }) => {
  const [form] = Form.useForm();
  const [currentStep, setCurrentStep] = React.useState(0);

  const steps = [
    { title: '基本信息', description: '节点名称和IP' },
    { title: 'GPU配置', description: 'GPU型号和数量' },
    { title: '驱动配置', description: 'NVIDIA驱动版本' },
    { title: '确认', description: '确认节点配置' },
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
              label="节点名称"
              rules={[{ required: true, message: '请输入节点名称' }]}
            >
              <Input placeholder="例如: node-01" />
            </Form.Item>
            <Form.Item
              name="ip"
              label="IP 地址"
              rules={[
                { required: true, message: '请输入 IP 地址' },
                { pattern: /^(\d{1,3}\.){3}\d{1,3}$/, message: '请输入有效的 IP 地址' },
              ]}
            >
              <Input placeholder="例如: 10.0.0.101" />
            </Form.Item>
            <Form.Item name="provider" label="云厂商">
              <Select placeholder="选择云厂商（可选）">
                <Option value="aws">AWS</Option>
                <Option value="azure">Azure</Option>
                <Option value="gcp">Google Cloud</Option>
                <Option value="aliyun">阿里云</Option>
                <Option value="huawei">华为云</Option>
                <Option value="self-hosted">自建机房</Option>
              </Select>
            </Form.Item>
          </>
        );
      case 1:
        return (
          <>
            <Form.Item
              name="gpuModel"
              label="GPU 型号"
              rules={[{ required: true, message: '请选择 GPU 型号' }]}
            >
              <Select placeholder="选择 GPU 型号">
                <Option value="A100">NVIDIA A100</Option>
                <Option value="H100">NVIDIA H100</Option>
                <Option value="V100">NVIDIA V100</Option>
                <Option value="A10">NVIDIA A10</Option>
                <Option value="T4">NVIDIA T4</Option>
              </Select>
            </Form.Item>
            <Form.Item
              name="gpuCount"
              label="GPU 数量"
              rules={[{ required: true, message: '请输入 GPU 数量' }]}
              initialValue={4}
            >
              <InputNumber min={1} max={8} style={{ width: '100%' }} />
            </Form.Item>
          </>
        );
      case 2:
        return (
          <>
            <Form.Item
              name="driverVersion"
              label="NVIDIA 驱动版本"
              rules={[{ required: true, message: '请选择驱动版本' }]}
            >
              <Select placeholder="选择驱动版本">
                <Option value="535.54.03">535.54.03 (CUDA 12.2)</Option>
                <Option value="535.104.05">535.104.05 (CUDA 12.2)</Option>
                <Option value="545.23.06">545.23.06 (CUDA 12.3)</Option>
                <Option value="550.40.07">550.40.07 (CUDA 12.4)</Option>
              </Select>
            </Form.Item>
            <Alert
              message="注意"
              description="安装/升级 NVIDIA 驱动需要重启节点，请确保节点上的服务已安全迁移。"
              type="warning"
              showIcon
              style={{ marginTop: 16 }}
            />
          </>
        );
      case 3:
        return (
          <>
            <Alert
              message="确认添加节点"
              description="请确认以上配置信息无误后点击确定添加节点。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Form.Item label="节点名称">
              <span>{form.getFieldValue('name')}</span>
            </Form.Item>
            <Form.Item label="IP 地址">
              <span>{form.getFieldValue('ip')}</span>
            </Form.Item>
            <Form.Item label="GPU 配置">
              <span>{form.getFieldValue('gpuCount')} × {form.getFieldValue('gpuModel')}</span>
            </Form.Item>
            <Form.Item label="驱动版本">
              <span>{form.getFieldValue('driverVersion')}</span>
            </Form.Item>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <Modal
      title="添加节点向导"
      open={open}
      onCancel={handleCancel}
      width={600}
      footer={null}
    >
      <Steps current={currentStep} items={steps} style={{ marginBottom: 24 }} />

      <Form form={form} layout="vertical">
        {renderStepContent()}
      </Form>

      <div style={{ marginTop: 24, textAlign: 'right' }}>
        <Space>
          {currentStep > 0 && <Button onClick={handlePrev}>上一步</Button>}
          {currentStep < 3 && <Button type="primary" onClick={handleNext}>下一步</Button>}
          {currentStep === 3 && (
            <Button type="primary" onClick={handleOk}>
              确定
            </Button>
          )}
          <Button onClick={handleCancel}>取消</Button>
        </Space>
      </div>
    </Modal>
  );
};

export default AddNodeModal;