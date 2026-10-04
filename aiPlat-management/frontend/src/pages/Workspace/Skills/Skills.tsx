import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Plus, RotateCw, ShieldCheck, Upload, Key } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Switch, Button, Modal, toast, Input } from '../../../components/ui';
import { useWorkspaceSkillStore } from '../../../stores';
import { type Skill } from '../../../services';
import { workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../components/ui';
import AddSkillModal from '../../../components/workspace/AddSkillModal';
import SkillChatCreateModal from '../../../components/workspace/SkillChatCreateModal';
import WorkspacePageGuide from '../../../components/workspace/WorkspacePageGuide';
import EditSkillModal from '../../../components/workspace/EditSkillModal';
import ExecuteSkillModal from '../../../components/workspace/ExecuteSkillModal';
import SkillVersionsModal from '../../../components/workspace/SkillVersionsModal';
import SkillExecutionsModal from '../../../components/workspace/SkillExecutionsModal';
import WorkspaceSkillDetailModal from '../../../components/workspace/WorkspaceSkillDetailModal';
import SkillRowActions from '../../../components/workspace/SkillRowActions';
import AssetStatusLegend from '../../../components/workspace/AssetStatusLegend';
import ImportBar from '../../../components/workspace/ImportBar';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { SKILL_CATEGORIES } from '../../../utils/categoryConfig';
import { GovDetailBadge, StatusBadge } from '../../../utils/statusLabel';

const governanceBadge = (record: any) => <GovDetailBadge record={record} />;

const SKILL_CATEGORY_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'general', label: '通用' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
  { value: 'transformation', label: '转换' },
];

const WorkspaceSkills: React.FC = () => {
  const navigate = useNavigate();
  const { skills, loading, fetchSkills, deleteSkill, restoreSkill } = useWorkspaceSkillStore();
  const location = useLocation() as any;
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [filterSkillIds, setFilterSkillIds] = useState<string[] | null>(null);
  const [detailModal, setDetailModal] = useState<{ open: boolean; skill: Skill | null }>({ open: false, skill: null });
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; skill: Skill | null; hard: boolean }>({ open: false, skill: null, hard: false });
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [chatCreateOpen, setChatCreateOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editInitialSection, setEditInitialSection] = useState<'basic' | 'gov' | 'io' | 'sop'>('basic');
  const [deleting, setDeleting] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [versionsModalOpen, setVersionsModalOpen] = useState(false);
  const [executionsModalOpen, setExecutionsModalOpen] = useState(false);
  const [seedsModalOpen, setSeedsModalOpen] = useState(false);
  const [seeds, setSeeds] = useState<any[]>([]);
  const [seedsLoading, setSeedsLoading] = useState(false);
  const [batchSignOpen, setBatchSignOpen] = useState(false);
  const [batchSignKey, setBatchSignKey] = useState('');
  const [batchSigning, setBatchSigning] = useState(false);
  const [batchResult, setBatchResult] = useState<{ total: number; signed: number; failed: number } | null>(null);

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

  const handleExportPlugin = async (skill: any) => {
    try {
      const name = (skill.name || skill.id || 'skill').replace(/\s+/g, '_');
      const res = await fetch('/api/core/workspace/packages/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          version: '0.1.0',
          description: (skill as any).metadata?.description || skill.description || '',
          resources: [{ kind: 'skill', id: skill.id }],
        }),
      });
      if (!res.ok) { toast.error('导出失败'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${name}.zip`; a.click();
      URL.revokeObjectURL(url);
      toast.success(`已导出 ${name}`);
    } catch (e: any) { toast.error(`导出失败: ${e?.message || ''}`); }
  };

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

  const handleSubmitForReview = async (skill: Skill) => {
    try {
      await workspaceSkillApi.submitForReview(skill.id);
      toast.success(`Skill "${skill.name}" 已提交审批`);
      fetchSkills();
    } catch (e: any) {
      toast.error('提交失败', e?.message || String(e));
    }
  };

  const loadSeeds = async () => {
    setSeedsLoading(true);
    try {
      const r = await workspaceSkillApi.listSeeds();
      setSeeds(r.seeds || []);
    } catch { setSeeds([]); }
    finally { setSeedsLoading(false); }
  };

  const installSeed = async (seedId: string) => {
    try {
      await workspaceSkillApi.installSeed(seedId);
      toast.success(`已安装：${seedId}`);
      loadSeeds();
      fetchSkills();
    } catch (e: any) { toast.error('安装失败', e?.message || String(e)); }
  };

  const handleBatchSign = async () => {
    if (!batchSignKey.trim()) return;
    setBatchSigning(true);
    setBatchResult(null);
    try {
      const res = await workspaceSkillApi.signAll({ private_key: batchSignKey.trim() });
      setBatchResult({ total: res.total, signed: res.signed, failed: res.failed });
      toast.success(`批量签名完成：${res.signed} 成功 / ${res.failed} 失败`);
      fetchSkills();
    } catch (e: any) {
      toastGateError(e, '批量签名失败');
    } finally { setBatchSigning(false); }
  };

  const filteredSkills = skills.filter(s => {
    if (filterSkillIds && filterSkillIds.length && !filterSkillIds.includes(s.id)) return false;
    if (categoryFilter && s.category !== categoryFilter) return false;
    if (enabledOnly && !['published', 'listed'].includes((s.status || '').toLowerCase())) return false;
    if (statusFilter) {
      const st = (s.status || 'draft').toLowerCase();
      if (st !== statusFilter) return false;
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const hay = `${s.id || ''} ${s.name || ''} ${(s as any).display_name || ''} ${s.description || ''} ${s.category || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
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
        const cfg = SKILL_CATEGORIES[c] || { color: 'bg-dark-hover text-gray-300 border-gray-200', text: c };
        return <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}`}>{cfg.text}</span>;
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
      title: (
        <span title="生命周期：草稿→待审核→已发布→已上架。已启用≈可用旧状态。">上架状态</span>
      ),
      key: 'status',
      width: 88,
      render: (_: unknown, record: Skill) => <StatusBadge status={record.status} />,
    },
    {
      title: (
        <span title="签名/冒烟校验，与上架审核无关。未签名也可本机执行。">治理</span>
      ),
      key: 'governance',
      width: 88,
      align: 'center' as const,
      render: (_: unknown, record: Skill) => <div className="flex items-center justify-center">{governanceBadge(record)}</div>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      align: 'right' as const,
      sticky: 'right' as const,
      render: (_: unknown, record: Skill) => (
        <SkillRowActions
          skill={record}
          onExecute={(s) => { setExecuteSkill(s); setExecuteModalOpen(true); }}
          onEdit={(s) => { setEditSkill(s); setEditInitialSection('basic'); setEditModalOpen(true); }}
          onDetail={(s) => setDetailModal({ open: true, skill: s })}
          onVersions={(s) => { setEditSkill(s); setVersionsModalOpen(true); }}
          onHistory={(s) => { setExecuteSkill(s); setExecutionsModalOpen(true); }}
          onSubmitReview={handleSubmitForReview}
          onOpenApproval={() => navigate('/approval?type=skill&status=ready')}
          onExport={handleExportPlugin}
          onDeprecate={(s) => setDeleteConfirm({ open: true, skill: s, hard: false })}
          onRestore={handleRestore}
        />
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 Skill</h1>
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/skills（可编辑、可删除）</p>
        </div>
        <div className="flex items-center gap-2">
          <Button icon={<Plus className="w-4 h-4" />} onClick={() => setAddModalOpen(true)}>
            创建
          </Button>
          <Button variant="secondary" onClick={() => setChatCreateOpen(true)}>
            对话创建
          </Button>
          <Button variant="secondary" icon={<ShieldCheck className="w-4 h-4" />} onClick={() => navigate('/approval?type=skill&status=ready')}>
            资产审批
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchSkills()} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <WorkspacePageGuide
        steps={[
          { title: '执行 / 编辑', detail: '日常就用这两项；草稿可直接自测' },
          { title: '更多', detail: '提交审批、详情、版本、历史、弃用、导出' },
          { title: '资产审批', detail: '管理员点通过 → 已发布；再上架 → 已上架' },
        ]}
        tip="行内只保留「执行 / 编辑 / 更多」。模板安装、批量签名在下方导入区旁。"
      />

      <div className="flex flex-wrap items-center gap-2">
        <ImportBar assetType="skills" alsoScan={['agents', 'mcps']} onImported={() => fetchSkills()} />
      </div>
      <div className="flex flex-wrap items-center gap-2 -mt-2">
        <Button variant="secondary" size="sm" icon={<Upload className="w-3.5 h-3.5" />} onClick={() => { loadSeeds(); setSeedsModalOpen(true); }}>
          从模板安装
        </Button>
        <Button variant="secondary" size="sm" icon={<Key className="w-3.5 h-3.5" />} onClick={() => setBatchSignOpen(true)}>
          批量签名
        </Button>
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
          <Select value={categoryFilter} onChange={(v: string) => { setCategoryFilter(v); fetchSkills({ category: v || undefined, enabled_only: enabledOnly, status: statusFilter || undefined }); }} options={SKILL_CATEGORY_OPTIONS} />
        </div>
        <div className="w-44">
          <Select
            value={statusFilter}
            onChange={(v: string) => setStatusFilter(v)}
            options={[
              { value: '', label: '全部状态' },
              { value: 'draft', label: '草稿 (draft)' },
              { value: 'ready', label: '待审核 (ready)' },
              { value: 'published', label: '已发布 (published)' },
              { value: 'listed', label: '已上架 (listed)' },
              { value: 'deprecated', label: '已废弃 (deprecated)' },
            ]}
          />
        </div>
        <div className="flex-1 min-w-[200px] max-w-md">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索名称、ID 或描述..." />
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Switch checked={enabledOnly} onChange={() => setEnabledOnly(!enabledOnly)} />
          仅启用
        </div>
      </div>

      <AssetStatusLegend kind="skill" showSmokeTrack howToSubmit="更多 → 提交审批" />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={filteredSkills} rowKey="id" loading={loading} emptyText="暂无 Skill" />
      </motion.div>

      <EditSkillModal
        open={editModalOpen}
        skill={editSkill}
        initialSection={editInitialSection}
        onClose={() => { setEditModalOpen(false); setEditSkill(null); setEditInitialSection('basic'); }}
        onSuccess={() => fetchSkills()}
      />

      <ExecuteSkillModal
        open={executeModalOpen}
        skill={
          executeSkill
            ? {
                id: executeSkill.id,
                name: executeSkill.name,
                input_schema: executeSkill.input_schema,
                metadata: (executeSkill as any).metadata || null,
              }
            : null
        }
        onClose={() => { setExecuteModalOpen(false); setExecuteSkill(null); }}
        onEditSop={() => {
          if (!executeSkill) return;
          setEditSkill(executeSkill);
          setEditInitialSection('sop');
          setExecuteModalOpen(false);
          setEditModalOpen(true);
        }}
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

      <WorkspaceSkillDetailModal
        open={detailModal.open}
        skill={detailModal.skill}
        onClose={() => setDetailModal({ open: false, skill: null })}
        onRefresh={fetchSkills}
        onEdit={(s) => { setEditSkill(s); setEditInitialSection('basic'); setEditModalOpen(true); }}
        onExecute={(s) => { setExecuteSkill(s); setExecuteModalOpen(true); }}
        onVersions={(s) => { setEditSkill(s); setVersionsModalOpen(true); }}
      />

      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, skill: null, hard: false })}
        title="确认删除"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteConfirm({ open: false, skill: null, hard: false })} disabled={deleting}>
              取消
            </Button>
            <Button variant="primary" onClick={handleDelete} loading={deleting}>
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
      <SkillChatCreateModal
        open={chatCreateOpen}
        onClose={() => setChatCreateOpen(false)}
        onSuccess={fetchSkills}
      />

      <Modal
        open={seedsModalOpen}
        onClose={() => setSeedsModalOpen(false)}
        title="从模板安装 Skill"
        width={600}
        footer={<Button onClick={() => setSeedsModalOpen(false)}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">选择一个模板安装到 workspace。安装后可自由编辑 SKILL.md。</p>
          {seedsLoading ? (
            <div className="text-gray-500 text-center py-4">加载中...</div>
          ) : seeds.length === 0 ? (
            <div className="text-gray-500 text-center py-4">
              暂无可用模板
              <div className="text-[10px] text-gray-600 mt-1">将 SKILL.md 放入 aiPlat-core/core/workspace_seeds/skills/&lt;id&gt;/ 即可作为模板</div>
            </div>
          ) : (
            seeds.map((s: any) => (
              <div key={s.id} className="flex items-center justify-between p-3 rounded border border-dark-border bg-dark-bg">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-gray-200">{s.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{s.description}</div>
                  {s.category && <span className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-400 mt-1 inline-block">{s.category}</span>}
                </div>
                {s.installed ? (
                  <span className="text-xs text-green-400 ml-3">已安装</span>
                ) : (
                  <Button variant="primary" size="sm" onClick={() => installSeed(s.id)}>安装</Button>
                )}
              </div>
            ))
          )}
        </div>
      </Modal>

      <Modal
        open={batchSignOpen}
        onClose={() => { setBatchSignOpen(false); setBatchResult(null); }}
        title="批量签名"
        width={500}
        footer={<Button onClick={() => { setBatchSignOpen(false); setBatchResult(null); }}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">对所有 workspace Skill 使用同一个私钥签名。私钥不会保存。</p>
          {batchResult ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-green-400">
                <ShieldCheck size={16} />
                <span>完成：{batchResult.signed} 成功 / {batchResult.failed} 失败 / {batchResult.total} 总计</span>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <textarea
                className="w-full h-24 px-3 py-2 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
                placeholder="粘贴 Ed25519 私钥 PEM（-----BEGIN PRIVATE KEY-----...）"
                value={batchSignKey}
                onChange={(e) => setBatchSignKey(e.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  onClick={handleBatchSign}
                  loading={batchSigning}
                  disabled={!batchSignKey.trim() || batchSigning}
                >
                  开始批量签名
                </Button>
                <Button variant="ghost" size="sm" onClick={() => { try { window.open('/onboarding?step=sign_keys', '_blank', 'noopener,noreferrer'); } catch {} }}>
                  生成密钥
                </Button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default WorkspaceSkills;
