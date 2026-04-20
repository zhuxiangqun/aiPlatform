import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Copy, PackagePlus, RotateCw, Trash2, UploadCloud, Tag, Info } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import PageHeader from '../../../components/common/PageHeader';
import { Button, Input, Modal, Table, Textarea, toast, Select } from '../../../components/ui';
import { skillPackApi, type SkillPack, type SkillPackInstall, type SkillPackVersion } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const SkillPacks: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation() as any;
  const [loading, setLoading] = useState(false);
  const [packs, setPacks] = useState<SkillPack[]>([]);
  const [limit] = useState(100);
  const [offset] = useState(0);

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [installOpen, setInstallOpen] = useState(false);
  const [installsOpen, setInstallsOpen] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);

  const [current, setCurrent] = useState<SkillPack | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [manifestText, setManifestText] = useState('{\n  "skills": []\n}');

  const [publishVersion, setPublishVersion] = useState('0.1.0');
  const [installScope, setInstallScope] = useState<'workspace' | 'engine'>('workspace');
  const [installVersion, setInstallVersion] = useState<string>('');
  const [installResult, setInstallResult] = useState<{ install: SkillPackInstall; applied: any[] } | null>(null);

  const [versions, setVersions] = useState<SkillPackVersion[]>([]);
  const [installs, setInstalls] = useState<SkillPackInstall[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await skillPackApi.list({ limit, offset });
      setPacks(res.items || []);
    } catch (e: any) {
      toast.error('加载 Skill Packs 失败', String(e?.message || ''));
      setPacks([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Support cross-page deep link: /core/skill-packs with state { openPackId }
  useEffect(() => {
    const openPackId = location?.state?.openPackId;
    if (!openPackId) return;
    (async () => {
      try {
        const p = await skillPackApi.get(String(openPackId));
        setCurrent(p);
        setDetailOpen(true);
      } catch (e: any) {
        toast.error('打开 Skill Pack 失败', String(e?.message || ''));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location?.key]);

  const resetForm = (pack?: SkillPack | null) => {
    setName(pack?.name || '');
    setDescription(String(pack?.description || ''));
    setManifestText(JSON.stringify(pack?.manifest || { skills: [] }, null, 2));
  };

  const parseManifest = () => {
    try {
      const obj = JSON.parse(manifestText || '{}');
      return obj && typeof obj === 'object' ? obj : {};
    } catch (e: any) {
      throw new Error(`manifest 不是合法 JSON：${e?.message || ''}`);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('已复制');
    } catch {
      toast.error('复制失败');
    }
  };

  const openCreate = () => {
    setCurrent(null);
    resetForm(null);
    setCreateOpen(true);
  };

  const openEdit = (pack: SkillPack) => {
    setCurrent(pack);
    resetForm(pack);
    setEditOpen(true);
  };

  const openDetail = (pack: SkillPack) => {
    setCurrent(pack);
    setDetailOpen(true);
  };

  const doCreate = async () => {
    try {
      const manifest = parseManifest();
      await skillPackApi.create({ name, description, manifest });
      toast.success('已创建');
      setCreateOpen(false);
      await load();
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    }
  };

  const doUpdate = async () => {
    if (!current) return;
    try {
      const manifest = parseManifest();
      await skillPackApi.update(current.id, { name, description, manifest });
      toast.success('已更新');
      setEditOpen(false);
      await load();
    } catch (e: any) {
      toast.error('更新失败', String(e?.message || ''));
    }
  };

  const doDelete = async (pack: SkillPack) => {
    try {
      await skillPackApi.delete(pack.id);
      toast.success('已删除');
      await load();
    } catch (e: any) {
      toast.error('删除失败', String(e?.message || ''));
    }
  };

  const doPublish = async () => {
    if (!current) return;
    try {
      const v = await skillPackApi.publish(current.id, publishVersion);
      toast.success(`已发布版本 ${v.version}`);
      setPublishOpen(false);
    } catch (e: any) {
      toastGateError(e, '发布失败');
    }
  };

  const doInstall = async () => {
    if (!current) return;
    try {
      const res = await skillPackApi.install(current.id, {
        version: installVersion || undefined,
        scope: installScope,
        metadata: {},
      });
      setInstallResult(res);
      toast.success('安装请求已提交');
    } catch (e: any) {
      toastGateError(e, '安装失败');
    }
  };

  const jumpToWorkspaceSkills = () => {
    const ids = (installResult?.applied || [])
      .map((x: any) => String(x?.skill_id || '').trim())
      .filter((x: string) => Boolean(x));
    if (!ids.length) {
      toast.error('没有可跳转的 skill_id');
      return;
    }
    navigate('/workspace/skills', { state: { filterSkillIds: ids } });
    setInstallOpen(false);
  };

  const openVersions = async (pack: SkillPack) => {
    setCurrent(pack);
    setVersionsOpen(true);
    try {
      const res = await skillPackApi.listVersions(pack.id, { limit: 100, offset: 0 });
      setVersions(res.items || []);
    } catch {
      setVersions([]);
    }
  };

  const openInstalls = async () => {
    setInstallsOpen(true);
    try {
      const res = await skillPackApi.listInstalls({ scope: undefined, limit: 100, offset: 0 });
      setInstalls(res.items || []);
    } catch {
      setInstalls([]);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: '名称',
        key: 'name',
        render: (_: unknown, r: SkillPack) => (
          <button className="font-medium text-gray-100 text-left hover:underline" onClick={() => openDetail(r)} title="查看详情">
            {r.name}
          </button>
        ),
      },
      {
        title: 'skills',
        key: 'skills',
        width: 120,
        align: 'center' as const,
        render: (_: unknown, r: SkillPack) => {
          const n = Array.isArray((r.manifest as any)?.skills) ? (r.manifest as any).skills.length : 0;
          return <span className="text-gray-400">{n}</span>;
        },
      },
      {
        title: 'ID',
        key: 'id',
        width: 140,
        render: (_: unknown, r: SkillPack) => (
          <div className="flex items-center gap-2">
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{r.id}</code>
            <button className="text-gray-500 hover:text-gray-200" onClick={() => copyText(r.id)} title="复制">
              <Copy className="w-4 h-4" />
            </button>
          </div>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 220,
        align: 'center' as const,
        render: (_: unknown, r: SkillPack) => (
          <div className="flex items-center justify-center gap-1">
            <button
              onClick={() => openDetail(r)}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="详情"
            >
              <Info className="w-4 h-4" />
            </button>
            <button
              onClick={() => openEdit(r)}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="编辑"
            >
              <PackagePlus className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                setCurrent(r);
                setPublishOpen(true);
              }}
              className="p-1.5 rounded-lg text-amber-300 hover:bg-dark-hover transition-colors"
              title="发布版本"
            >
              <Tag className="w-4 h-4" />
            </button>
            <button
              onClick={() => openVersions(r)}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="版本列表"
            >
              <Tag className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                setCurrent(r);
                setInstallResult(null);
                setInstallOpen(true);
              }}
              className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors"
              title="安装并生效"
            >
              <UploadCloud className="w-4 h-4" />
            </button>
            <button
              onClick={() => doDelete(r)}
              className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
              title="删除"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ),
      },
    ],
    [copyText],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Skill Packs"
        description="管理 Skill Pack（创建 / 发布版本 / 安装并生效）"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<RotateCw className="w-4 h-4" />} onClick={load} loading={loading}>
              刷新
            </Button>
            <Button onClick={openInstalls}>安装记录</Button>
            <Button variant="primary" icon={<PackagePlus className="w-4 h-4" />} onClick={openCreate}>
              创建
            </Button>
          </div>
        }
      />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={packs} rowKey="id" loading={loading} emptyText="暂无 Skill Pack" />
      </motion.div>

      {/* Create */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="创建 Skill Pack"
        width={900}
        footer={
          <>
            <Button onClick={() => setCreateOpen(false)}>取消</Button>
            <Button variant="primary" onClick={doCreate}>
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="name" value={name} onChange={(e: any) => setName(e.target.value)} />
          <Input label="description" value={description} onChange={(e: any) => setDescription(e.target.value)} />
          <Textarea label="manifest（JSON）" rows={12} value={manifestText} onChange={(e: any) => setManifestText(e.target.value)} />
        </div>
      </Modal>

      {/* Edit */}
      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={`编辑 Skill Pack：${current?.name || ''}`}
        width={900}
        footer={
          <>
            <Button onClick={() => setEditOpen(false)}>取消</Button>
            <Button variant="primary" onClick={doUpdate}>
              保存
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="name" value={name} onChange={(e: any) => setName(e.target.value)} />
          <Input label="description" value={description} onChange={(e: any) => setDescription(e.target.value)} />
          <Textarea label="manifest（JSON）" rows={12} value={manifestText} onChange={(e: any) => setManifestText(e.target.value)} />
        </div>
      </Modal>

      {/* Detail */}
      <Modal open={detailOpen} onClose={() => setDetailOpen(false)} title={`Skill Pack：${current?.name || ''}`} width={900} footer={<Button onClick={() => setDetailOpen(false)}>关闭</Button>}>
        <div className="space-y-3 text-sm text-gray-300">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">id</div>
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(current?.id || '-')}</code>
                {current?.id && (
                  <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(current?.id || ''))}>
                    复制
                  </Button>
                )}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">name</div>
              <div>{current?.name || '-'}</div>
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">description</div>
            <div className="text-gray-400">{String(current?.description || '-')}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">manifest</div>
            <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-96">{JSON.stringify(current?.manifest || {}, null, 2)}</pre>
          </div>
        </div>
      </Modal>

      {/* Publish */}
      <Modal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        title={`发布版本：${current?.name || ''}`}
        footer={
          <>
            <Button onClick={() => setPublishOpen(false)}>取消</Button>
            <Button variant="primary" onClick={doPublish}>
              发布
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="version（例如 0.1.0）" value={publishVersion} onChange={(e: any) => setPublishVersion(e.target.value)} />
          <div className="text-xs text-gray-500">发布会固化当前 manifest 为该版本快照（pack_id + version 唯一）</div>
        </div>
      </Modal>

      {/* Versions */}
      <Modal open={versionsOpen} onClose={() => setVersionsOpen(false)} title={`版本列表：${current?.name || ''}`} width={900} footer={<Button onClick={() => setVersionsOpen(false)}>关闭</Button>}>
        <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
          <Table
            columns={[
              { title: 'version', key: 'version', render: (_: unknown, r: SkillPackVersion) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{r.version}</code> },
              { title: 'created_at', key: 'created_at', render: (_: unknown, r: SkillPackVersion) => <span className="text-gray-400">{r.created_at ?? '-'}</span> },
              { title: 'id', key: 'id', render: (_: unknown, r: SkillPackVersion) => <span className="text-gray-400">{r.id}</span> },
            ]}
            data={versions}
            rowKey="id"
            loading={false}
            emptyText="暂无版本"
          />
        </div>
      </Modal>

      {/* Install */}
      <Modal
        open={installOpen}
        onClose={() => { setInstallOpen(false); setInstallResult(null); }}
        title={`安装并生效：${current?.name || ''}`}
        width={900}
        footer={
          <>
            <Button onClick={() => { setInstallOpen(false); setInstallResult(null); }}>关闭</Button>
            <Button variant="primary" onClick={doInstall}>
              安装
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            value={installScope}
            onChange={(v) => setInstallScope((v as any) || 'workspace')}
            options={[
              { value: 'workspace', label: 'workspace（推荐）' },
              { value: 'engine', label: 'engine' },
            ]}
            placeholder="scope"
          />
          <Input label="version（可选；为空则使用当前 pack manifest）" value={installVersion} onChange={(e: any) => setInstallVersion(e.target.value)} />
          {installResult && (
            <div className="space-y-2">
              <div className="text-sm text-gray-200">applied</div>
              <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-60">{JSON.stringify(installResult.applied || [], null, 2)}</pre>
              <div className="flex items-center justify-end gap-2">
                <Button
                  onClick={() => copyText((installResult.applied || []).map((x: any) => x?.skill_id).filter(Boolean).join(','))}
                >
                  复制 skill_ids
                </Button>
                <Button variant="primary" onClick={jumpToWorkspaceSkills}>
                  打开应用库 Skill
                </Button>
              </div>
            </div>
          )}
          <div className="text-xs text-gray-500">
            workspace 安装会将 manifest.skills materialize 成目录化 skill（写入 SKILL.md），并 enable/restore。
          </div>
        </div>
      </Modal>

      {/* Installs */}
      <Modal open={installsOpen} onClose={() => setInstallsOpen(false)} title="安装记录" width={900} footer={<Button onClick={() => setInstallsOpen(false)}>关闭</Button>}>
        <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
          <Table
            columns={[
              { title: 'pack_id', key: 'pack_id', render: (_: unknown, r: SkillPackInstall) => <span className="text-gray-300">{r.pack_id}</span> },
              { title: 'version', key: 'version', width: 120, render: (_: unknown, r: SkillPackInstall) => <span className="text-gray-400">{r.version || '-'}</span> },
              { title: 'scope', key: 'scope', width: 120, render: (_: unknown, r: SkillPackInstall) => <span className="text-gray-400">{r.scope}</span> },
              { title: 'installed_at', key: 'installed_at', width: 140, render: (_: unknown, r: SkillPackInstall) => <span className="text-gray-400">{r.installed_at ?? '-'}</span> },
            ]}
            data={installs}
            rowKey="id"
            loading={false}
            emptyText="暂无安装记录"
          />
        </div>
      </Modal>
    </div>
  );
};

export default SkillPacks;
