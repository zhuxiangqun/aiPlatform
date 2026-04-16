import React, { useState, useEffect } from 'react';
import { Plus, RotateCw, Trash2, Pencil, Play } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Switch, Button, Modal, toast } from '../../../components/ui';
import { AddSkillModal, EditSkillModal, ExecuteSkillModal } from '../../../components/core';
import { useSkillStore } from '../../../stores';
import type { Skill } from '../../../services';

const categoryConfig: Record<string, { color: string; text: string }> = {
  general: { color: 'bg-dark-hover text-gray-300 border-gray-200', text: '通用' },
  reasoning: { color: 'bg-blue-50 text-blue-300 border-blue-200', text: '推理' },
  coding: { color: 'bg-green-50 text-green-300 border-green-200', text: '编程' },
  search: { color: 'bg-amber-50 text-amber-300 border-amber-200', text: '搜索' },
  tool: { color: 'bg-purple-50 text-purple-300 border-purple-200', text: '工具' },
  communication: { color: 'bg-cyan-50 text-cyan-300 border-cyan-200', text: '通信' },
  execution: { color: 'bg-orange-50 text-orange-300 border-orange-200', text: '执行' },
  retrieval: { color: 'bg-teal-50 text-teal-300 border-teal-200', text: '检索' },
  analysis: { color: 'bg-indigo-50 text-indigo-300 border-indigo-200', text: '分析' },
  generation: { color: 'bg-pink-50 text-pink-300 border-pink-200', text: '生成' },
  transformation: { color: 'bg-yellow-50 text-yellow-300 border-yellow-200', text: '转换' },
};

const Skills: React.FC = () => {
  const { skills, loading, fetchSkills, toggleSkill, deleteSkill } = useSkillStore();
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; skill: Skill | null }>({ open: false, skill: null });

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleToggle = async (skill: Skill) => {
    try {
      await toggleSkill(skill.id, !skill.enabled);
      toast.success(skill.enabled ? `Skill "${skill.name}" 已禁用` : `Skill "${skill.name}" 已启用`);
    } catch {
      toast.error('操作失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.skill) return;
    try {
      await deleteSkill(deleteConfirm.skill.id);
      toast.success('Skill已删除');
      setDeleteConfirm({ open: false, skill: null });
    } catch {
      toast.error('删除失败');
    }
  };

  const filteredSkills = skills.filter(s => {
    if (categoryFilter && s.category !== categoryFilter) return false;
    if (enabledOnly && !s.enabled) return false;
    return true;
  });

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <span className="font-medium text-gray-100">{name}</span>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (desc: string) => <span className="text-gray-500">{desc || '-'}</span>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (category: string) => {
        const cfg = categoryConfig[category] || { color: 'bg-dark-hover text-gray-300 border-gray-200', text: category };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}`}>
            {cfg.text}
          </span>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      align: 'center' as const,
      render: (enabled: boolean, record: Skill) => (
        <Switch
          checked={enabled}
          onChange={() => handleToggle(record)}
        />
      ),
    },
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{id.slice(0, 8)}</code>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => { setExecuteSkill(record); setExecuteModalOpen(true); }}
            className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors"
            title="执行"
          >
            <Play className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setEditSkill(record); setEditModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="编辑"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={() => setDeleteConfirm({ open: true, skill: record })}
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">Skill管理</h1>
          <p className="text-sm text-gray-500 mt-1">管理技能的注册、启用与版本控制</p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={categoryFilter}
            onChange={(v) => setCategoryFilter(v || undefined)}
            options={Object.entries(categoryConfig).map(([k, v]) => ({ value: k, label: v.text }))}
            placeholder="分类筛选"
          />
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">仅启用</span>
            <Switch checked={enabledOnly} onChange={setEnabledOnly} />
          </div>
          <Button
            icon={<RotateCw className="w-4 h-4" />}
            onClick={fetchSkills}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            variant="primary"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => setAddModalOpen(true)}
          >
            创建Skill
          </Button>
        </div>
      </div>

      {/* Table Card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={filteredSkills}
          rowKey="id"
          loading={loading}
          emptyText="暂无Skill数据"
        />
      </motion.div>

      {/* Delete Confirmation Modal */}
      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, skill: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteConfirm({ open: false, skill: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除Skill "{deleteConfirm.skill?.name}" 吗？此操作不可撤销，请谨慎操作。
        </p>
      </Modal>

      <AddSkillModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={fetchSkills}
      />

      <EditSkillModal
        open={editModalOpen}
        skill={editSkill}
        onClose={() => setEditModalOpen(false)}
        onSuccess={fetchSkills}
      />

      <ExecuteSkillModal
        open={executeModalOpen}
        skill={executeSkill}
        onClose={() => setExecuteModalOpen(false)}
      />
    </div>
  );
};

export default Skills;
