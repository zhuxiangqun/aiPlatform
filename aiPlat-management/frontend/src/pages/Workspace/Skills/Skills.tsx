import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Copy, Info, Plus, RotateCw, Trash2, Pencil, Play, Layers, Clock } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Select, Switch, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceSkillStore } from '../../../stores';
import type { Skill } from '../../../services';
import { workspaceSkillApi } from '../../../services/coreApi';
import AddSkillModal from '../../../components/workspace/AddSkillModal';
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

const governanceBadge = (record: any) => {
  const g = (record?.metadata as any)?.governance || {};
  const v = (record?.metadata as any)?.verification || {};
  const st = String((g?.status || v?.status || '')).toLowerCase();
  if (st === 'verified') return <Badge variant={'success' as any}>verified</Badge>;
  if (st === 'failed') return <Badge variant={'error' as any}>failed</Badge>;
  if (st === 'pending') return <Badge variant={'warning' as any}>pending</Badge>;
  return <Badge variant={'default' as any}>n/a</Badge>;
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
  const { skills, loading, fetchSkills, toggleSkill, deleteSkill, restoreSkill } = useWorkspaceSkillStore();
  const location = useLocation() as any;
  const navigate = useNavigate();
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [filterSkillIds, setFilterSkillIds] = useState<string[] | null>(null);
  const [detailModal, setDetailModal] = useState<{ open: boolean; skill: Skill | null }>({ open: false, skill: null });
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; skill: Skill | null; hard: boolean }>({ open: false, skill: null, hard: false });
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [versionsModalOpen, setVersionsModalOpen] = useState(false);
  const [executionsModalOpen, setExecutionsModalOpen] = useState(false);
  const [skillMdOpen, setSkillMdOpen] = useState(false);
  const [skillMdLoading, setSkillMdLoading] = useState(false);
  const [skillMd, setSkillMd] = useState<{ path: string; content: string } | null>(null);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // Skill Pack -> Workspace Skill quick filter (by navigation state)
  useEffect(() => {
    try {
      const ids = location?.state?.filterSkillIds;
      if (Array.isArray(ids) && ids.length) {
        setFilterSkillIds(ids.map((x: any) => String(x)).filter((x: string) => x.trim()));
      }
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location?.key]);

  const handleToggle = async (skill: Skill) => {
    try {
      if ((skill.status || '').toLowerCase() === 'deprecated') {
        toast.error('已弃用的 Skill 不能直接切换开关（可先“恢复”再启用）');
        return;
      }
      const res: any = await toggleSkill(skill.id, !skill.enabled);
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.error(`需要审批：${res.approval_request_id}`);
        try {
          window.open('/core/learning/approvals', '_blank', 'noopener,noreferrer');
        } catch {
          // ignore
        }
        return;
      }
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
    if (filterSkillIds && filterSkillIds.length && !filterSkillIds.includes(s.id)) return false;
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
      title: '来源',
      key: 'source',
      width: 220,
      render: (_: unknown, record: Skill) => {
        const sp: any = (record as any)?.metadata?.skill_pack;
        const packId = sp?.pack_id || sp?.packId || sp?.id;
        const ver = sp?.version;
        if (!packId) return <span className="text-gray-500">-</span>;
        return (
          <div className="flex items-center gap-2">
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(packId).slice(0, 10)}...</code>
            <span className="text-xs text-gray-400">{ver ? `v${ver}` : ''}</span>
            <button
              className="text-xs text-primary hover:underline"
              onClick={() => navigate('/core/skill-packs', { state: { openPackId: String(packId) } })}
              title="打开 Skill Pack"
            >
              查看包
            </button>
          </div>
        );
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
      title: '治理',
      key: 'governance',
      width: 110,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => <div className="flex items-center justify-center">{governanceBadge(record)}</div>,
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
  const sp = ((detailModal.skill as any)?.metadata?.skill_pack || {}) as any;
  const gov = ((detailModal.skill as any)?.metadata?.governance || {}) as any;
  const ver = ((detailModal.skill as any)?.metadata?.verification || {}) as any;

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

      {filterSkillIds && filterSkillIds.length > 0 && (
        <div className="bg-dark-card border border-dark-border rounded-xl p-3 flex items-center justify-between">
          <div className="text-sm text-gray-300">
            当前按 Skill Pack 过滤：<span className="text-gray-100 font-medium">{filterSkillIds.length}</span> 个 skill
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(filterSkillIds.join(','));
                  toast.success('已复制 skill_ids');
                } catch {
                  toast.error('复制失败');
                }
              }}
            >
              复制 skill_ids
            </Button>
            <Button onClick={() => setFilterSkillIds(null)}>清除过滤</Button>
          </div>
        </div>
      )}

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
            <div className="text-xs text-gray-500">skill_pack</div>
            {sp?.pack_id ? (
              <div className="flex items-center justify-between gap-2">
                <div className="text-gray-300">
                  <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(sp.pack_id)}</code>
                  <span className="ml-2 text-xs text-gray-400">{sp?.version ? `v${sp.version}` : ''}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(String(sp.pack_id));
                        toast.success('已复制 pack_id');
                      } catch {
                        toast.error('复制失败');
                      }
                    }}
                  >
                    复制
                  </Button>
                  <Button variant="primary" onClick={() => navigate('/core/skill-packs', { state: { openPackId: String(sp.pack_id) } })}>
                    查看包
                  </Button>
                </div>
              </div>
            ) : (
              <div className="text-gray-500">-</div>
            )}
          </div>
          <div>
            <div className="text-xs text-gray-500">governance</div>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {governanceBadge({ metadata: { governance: gov, verification: ver } } as any)}
                <span className="text-xs text-gray-500">
                  {gov?.job_run_id ? `job_run: ${String(gov.job_run_id).slice(0, 10)}...` : ''}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {gov?.candidate_id && (
                  <Button variant="ghost" onClick={() => copyText(String(gov.candidate_id))}>
                    复制 candidate_id
                  </Button>
                )}
                <Button
                  variant="secondary"
                  onClick={() => {
                    try {
                      window.open('/core/learning/releases', '_blank', 'noopener,noreferrer');
                    } catch {
                      // ignore
                    }
                  }}
                >
                  打开 Releases
                </Button>
              </div>
            </div>
            <pre className="mt-2 text-xs bg-dark-hover rounded p-2 overflow-auto max-h-40">{JSON.stringify(gov || {}, null, 2)}</pre>
          </div>
          <div>
            <div className="text-xs text-gray-500">filesystem.skill_md</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(fs.skill_md || '-')}</code>
              {fs.skill_md && (
                <div className="flex items-center gap-2">
                  <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(fs.skill_md))}>
                    复制
                  </Button>
                  <Button
                    variant="primary"
                    onClick={async () => {
                      if (!detailModal.skill?.id) return;
                      setSkillMdOpen(true);
                      setSkillMdLoading(true);
                      setSkillMd(null);
                      try {
                        const res = await workspaceSkillApi.getSkillMarkdown(String(detailModal.skill.id));
                        setSkillMd({ path: res.path, content: res.content });
                      } catch (e: any) {
                        toast.error('预览失败', String(e?.message || ''));
                      } finally {
                        setSkillMdLoading(false);
                      }
                    }}
                  >
                    预览
                  </Button>
                </div>
              )}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">provenance</div>
              <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-40">
                {JSON.stringify((detailModal.skill as any)?.metadata?.provenance || {}, null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-xs text-gray-500">integrity</div>
              <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-40">
                {JSON.stringify((detailModal.skill as any)?.metadata?.integrity || {}, null, 2)}
              </pre>
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">metadata</div>
            <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-56">{JSON.stringify(detailModal.skill?.metadata || {}, null, 2)}</pre>
          </div>
        </div>
      </Modal>

      <Modal
        open={skillMdOpen}
        onClose={() => { setSkillMdOpen(false); setSkillMd(null); }}
        title={`SKILL.md 预览：${detailModal.skill?.id || ''}`}
        width={980}
        footer={<Button onClick={() => { setSkillMdOpen(false); setSkillMd(null); }}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <div className="text-xs text-gray-500">path</div>
          <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{skillMd?.path || '-'}</code>
          <div className="text-xs text-gray-500">content</div>
          <pre className="text-xs bg-dark-hover rounded p-3 overflow-auto max-h-[520px]">
            {skillMdLoading ? '加载中...' : (skillMd?.content || '')}
          </pre>
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

      <AddSkillModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={fetchSkills}
      />
    </div>
  );
};

export default WorkspaceSkills;
