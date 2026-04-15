import React, { useState } from 'react';
import { Modal, Button, Input, Select } from '../ui';
import { useSkillStore } from '../../stores';

interface AddSkillModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const SKILL_CATEGORIES = [
  { value: 'general', label: '通用' },
  { value: 'reasoning', label: '推理' },
  { value: 'coding', label: '编程' },
  { value: 'search', label: '搜索' },
  { value: 'tool', label: '工具' },
  { value: 'communication', label: '通信' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
  { value: 'transformation', label: '转换' },
];

const AddSkillModal: React.FC<AddSkillModalProps> = ({ open, onClose, onSuccess }) => {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const { createSkill } = useSkillStore.getState();

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setLoading(true);
    try {
      await createSkill({ name: name.trim(), description, category });
      onSuccess();
      onClose();
      setName('');
      setCategory('general');
      setDescription('');
    } catch (error) {
      console.error('Failed to create skill:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="创建 Skill">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">名称</label>
          <Input
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
            placeholder="例如：Python代码审查助手"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">分类</label>
          <Select
            value={category}
            onChange={(val: string) => setCategory(val)}
            options={SKILL_CATEGORIES}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">描述</label>
          <Input
            value={description}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDescription(e.target.value)}
            placeholder="描述此技能的用途和使用场景"
          />
        </div>
        <div className="flex justify-end gap-2 pt-4">
          <Button onClick={onClose} variant="secondary">取消</Button>
          <Button onClick={handleSubmit} loading={loading}>创建</Button>
        </div>
      </div>
    </Modal>
  );
};

export default AddSkillModal;