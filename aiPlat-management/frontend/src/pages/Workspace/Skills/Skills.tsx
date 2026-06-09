import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Copy, Info, Plus, RotateCw, Trash2, Pencil, Play, Layers, Clock, ShieldCheck, Upload, Key } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Select, Switch, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceSkillStore } from '../../../stores';
import { learningApi, type Skill } from '../../../services';
import { workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../components/ui';
import AddSkillModal from '../../../components/workspace/AddSkillModal';
import EditSkillModal from '../../../components/workspace/EditSkillModal';
import ExecuteSkillModal from '../../../components/workspace/ExecuteSkillModal';
import SkillVersionsModal from '../../../components/workspace/SkillVersionsModal';
import SkillExecutionsModal from '../../../components/workspace/SkillExecutionsModal';
import ImportBar from '../../../components/workspace/ImportBar';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { SKILL_CATEGORIES } from '../../../utils/categoryConfig';
import { GovDetailBadge } from '../../../utils/statusLabel';

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
  const { skills, loading, fetchSkills, deleteSkill, restoreSkill } = useWorkspaceSkillStore();
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
  const [deleting, setDeleting] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<Skill | null>(null);
  const [executeSkill, setExecuteSkill] = useState<Skill | null>(null);
  const [versionsModalOpen, setVersionsModalOpen] = useState(false);
  const [executionsModalOpen, setExecutionsModalOpen] = useState(false);
  const [skillMdOpen, setSkillMdOpen] = useState(false);
  const [skillMdLoading, setSkillMdLoading] = useState(false);
  const [skillMd, setSkillMd] = useState<{ path: string; content: string } | null>(null);
  const [seedsModalOpen, setSeedsModalOpen] = useState(false);
  const [seeds, setSeeds] = useState<any[]>([]);
  const [seedsLoading, setSeedsLoading] = useState(false);
  const [signing, setSigning] = useState(false);
  const [signKey, setSignKey] = useState('');
  const [signResult, setSignResult] = useState<string | null>(null);
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

  const handleSign = async () => {
    if (!detailModal.skill?.id || !signKey.trim()) return;
    setSigning(true);
    setSignResult(null);
    try {
      const res = await workspaceSkillApi.sign(detailModal.skill.id, { private_key: signKey.trim() });
      setSignResult(res.signature);
      toast.success('签名成功');
      setSignKey('');
      fetchSkills();
    } catch (e: any) {
      toastGateError(e, '签名失败');
      setSignResult(null);
    } finally {
      setSigning(false);
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
    if (enabledOnly && !['published', 'listed'].includes((s.status || '').toLowerCase())) return false;
    if (statusFilter) {
      const st = (s.status || 'draft').toLowerCase();
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
      title: '上架状态',
      dataIndex: 'status',
      key: 'listing_status',
      width: 130,
      align: 'center' as const,
      render: (s: string) => {
        const labels: Record<string, string> = { draft: '草稿', ready: '待审核', published: '已发布', listed: '已上架', deprecated: '已废弃' };
        const colors: Record<string, string> = { draft: '#888', ready: '#f59e0b', published: '#3b82f6', listed: '#10b981', deprecated: '#6b7280' };
        return <span className="text-xs" style={{ color: colors[s] || '#888' }}>{labels[s] || s || '-'}</span>;
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
      width: 160,
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
            <>
              {(record.status || '').toLowerCase() === 'draft' || (record.status || '').toLowerCase() === 'enabled' ? (
                <button
                  onClick={() => handleSubmitForReview(record)}
                  className="p-1.5 rounded-lg text-amber-400 hover:bg-amber-400/10 transition-colors"
                  title="提交审批"
                >
                  <ShieldCheck className="w-4 h-4" />
                </button>
              ) : null}
              <button
                onClick={() => setDeleteConfirm({ open: true, skill: record, hard: false })}
                className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
                title="弃用"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleExportPlugin(record)}
                className="p-1.5 rounded-lg text-purple-400 hover:bg-purple-400/10 transition-colors"
                title="导出为插件"
              >
                <Upload className="w-4 h-4" />
              </button>
            </>
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
          <Button variant="secondary" icon={<Upload className="w-4 h-4" />} onClick={() => { loadSeeds(); setSeedsModalOpen(true); }}>
            从模板安装
          </Button>
          <Button variant="secondary" icon={<ShieldCheck className="w-4 h-4" />} onClick={() => setBatchSignOpen(true)}>
            批量签名
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchSkills()} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <ImportBar assetType="skills" alsoScan={['agents', 'mcps']} onImported={() => fetchSkills()} />

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
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Switch checked={enabledOnly} onChange={() => setEnabledOnly(!enabledOnly)} />
          仅启用
        </div>
      </div>

      {/* Legend */}
      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">名称/描述</span><span className="ml-2 text-gray-600">SKILL.md 的 display_name + description</span></div>
          <div><span className="text-gray-300">分类</span><span className="ml-2 text-gray-600">category：生成/分析/检索/执行/design/document/tool/text</span></div>
          <div><span className="text-gray-300">上架状态</span><span className="ml-2 text-gray-600"><span className="text-gray-400">draft</span> 开发中 · <span className="text-yellow-400">ready</span> 待审 · <span className="text-green-400">published</span> 已发布 · <span className="text-green-400">listed</span> 上架 · <span className="text-red-400">deprecated</span> 废弃</span></div>
          <div><span className="text-gray-300">启用</span><span className="ml-2 text-gray-600">即上架状态。draft 可直接执行测试。published/listed 为可用</span></div>
          <div><span className="text-gray-300">治理</span><span className="ml-2 text-gray-600"><span className="text-green-400">已验签</span> 签名验证通过 · <span className="text-blue-400">已签名</span> 已写入签名 · <span className="text-yellow-400">pending</span> 等待中 · <span className="text-red-400">failed</span> 未通过 · <span className="text-gray-400">未签名</span> 缺少签名</span></div>
          <div><span className="text-gray-300">Lint</span><span className="ml-2 text-gray-600"><span className="text-red-300">E数</span>=错误 <span className="text-yellow-300">W数</span>=警告 low/medium/high=风险</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">版本/历史/执行/编辑/审批/弃用/导出/详情</span></div>
        </div>
      </details>

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
                {gov?.candidate_id && String(gov?.published_candidate_id || '') !== String(gov?.candidate_id || '') && (
                  <Button
                    variant="primary"
                    onClick={async () => {
                      try {
                        const cid = String(gov.candidate_id);
                        const r: any = await learningApi.publishCandidate(cid, {
                          user_id: 'admin',
                          require_approval: true,
                          details: `publish workspace skill ${String(detailModal.skill?.id || '')}`,
                        });
                        if (r?.status === 'approval_required' && r?.approval_request_id) {
                          toast.error(`需要审批：${String(r.approval_request_id)}`);
                          try {
                            window.open('/core/approvals', '_blank', 'noopener,noreferrer');
                          } catch {
                            // ignore
                          }
                          return;
                        }
                        toast.success('已发布');
                        fetchSkills();
                        setDetailModal({ open: false, skill: null });
                      } catch (e: any) {
                        toastGateError(e, '发布失败');
                      }
                    }}
                  >
                    发布
                  </Button>
                )}
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
            <div className="text-xs text-gray-500 mb-1">签名</div>
            {signResult ? (
              <div className="flex items-center gap-2 text-success text-xs">
                <ShieldCheck size={14} />
                <span>已签名 · {signResult.slice(0, 16)}...</span>
                <Button variant="ghost" onClick={() => setSignResult(null)}>重新签名</Button>
              </div>
            ) : (
              <div className="flex items-start gap-2">
                <textarea
                  className="flex-1 h-16 px-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-xs text-gray-200 placeholder-gray-500 font-mono focus:outline-none focus:border-primary resize-none"
                  placeholder="粘贴 Ed25519 私钥 PEM（-----BEGIN PRIVATE KEY-----...）"
                  value={signKey}
                  onChange={(e) => setSignKey(e.target.value)}
                />
                <div className="flex flex-col gap-1">
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<Key size={14} />}
                    onClick={handleSign}
                    loading={signing}
                    disabled={!signKey.trim() || signing}
                  >
                    签名
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      try {
                        window.open('/onboarding', '_blank', 'noopener,noreferrer');
                      } catch {
                        // ignore
                      }
                    }}
                  >
                    生成密钥
                  </Button>
                </div>
              </div>
            )}
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
                <Button variant="ghost" size="sm" onClick={() => { try { window.open('/onboarding', '_blank', 'noopener,noreferrer'); } catch {} }}>
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
