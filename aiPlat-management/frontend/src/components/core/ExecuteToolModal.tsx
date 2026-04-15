import React, { useState, useMemo } from 'react';
import { Modal, Form, Input, InputNumber, Select, message } from 'antd';

interface ParameterProperty {
  type?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
}

interface ExecuteToolModalProps {
  open: boolean;
  tool: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
  } | null;
  onClose: () => void;
}

const ExecuteToolModal: React.FC<ExecuteToolModalProps> = ({ open, tool, onClose }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ output?: unknown; error?: string; success?: boolean; latency?: number } | null>(null);

  const paramSchema = tool?.parameters as any;
  const requiredFields: string[] = paramSchema?.required || [];
  const properties = paramSchema?.properties || {};

  const sortedFields = useMemo(() => {
    return Object.entries(properties).sort(([a], [b]) => {
      const aReq = requiredFields.includes(a) ? 0 : 1;
      const bReq = requiredFields.includes(b) ? 0 : 1;
      return aReq - bReq;
    });
  }, [properties, requiredFields]);

  const handleExecute = async () => {
    if (!tool) return;
    try {
      const values = await form.validateFields();
      setLoading(true);
      setResult(null);

      const { toolApi } = await import('../../services');
      const res = await toolApi.execute(tool.name, values);
      setResult(res as any);
      message.success(res.success !== false ? '执行成功' : '执行完成');
    } catch (error: any) {
      if (error.errorFields) return;
      message.error('执行失败');
      setResult({ error: error.message || 'Unknown error', success: false });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    form.resetFields();
    onClose();
  };

  const renderField = (name: string, spec: ParameterProperty) => {
    const isRequired = requiredFields.includes(name);
    const fieldType = spec.type || 'string';

    if (fieldType === 'integer' || fieldType === 'number') {
      return (
        <Form.Item
          key={name}
          name={name}
          label={name}
          required={isRequired}
          rules={isRequired ? [{ required: true, message: `请输入${name}` }] : undefined}
          initialValue={spec.default as number | undefined}
        >
          <InputNumber
            className="w-full"
            placeholder={spec.description || `输入${name}`}
          />
        </Form.Item>
      );
    }

    if (spec.enum && spec.enum.length > 0) {
      return (
        <Form.Item
          key={name}
          name={name}
          label={name}
          required={isRequired}
          rules={isRequired ? [{ required: true, message: `请选择${name}` }] : undefined}
          initialValue={spec.default as string | undefined}
        >
          <Select
            placeholder={spec.description || `选择${name}`}
            options={spec.enum.map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
      );
    }

    return (
      <Form.Item
        key={name}
        name={name}
        label={name}
        required={isRequired}
        rules={isRequired ? [{ required: true, message: `请输入${name}` }] : undefined}
        initialValue={spec.default as string | undefined}
      >
        <Input placeholder={spec.description || `输入${name}`} />
      </Form.Item>
    );
  };

  return (
    <Modal
      title={`执行Tool: ${tool?.name || ''}`}
      open={open}
      onOk={handleExecute}
      onCancel={handleClose}
      okText="执行"
      cancelText="关闭"
      confirmLoading={loading}
      destroyOnHidden
      width={640}
    >
      {tool?.description && (
        <div className="mb-4 text-sm text-gray-400">{tool.description}</div>
      )}

      {sortedFields.length > 0 ? (
        <Form form={form} layout="vertical">
          {sortedFields.map(([name, spec]) => renderField(name, spec as ParameterProperty))}
        </Form>
      ) : (
        <div className="py-4 text-center text-gray-400 text-sm">
          此 Tool 无需参数，直接点击"执行"即可
        </div>
      )}

      {result && (
        <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-100">执行结果</span>
            <span className={`text-xs px-2 py-0.5 rounded ${result.success !== false ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
              {result.success !== false ? '成功' : '失败'}
            </span>
          </div>
          {result.latency != null && (
            <div className="text-xs text-gray-400 mb-2">耗时: {result.latency.toFixed(1)}ms</div>
          )}
          {result.output !== undefined && result.output !== null && (
            <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
              {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
            </pre>
          )}
          {result.error && !result.output && (
            <div className="text-xs text-red-300">{result.error}</div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteToolModal;