import React, { useMemo, useState } from 'react';
import { workspaceSkillApi } from '../../services/coreApi';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';

interface AddSkillModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const SKILL_CATEGORIES = [
  { value: 'general', label: '通用' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
  { value: 'transformation', label: '转换' },
];

const AddSkillModal: React.FC<AddSkillModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [configText, setConfigText] = useState('');
  const [inputSchemaText, setInputSchemaText] = useState('{}');
  const [outputSchemaText, setOutputSchemaText] = useState('{}');

  const categoryOptions = useMemo(() => SKILL_CATEGORIES, []);

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('请输入 Skill 名称');
      return;
    }
    setLoading(true);
    try {
      let config: Record<string, unknown> = {};
      let input_schema: Record<string, unknown> = {};
      let output_schema: Record<string, unknown> = {};

      if (configText.trim()) {
        try {
          config = JSON.parse(configText);
        } catch {
          toast.error('config JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      if (inputSchemaText.trim()) {
        try {
          input_schema = JSON.parse(inputSchemaText);
        } catch {
          toast.error('input_schema JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      if (outputSchemaText.trim()) {
        try {
          output_schema = JSON.parse(outputSchemaText);
        } catch {
          toast.error('output_schema JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      await workspaceSkillApi.create({
        name: name.trim(),
        category,
        description: description || '',
        config,
        input_schema,
        output_schema,
      } as any);

      toast.success('已创建');
      onSuccess();
      onClose();
      setName('');
      setCategory('general');
      setDescription('');
      setConfigText('');
      setInputSchemaText('{}');
      setOutputSchemaText('{}');
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="创建应用库 Skill"
      width={820}
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
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：我的客服助手" />
        <Select label="分类" value={category} onChange={(v) => setCategory(v)} options={categoryOptions} />
        <Input label="描述" value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="描述用途" />

        <Textarea label="config（JSON，可选）" rows={6} value={configText} onChange={(e: any) => setConfigText(e.target.value)} placeholder='{"timeout_seconds": 60}' />
        <Textarea label="input_schema（JSON）" rows={6} value={inputSchemaText} onChange={(e: any) => setInputSchemaText(e.target.value)} />
        <Textarea label="output_schema（JSON）" rows={6} value={outputSchemaText} onChange={(e: any) => setOutputSchemaText(e.target.value)} />
      </div>
    </Modal>
  );
};

export default AddSkillModal;

