import React, { useState, useEffect } from 'react';
import { Modal, Form, InputNumber, Spin, message } from 'antd';
import { toolApi } from '../../services';

interface EditToolConfigModalProps {
  open: boolean;
  tool: { name: string; config?: Record<string, unknown> } | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditToolConfigModal: React.FC<EditToolConfigModalProps> = ({ open, tool, onClose, onSuccess }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    if (open && tool) {
      form.resetFields();
      setFetching(true);
      toolApi.get(tool.name).then((detail) => {
        const data = detail as any;
        const cfg = data.config || {};
        form.setFieldsValue({
          timeout_seconds: cfg.timeout_seconds ?? null,
          max_concurrent: cfg.max_concurrent ?? null,
        });
      }).catch(() => {
        const cfg = tool.config || {};
        form.setFieldsValue({
          timeout_seconds: cfg.timeout_seconds ?? null,
          max_concurrent: cfg.max_concurrent ?? null,
        });
      }).finally(() => {
        setFetching(false);
      });
    }
  }, [open, tool, form]);

  const handleSubmit = async () => {
    if (!tool) return;
    try {
      const values = await form.validateFields();
      setLoading(true);

      const config: Record<string, unknown> = {};
      if (values.timeout_seconds != null) config.timeout_seconds = values.timeout_seconds;
      if (values.max_concurrent != null) config.max_concurrent = values.max_concurrent;

      await toolApi.updateConfig(tool.name, config);
      message.success(`Tool "${tool.name}" 配置更新成功`);
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

  return (
    <Modal
      title={`编辑配置: ${tool?.name || ''}`}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      confirmLoading={loading}
      destroyOnHidden
      width={480}
    >
      <Spin spinning={fetching} tip="加载中...">
        <Form form={form} layout="vertical">
          <Form.Item name="timeout_seconds" label="超时时间（秒）" extra="Tool 执行的最大等待时间">
            <InputNumber className="w-full" min={1} max={600} placeholder="默认 60" />
          </Form.Item>
          <Form.Item name="max_concurrent" label="最大并发数" extra="同时执行的最大任务数">
            <InputNumber className="w-full" min={1} max={100} placeholder="默认 10" />
          </Form.Item>
        </Form>
      </Spin>
    </Modal>
  );
};

export default EditToolConfigModal;