import React, { useEffect, useState } from 'react';
import { Copy, Info, Plus, RotateCw, Trash2, Pencil, Play, Layers, Clock } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Select, Switch, Button, Modal, Input, toast } from '../../../components/ui';
import { useWorkspaceSkillStore } from '../../../stores';
import type { Skill } from '../../../services';
import EditSkillModal from '../../../components/workspace/EditSkillModal';
import ExecuteSkillModal from '../../../components/workspace/ExecuteSkillModal';
import SkillVersionsModal from '../../../components/workspace/SkillVersionsModal';
import SkillExecutionsModal from '../../../components/workspace/SkillExecutionsModal';

const categoryConfig: Record<string, { color: string; text: string }> = {
  general: { color: 'bg-dark-hover text-gray-300 border-gray-200', text: '通用' },
  execution: { color: 'bg-orange-50 text-orange-300 border-orange-200', text: '执行' },
  retrieval: { color: 'bg-teal-50 text-teal-300 border-teal-200', text: '检索' },
  analysis: { color: 'bg-indigo-50 text-indigo-300 border-indigo-200', text: '分析' },
  generation: { color: 'bg-pink-50 text-pink-300 border-pink-200', text: '生成' },
  transformation: { color: 'bg-yellow-50 text-yellow-300 border-yellow-200', text: '转换' },
};

const SKILL_CATEGORIES = [
  { value: '', label: '全部' },
  { value: 'general', label: '通用' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
  { value: 'transformation', label: '转换' },
];

const WorkspaceSkills: React.FC = () => {
  const { skills, loading, fetchSkills, toggleSkill, deleteSkill, restoreSkill, createSkill } = useWorkspaceSkillStore();
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [detailModal, setDetailModal] = useState<{ open: boolean; skill: Skill | null }>({ open: false, skill: null });
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; skill: Skill | null; hard: boolean }>({ open: false, skill: null, hard: false });
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [versionsModalOpen, setVersionsModalOpen] = useState(false);
  const [executionsModalOpen, setExecutionsModalOpen] = useState(false);

  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState('general');
  const [newDesc, setNewDesc] = useState('');

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
        <button className="font-medium text-gray-100 text-left hover:underline" onClick={() => setDetailModal({ open: true, skill: record })}>
          {name}
        </button>
      ),
    },
    { title: '描述', dataIndex: 'description', key: 'description', render: (d: string) => <span className="text-gray-500">{d || '-'}</span> },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (c: string) => {
        const cfg = categoryConfig[c] || { color: 'bg-dark-hover text-gray-300 border-gray-200', text: c };
        return <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}`}>{cfg.text}</span>;
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 140,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => {
        const st = (record.status || (record.enabled ? 'enabled' : 'disabled')).toLowerCase();
        if (st === 'deprecated') return <Badge variant={'error' as any}>deprecated</Badge>;
        return (
          <div className="flex items-center justify-center gap-2">
            <Badge variant={(record.enabled ? 'success' : 'warning') as any}>{record.enabled ? 'enabled' : 'disabled'}</Badge>
            <Switch checked={record.enabled} onChange={() => handleToggle(record)} />
          </div>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => { setEditSkill(record); setVersionsModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="版本"
          >
            <Layers className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setExecuteSkill(record); setExecutionsModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="历史"
          >
            <Clock className="w-4 h-4" />
          </button>
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
          {(record.status || '').toLowerCase() === 'deprecated' ? (
            <Button size="sm" variant="secondary" onClick={() => handleRestore(record)}>
              恢复
            </Button>
          ) : (
            <button
              onClick={() => setDeleteConfirm({ open: true, skill: record, hard: false })}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="弃用"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => setDetailModal({ open: true, skill: record })}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="详情"
          >
            <Info className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  const fs = ((detailModal.skill as any)?.metadata?.filesystem || {}) as any;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 Skill</h1>
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/skills（可编辑、可删除）</p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<Plus className="w-4 h-4" />} onClick={() => setAddModalOpen(true)}>
            创建
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchSkills()} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="w-44">
          <Select value={categoryFilter} onChange={(v: string) => { setCategoryFilter(v); fetchSkills({ category: v || undefined, enabled_only: enabledOnly, status: statusFilter || undefined }); }} options={SKILL_CATEGORIES} />
        </div>
        <div className="w-44">
          <Select
            value={statusFilter}
            onChange={(v: string) => setStatusFilter(v)}
            options={[
              { value: '', label: '全部状态' },
              { value: 'enabled', label: 'enabled' },
              { value: 'disabled', label: 'disabled' },
              { value: 'deprecated', label: 'deprecated' },
            ]}
          />
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Switch checked={enabledOnly} onChange={() => setEnabledOnly(!enabledOnly)} />
          仅启用
        </div>
      </div>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={filteredSkills} rowKey="id" loading={loading} emptyText="暂无 Skill" />
      </motion.div>

      <EditSkillModal
        open={editModalOpen}
        skill={editSkill}
        onClose={() => { setEditModalOpen(false); setEditSkill(null); }}
        onSuccess={() => fetchSkills()}
      />

      <ExecuteSkillModal
        open={executeModalOpen}
        skill={executeSkill ? { id: executeSkill.id, name: executeSkill.name } : null}
        onClose={() => { setExecuteModalOpen(false); setExecuteSkill(null); }}
      />

      <SkillVersionsModal
        open={versionsModalOpen}
        skill={editSkill ? { id: editSkill.id, name: editSkill.name } : null}
        onClose={() => { setVersionsModalOpen(false); setEditSkill(null); }}
      />

      <SkillExecutionsModal
        open={executionsModalOpen}
        skill={executeSkill ? { id: executeSkill.id, name: executeSkill.name } : null}
        onClose={() => { setExecutionsModalOpen(false); setExecuteSkill(null); }}
      />

      <Modal
        open={detailModal.open}
        onClose={() => setDetailModal({ open: false, skill: null })}
        title={`Skill 详情：${detailModal.skill?.name || ''}`}
        width={860}
        footer={<Button onClick={() => setDetailModal({ open: false, skill: null })}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <div>
            <div className="text-xs text-gray-500">id</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{detailModal.skill?.id}</code>
              <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(detailModal.skill?.id || ''))}>
                复制
              </Button>
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">filesystem.skill_md</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(fs.skill_md || '-')}</code>
              {fs.skill_md && (
                <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(fs.skill_md))}>
                  复制
                </Button>
              )}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">metadata</div>
            <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-56">{JSON.stringify(detailModal.skill?.metadata || {}, null, 2)}</pre>
          </div>
        </div>
      </Modal>

      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, skill: null, hard: false })}
        title="确认删除"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteConfirm({ open: false, skill: null, hard: false })}>
              取消
            </Button>
            <Button variant="primary" onClick={handleDelete}>
              确认
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm text-gray-300">
          <div>将对 Skill “{deleteConfirm.skill?.name}”执行删除操作：</div>
          <div className="flex items-center gap-3">
            <Select
              value={deleteConfirm.hard ? 'hard' : 'soft'}
              onChange={(v: string) => setDeleteConfirm({ ...deleteConfirm, hard: v === 'hard' })}
              options={[
                { value: 'soft', label: '弃用（deprecated）' },
                { value: 'hard', label: '彻底删除（删除目录）' },
              ]}
            />
          </div>
        </div>
      </Modal>

      <Modal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        title="创建应用库 Skill"
        footer={
          <>
            <Button variant="secondary" onClick={() => setAddModalOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={async () => {
                if (!newName.trim()) return;
                try {
                  await createSkill({ name: newName.trim(), description: newDesc, category: newCategory });
                  toast.success('已创建');
                  setAddModalOpen(false);
                  setNewName('');
                  setNewDesc('');
                  setNewCategory('general');
                } catch {
                  toast.error('创建失败（可能与引擎 Skill 同名被保留）');
                }
              }}
            >
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">名称</label>
            <Input value={newName} onChange={(e: any) => setNewName(e.target.value)} placeholder="例如：我的客服助手" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">分类</label>
            <Select value={newCategory} onChange={(v: string) => setNewCategory(v)} options={SKILL_CATEGORIES.filter(x => x.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">描述</label>
            <Input value={newDesc} onChange={(e: any) => setNewDesc(e.target.value)} placeholder="描述用途" />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default WorkspaceSkills;
