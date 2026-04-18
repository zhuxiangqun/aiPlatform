import React, { useState, useEffect } from 'react';
import { Copy, Info, RotateCw, RotateCcw, Trash2, Pencil, Play } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Select, Switch, Button, Modal, toast } from '../../../components/ui';
import { EditSkillModal, ExecuteSkillModal } from '../../../components/core';
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
  const { skills, loading, fetchSkills, toggleSkill, deleteSkill, restoreSkill } = useSkillStore();
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; skill: Skill | null; hard: boolean }>({ open: false, skill: null, hard: false });
  const [detailModal, setDetailModal] = useState<{ open: boolean; skill: Skill | null }>({ open: false, skill: null });

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleToggle = async (skill: Skill) => {
    try {
      if ((skill.status || '').toLowerCase() === 'deprecated') {
        toast.error('已弃用的 Skill 不能直接切换开关（可先“恢复”再启用）');
        return;
      }
      await toggleSkill(skill.id, !skill.enabled);
      toast.success(skill.enabled ? `Skill "${skill.name}" 已禁用` : `Skill "${skill.name}" 已启用`);
    } catch {
      toast.error('操作失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.skill) return;
    try {
      await deleteSkill(deleteConfirm.skill.id, { delete_files: deleteConfirm.hard });
      toast.success(deleteConfirm.hard ? 'Skill已彻底删除' : 'Skill已弃用（deprecated）');
      setDeleteConfirm({ open: false, skill: null, hard: false });
    } catch {
      toast.error('删除失败');
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

  const copyText = async (text: string) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast.success('已复制');
    } catch {
      toast.error('复制失败');
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
          onClick={() => setDetailModal({ open: true, skill: record })}
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
      key: 'status',
      width: 170,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => {
        const st = (record.status || (record.enabled ? 'enabled' : 'disabled')).toLowerCase();
        const badgeVariant = st === 'enabled' ? 'success' : st === 'disabled' ? 'warning' : st === 'deprecated' ? 'error' : 'default';
        return (
          <div className="flex items-center justify-center gap-2">
            <Badge variant={badgeVariant as any}>{st}</Badge>
            <Switch
              checked={record.enabled}
              disabled={st === 'deprecated'}
              onChange={() => handleToggle(record)}
            />
          </div>
        );
      },
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
      width: 180,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => {
        const isProtected = Boolean((record as any)?.metadata?.protected === true || (record as any)?.protected === true);
        return (
          <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => setDetailModal({ open: true, skill: record })}
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
            <>
              <button
                onClick={() => setDeleteConfirm({ open: true, skill: record, hard: false })}
                className="p-1.5 rounded-lg text-amber-300 hover:bg-dark-hover transition-colors"
                title="弃用（soft delete）"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              <button
                onClick={() => setDeleteConfirm({ open: true, skill: record, hard: true })}
                className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
                title="彻底删除（hard delete）"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
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
            options={Object.entries(categoryConfig).map(([k, v]) => ({ value: k, label: v.text }))}
            placeholder="分类筛选"
          />
          <Select
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || '')}
            options={[
              { value: 'enabled', label: 'enabled' },
              { value: 'disabled', label: 'disabled' },
              { value: 'deprecated', label: 'deprecated' },
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
        title={deleteConfirm.hard ? '确认彻底删除' : '确认弃用'}
        footer={
          <>
            <Button onClick={() => setDeleteConfirm({ open: false, skill: null, hard: false })}>
              取消
            </Button>
            <Button variant={deleteConfirm.hard ? 'danger' : 'secondary'} onClick={handleDelete}>
              {deleteConfirm.hard ? '彻底删除' : '弃用'}
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          {deleteConfirm.hard
            ? `确定要彻底删除 Skill "${deleteConfirm.skill?.name}" 吗？将删除磁盘目录与 SKILL.md，且不可恢复。`
            : `确定要弃用 Skill "${deleteConfirm.skill?.name}" 吗？将标记为 deprecated 并保留目录与 SOP，可后续恢复或硬删除。`}
        </p>
      </Modal>

      {/* Detail Modal */}
      <Modal
        open={detailModal.open}
        onClose={() => setDetailModal({ open: false, skill: null })}
        title={`Skill 详情：${detailModal.skill?.name || ''}`}
        width={820}
        footer={<Button onClick={() => setDetailModal({ open: false, skill: null })}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">skill_id</div>
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(detailModal.skill?.id || '-')}</code>
                {detailModal.skill?.id && (
                  <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(detailModal.skill?.id || ''))}>
                    复制
                  </Button>
                )}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">status</div>
              <div>{detailModal.skill?.status || (detailModal.skill?.enabled ? 'enabled' : 'disabled')}</div>
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500">filesystem.skill_dir</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">
                {String((detailModal.skill as any)?.metadata?.filesystem?.skill_dir || '-')}
              </code>
              {((detailModal.skill as any)?.metadata?.filesystem?.skill_dir) && (
                <Button
                  variant="ghost"
                  icon={<Copy className="w-4 h-4" />}
                  onClick={() => copyText(String((detailModal.skill as any)?.metadata?.filesystem?.skill_dir))}
                >
                  复制
                </Button>
              )}
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500">filesystem.skill_md</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">
                {String((detailModal.skill as any)?.metadata?.filesystem?.skill_md || '-')}
              </code>
              {((detailModal.skill as any)?.metadata?.filesystem?.skill_md) && (
                <Button
                  variant="ghost"
                  icon={<Copy className="w-4 h-4" />}
                  onClick={() => copyText(String((detailModal.skill as any)?.metadata?.filesystem?.skill_md))}
                >
                  复制
                </Button>
              )}
            </div>
          </div>
        </div>
      </Modal>

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
