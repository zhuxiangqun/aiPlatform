import React, { useEffect, useMemo, useState } from 'react';
import { workspaceSkillApi } from '../../services/coreApi';
import type { Skill } from '../../services';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';

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
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [configText, setConfigText] = useState('');

  useEffect(() => {
    if (open && skill) {
      setFetching(true);
      workspaceSkillApi.get(skill.id).then((detail) => {
        const data = detail as any;
        const cat = data.category || data.type || skill.category || 'general';
        const config = data.config || skill.config;
        setName(data.name || skill.name || '');
        setCategory(cat);
        setDescription(data.description || skill.description || '');
        setConfigText(config && Object.keys(config).length > 0 ? JSON.stringify(config, null, 2) : '');
      }).catch(() => {
        const config = skill.config;
        setName(skill.name || '');
        setCategory(skill.category || 'general');
        setDescription(skill.description || '');
        setConfigText(config && Object.keys(config).length > 0 ? JSON.stringify(config, null, 2) : '');
      }).finally(() => {
        setFetching(false);
      });
    }
  }, [open, skill]);

  const handleSubmit = async () => {
    if (!skill) return;
    try {
      if (!name.trim()) {
        toast.error('请输入 Skill 名称');
        return;
      }
      if (!category) {
        toast.error('请选择分类');
        return;
      }
      setLoading(true);

      let config: Record<string, unknown> | undefined;
      if (configText?.trim()) {
        try {
          config = JSON.parse(configText);
        } catch {
          toast.error('配置 JSON 格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      await workspaceSkillApi.update(skill.id, {
        name: name.trim(),
        category,
        description: description || '',
        ...(config ? { config } : {}),
      });
      toast.success(`Skill "${name.trim()}" 更新成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.message) {
        toast.error('更新失败', String(error.message || ''));
      }
    } finally {
      setLoading(false);
    }
  };

  const categoryOptions = useMemo(() => SKILL_CATEGORIES, []);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="编辑应用库 Skill"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={fetching}>
            保存
          </Button>
        </>
      }
    >
      {fetching ? (
        <div className="text-sm text-gray-500">加载中...</div>
      ) : (
        <div className="space-y-4">
          <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} />
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">分类</div>
            <Select value={category} onChange={(v: string) => setCategory(v)} options={categoryOptions} />
          </div>
          <Input label="描述" value={description} onChange={(e: any) => setDescription(e.target.value)} />
          <Textarea label="配置（JSON，可选）" rows={10} value={configText} onChange={(e: any) => setConfigText(e.target.value)} />
        </div>
      )}
    </Modal>
  );
};

export default EditSkillModal;

