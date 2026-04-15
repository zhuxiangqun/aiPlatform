import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, Spin, message } from 'antd';
import { skillApi } from '../../services';
import type { Skill } from '../../services';

const SKILL_CATEGORIES = [
  { value: 'general', label: '通用技能' },
  { value: 'reasoning', label: '推理技能' },
  { value: 'coding', label: '编程技能' },
  { value: 'search', label: '搜索技能' },
  { value: 'tool', label: '工具技能' },
  { value: 'communication', label: '通信技能' },
  { value: 'execution', label: '执行技能' },
  { value: 'retrieval', label: '检索技能' },
  { value: 'analysis', label: '分析技能' },
  { value: 'generation', label: '生成技能' },
  { value: 'transformation', label: '转换技能' },
];

interface EditSkillModalProps {
  open: boolean;
  skill: Skill | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditSkillModal: React.FC<EditSkillModalProps> = ({ open, skill, onClose, onSuccess }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    if (open && skill) {
      form.resetFields();
      setFetching(true);
      skillApi.get(skill.id).then((detail) => {
        const data = detail as any;
        const category = data.category || data.type || skill.category || 'general';
        const config = data.config || skill.config;
        form.setFieldsValue({
          name: data.name || skill.name,
          category,
          description: data.description || skill.description || '',
          config: config && Object.keys(config).length > 0 ? JSON.stringify(config, null, 2) : '',
        });
      }).catch(() => {
        const config = skill.config;
        form.setFieldsValue({
          name: skill.name,
          category: skill.category || 'general',
          description: skill.description || '',
          config: config && Object.keys(config).length > 0 ? JSON.stringify(config, null, 2) : '',
        });
      }).finally(() => {
        setFetching(false);
      });
    }
  }, [open, skill, form]);

  const handleSubmit = async () => {
    if (!skill) return;
    try {
      const values = await form.validateFields();
      setLoading(true);

      let config: Record<string, unknown> | undefined;
      if (values.config?.trim()) {
        try {
          config = JSON.parse(values.config);
        } catch {
          message.error('配置JSON格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      await skillApi.update(skill.id, {
        name: values.name,
        category: values.category,
        description: values.description || '',
        ...(config ? { config } : {}),
      });
      message.success(`Skill "${values.name}" 更新成功`);
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
      title="编辑 Skill"
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      confirmLoading={loading}
      destroyOnHidden
      width={640}
    >
      <Spin spinning={fetching} tip="加载中...">
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入Skill名称' }]}
          >
            <Input placeholder="例如：Python代码审查助手" />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: '请选择分类' }]}>
            <Select options={SKILL_CATEGORIES} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="描述此技能的用途和使用场景" />
          </Form.Item>
          <Form.Item name="config" label="配置 (JSON)" extra="可选，配置超时时间、并发数、重试次数等参数">
            <Input.TextArea rows={6} placeholder='{"timeout_seconds": 60, "max_concurrent": 10, "retry_count": 3}' />
          </Form.Item>
        </Form>
      </Spin>
    </Modal>
  );
};

export default EditSkillModal;