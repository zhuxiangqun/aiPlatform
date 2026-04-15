import React, { useState } from 'react';
import { Modal, Form, Input, message } from 'antd';

interface ExecuteSkillModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

const ExecuteSkillModal: React.FC<ExecuteSkillModalProps> = ({ open, skill, onClose }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: string; output?: unknown; error?: string; duration_ms?: number } | null>(null);

  const handleExecute = async () => {
    if (!skill) return;
    try {
      const values = await form.validateFields();
      setLoading(true);
      setResult(null);

      let input: Record<string, unknown> = {};
      if (values.input?.trim()) {
        try {
          input = JSON.parse(values.input);
        } catch {
          input = { message: values.input };
        }
      }

      const { skillApi } = await import('../../services');
      const res = await skillApi.execute(skill.id, { input });
      setResult(res as any);
      message.success(res.status === 'completed' || res.status === 'success' ? '执行成功' : `状态: ${res.status}`);
    } catch (error: any) {
      message.error('执行失败');
      setResult({ status: 'error', error: error.message || 'Unknown error' });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title={`执行Skill: ${skill?.name || ''}`}
      open={open}
      onOk={handleExecute}
      onCancel={handleClose}
      okText="执行"
      cancelText="关闭"
      confirmLoading={loading}
      destroyOnHidden
      width={640}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="input" label="输入参数" extra="支持 JSON 格式或纯文本">
          <Input.TextArea rows={4} placeholder='{"query": "搜索关键词"} 或直接输入文本' />
        </Form.Item>
      </Form>

      {result && (
        <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-100">执行结果</span>
            <span className={`text-xs px-2 py-0.5 rounded ${result.status === 'completed' || result.status === 'success' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
              {result.status}
            </span>
          </div>
          {result.duration_ms != null && (
            <div className="text-xs text-gray-400 mb-2">耗时: {result.duration_ms}ms</div>
          )}
          {result.output !== undefined && result.output !== null && (
            <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
              {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
            </pre>
          )}
          {result.error && !result.output && (
            <div className="text-xs text-red-300 mt-2">{result.error}</div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteSkillModal;