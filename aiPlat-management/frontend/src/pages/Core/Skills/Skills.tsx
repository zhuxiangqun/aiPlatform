import React, { useState, useEffect } from 'react';
import { Info, RotateCw, RotateCcw, Trash2, Pencil, Play } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Switch, Button, Modal, toast } from '../../../components/ui';
import { EditSkillModal, ExecuteSkillModal, SkillDetailModal } from '../../../components/core';
import { useSkillStore } from '../../../stores';
import type { Skill } from '../../../services';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { SKILL_CATEGORIES } from '../../../utils/categoryConfig';
import { StatusBadge } from '../../../utils/statusLabel';

const Skills: React.FC = () => {
  const { skills, loading, fetchSkills, deleteSkill, restoreSkill } = useSkillStore();
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; skill: Skill | null; hard: boolean }>({ open: false, skill: null, hard: false });
  const [deleting, setDeleting] = useState(false);
  const [detailSkillId, setDetailSkillId] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);


  const handleDelete = async () => {
    if (!deleteConfirm.skill || deleting) return;
    setDeleting(true);
    try {
      await deleteSkill(deleteConfirm.skill.id, { delete_files: deleteConfirm.hard });
      toast.success(deleteConfirm.hard ? 'Skill已彻底删除' : 'Skill已弃用（deprecated）');
      setDeleteConfirm({ open: false, skill: null, hard: false });
    } catch (e: any) {
      toast.error('删除失败', e?.message || '');
    } finally {
      setDeleting(false);
    }
  };

  const handleRestore = async (skill: Skill) => {
    try {
      await restoreSkill(skill.id);
      toast.success(`Skill "${skill.name}" 已恢复`);
    } catch {
      toast.error('恢复失败');
    }
  };

  const filteredSkills = skills.filter(s => {
    if (categoryFilter && s.category !== categoryFilter) return false;
    if (enabledOnly && !s.enabled) return false;
    if (statusFilter) {
      const st = (s.status || (s.enabled ? 'enabled' : 'disabled')).toLowerCase();
      if (st !== statusFilter) return false;
    }
    return true;
  });

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: Skill) => (
        <button
          className="font-medium text-gray-100 text-left hover:underline"
           onClick={() => setDetailSkillId(record.id)}
           title="查看详情"
        >
          {name}
        </button>
      ),
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
        const cfg = SKILL_CATEGORIES[category] || { color: 'bg-dark-hover text-gray-300 border-gray-200', text: category };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}`}>
            {cfg.text}
          </span>
        );
      },
    },
    {
      title: '来源',
      key: 'source',
      width: 80,
      render: (_: unknown, record: Skill) => (
        <span className="text-gray-400 text-xs">{getSourceLabel(extractProvenance(record))}</span>
      ),
    },
    {
      title: '上架状态',
      key: 'status',
      width: 80,
      render: (_: unknown, record: Skill) => <StatusBadge status={record.status} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => {
        const isProtected = Boolean((record as any)?.metadata?.protected === true || (record as any)?.protected === true);
        return (
          <div className="flex items-center justify-center gap-1">
          <button
          onClick={() => setDetailSkillId(record.id)}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="详情"
          >
            <Info className="w-4 h-4" />
          </button>
          <button
            onClick={() => {
              if ((record.status || '').toLowerCase() === 'deprecated') return;
              setExecuteSkill(record);
              setExecuteModalOpen(true);
            }}
            className={`p-1.5 rounded-lg transition-colors ${
              (record.status || '').toLowerCase() === 'deprecated'
                ? 'text-gray-600 cursor-not-allowed'
                : 'text-success hover:bg-success-light'
            }`}
            title="执行"
          >
            <Play className="w-4 h-4" />
          </button>
          {!isProtected && (
            <button
              onClick={() => { setEditSkill(record); setEditModalOpen(true); }}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="编辑"
            >
              <Pencil className="w-4 h-4" />
            </button>
          )}
          {((record.status || '').toLowerCase() === 'deprecated') && (
            <button
              onClick={() => handleRestore(record)}
              className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors"
              title="恢复"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          )}
          {!isProtected && (
              <button
                onClick={() => setDeleteConfirm({ open: true, skill: record, hard: false })}
                className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
                title="删除"
              >
                <Trash2 className="w-4 h-4" />
              </button>
          )}
        </div>
        );
      },
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
            options={[{ value: '', label: '全部' }, ...Object.entries(SKILL_CATEGORIES).map(([k, v]) => ({ value: k, label: v.text }))]}
            placeholder="分类筛选"
          />
          <Select
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || '')}
            options={[
              { value: '', label: '全部状态' },
              { value: 'draft', label: '草稿' },
              { value: 'ready', label: '待审核' },
              { value: 'published', label: '已发布' },
              { value: 'listed', label: '已上架' },
              { value: 'deprecated', label: '已废弃' },
            ]}
            placeholder="状态筛选"
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
        </div>
       </div>

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">名称</span><span className="ml-2 text-gray-600">SKILL.md 的 display_name，点击查看详情</span></div>
          <div><span className="text-gray-300">描述</span><span className="ml-2 text-gray-600">SKILL.md 的 description</span></div>
          <div><span className="text-gray-300">分类</span><span className="ml-2 text-gray-600">category：推理/编程/搜索/工具/通信/执行/检索/分析/生成/转换</span></div>
          <div><span className="text-gray-300">上架状态</span><span className="ml-2 text-gray-600"><span className="text-gray-400">draft</span> 开发中 · <span className="text-yellow-400">ready</span> 待审 · <span className="text-blue-400">published</span> 已发布 · <span className="text-green-400">listed</span> 上架 · <span className="text-red-400">deprecated</span> 废弃</span></div>
          <div><span className="text-gray-300">启用</span><span className="ml-2 text-gray-600">即上架状态。engine 内置为 published（只读）</span></div>
          <div><span className="text-gray-300">ID</span><span className="ml-2 text-gray-600">Skill 唯一标识符</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">详情/执行/编辑/恢复/弃用/删除</span></div>
        </div>
      </details>

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
        onClose={() => setDeleteConfirm({ open: false, skill: null, hard: false })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteConfirm({ open: false, skill: null, hard: false })} disabled={deleting}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete} loading={deleting}>
              确认
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-300 mb-3">将对 Skill "{deleteConfirm.skill?.name}" 执行删除操作：</p>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">删除方式</span>
          <Select
            value={deleteConfirm.hard ? 'hard' : 'soft'}
            onChange={(v: string) => setDeleteConfirm({ ...deleteConfirm, hard: v === 'hard' })}
            options={[
              { value: 'soft', label: '弃用 (deprecated，可恢复)' },
              { value: 'hard', label: '硬删除 (删除目录，不可撤销)' },
            ]}
          />
        </div>
      </Modal>

      {/* Skill Detail Modal */}
      <SkillDetailModal
        open={!!detailSkillId}
        skillId={detailSkillId}
        onClose={() => setDetailSkillId(null)}
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
