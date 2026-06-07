import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Input, Modal, Select, Switch, Table, Tabs, Textarea, toast } from '../../../components/ui';
import { workspaceSkillApi, workspaceSkillInstallerApi, type WorkspaceSkillInstallerPlan, SKILL_CATEGORIES } from '../../../services';
import { toastGateError } from '../../../components/ui';

type SourceType = 'git' | 'path' | 'zip';

const SOURCE_OPTIONS = [
  { value: 'git', label: 'Git 仓库（url + ref）' },
  { value: 'path', label: '本地目录（服务器路径）' },
  { value: 'zip', label: '本地 Zip（服务器路径）' },
];

const SkillMarketplace: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'browse' | 'import' | 'installed'>('browse');
  // Catalog state
  const [catalog, setCatalog] = useState<any[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogCategory, setCatalogCategory] = useState('');
  const [catalogQuery, setCatalogQuery] = useState('');
  // Import state
  const [sourceType, setSourceType] = useState<SourceType>('git');
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('');
  const [path, setPath] = useState('');
  const [subdir, setSubdir] = useState('');
  const [autoDetect, setAutoDetect] = useState(true);
  const [allowOverwrite, setAllowOverwrite] = useState(false);
  const [skillId, setSkillId] = useState('');
  const [metadataJson, setMetadataJson] = useState('{"source":"opensource"}');

  const [confirm, setConfirm] = useState(false);
  const [requireApproval, setRequireApproval] = useState(false);
  const [approvalRequestId, setApprovalRequestId] = useState('');
  const [details, setDetails] = useState('install open-source skills');

  const [planning, setPlanning] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [plan, setPlan] = useState<WorkspaceSkillInstallerPlan | null>(null);

  const [installedSkills, setInstalledSkills] = useState<any[]>([]);
  const [loadingInstalled, setLoadingInstalled] = useState(false);
  const [installedLoadedOnce, setInstalledLoadedOnce] = useState(false);
  const [updateModal, setUpdateModal] = useState<{ open: boolean; skillId: string; ref: string }>({ open: false, skillId: '', ref: '' });

  // Zip upload mode
  const [zipUploadMode, setZipUploadMode] = useState<'server' | 'upload'>('upload');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const metaObj = useMemo(() => {
    try {
      const o = JSON.parse(metadataJson || '{}');
      return typeof o === 'object' && o ? (o as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }, [metadataJson]);

  const loadInstalled = async () => {
    setLoadingInstalled(true);
    try {
      const res: any = await workspaceSkillApi.list({ limit: 200, offset: 0 });
      setInstalledSkills((res as any)?.skills || []);
    } catch (e: any) {
      toastGateError(e, '获取已安装 Skill 失败');
    } finally {
      setLoadingInstalled(false);
    }
  };

  // Load catalog when browse tab is active
  const loadCatalog = async () => {
    setCatalogLoading(true);
    try {
      const params: any = {};
      if (catalogCategory) params.category = catalogCategory;
      if (catalogQuery.trim()) params.query = catalogQuery.trim();
      const res = await workspaceSkillInstallerApi.catalog(params);
      setCatalog((res as any).catalog || []);
    } catch (e) {
      setCatalog([]);
    } finally {
      setCatalogLoading(false);
    }
  };

  // Auto-install from browse: fill form → switch to import → auto-plan
  const onBrowseInstall = async (item: any) => {
    setUrl(item.url || '');
    setSourceType('git');
    setActiveTab('import');
    // Trigger plan after form state settles
    setTimeout(async () => {
      try {
        setPlanning(true);
        const headRes = await workspaceSkillInstallerApi.resolveHead(item.url);
        const latestRef = (headRes as any).head_sha || '';
        if (latestRef) setRef(latestRef);
        const planRes = await workspaceSkillInstallerApi.plan({
          source_type: 'git',
          url: item.url,
          ref: latestRef || undefined,
          auto_detect_subdir: true,
        });
        setPlan(planRes);
      } catch (e) {
        toastGateError(e, '生成安装计划失败');
      } finally {
        setPlanning(false);
      }
    }, 200);
  };

  useEffect(() => {
    if (activeTab === 'browse') loadCatalog();
  }, [activeTab === 'browse' ? catalogCategory + '|' + catalogQuery : null, activeTab === 'browse']);

  useEffect(() => {
    // Lazy load installed list only when user opens "已安装"
    if (activeTab !== 'installed') return;
    if (installedLoadedOnce) return;
    loadInstalled().finally(() => setInstalledLoadedOnce(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const buildInstallerPayload = () => {
    const payload: any = {
      source_type: sourceType,
      auto_detect_subdir: autoDetect,
      allow_overwrite: allowOverwrite,
      metadata: metaObj,
    };
    if (skillId.trim()) payload.skill_id = skillId.trim();
    if (subdir.trim()) payload.subdir = subdir.trim();

    if (sourceType === 'git') {
      payload.url = url.trim();
      payload.ref = ref.trim();
    } else {
      payload.path = path.trim();
    }
    return payload;
  };

  const onPlan = async () => {
    setPlanning(true);
    try {
      // Use upload API when zip file is selected
      if (sourceType === 'zip' && zipFile) {
        const res: any = await workspaceSkillInstallerApi.uploadPlan(zipFile, {
          subdir: subdir.trim() || undefined,
          skill_id: skillId.trim() || undefined,
          auto_detect_subdir: autoDetect,
        });
        setPlan(res as any);
        toast.success('已生成安装计划');
      } else {
        const payload = buildInstallerPayload();
        const res: any = await workspaceSkillInstallerApi.plan(payload);
        setPlan(res as any);
        toast.success('已生成安装计划');
      }
    } catch (e: any) {
      toastGateError(e, '生成计划失败');
    } finally {
      setPlanning(false);
    }
  };

  const onInstall = async () => {
    setInstalling(true);
    try {
      // Use upload API when zip file is selected
      if (sourceType === 'zip' && zipFile) {
        const res: any = await workspaceSkillInstallerApi.uploadInstall(zipFile, {
          subdir: subdir.trim() || undefined,
          skill_id: skillId.trim() || undefined,
          auto_detect_subdir: autoDetect,
          allow_overwrite: allowOverwrite,
          plan_id: plan?.plan_id,
        });
        toast.success(`安装完成：${(res?.installed || []).length} 个`);
        setPlan(null); setConfirm(false);
        await loadInstalled();
      } else {
        const payload: any = buildInstallerPayload();
      payload.confirm = confirm;
      payload.require_approval = requireApproval;
      payload.approval_request_id = approvalRequestId.trim() || undefined;
      payload.details = details;
      // if we already have plan_id from plan, include it
      if (plan?.plan_id) payload.plan_id = plan.plan_id;

      const res: any = await workspaceSkillInstallerApi.install(payload);
      toast.success(`安装完成：${(res?.installed || []).length} 个`);
      setPlan(null);
      setConfirm(false);
      await loadInstalled();
      }
    } catch (e: any) {
      // Try to surface plan/approval guidance if server returns structured detail
      try {
        const detail = (e as any)?.response?.data?.detail ?? (e as any)?.response?.data;
        if (detail?.code === 'confirm_required' && detail?.plan) {
          setPlan(detail.plan);
          toast.error('需要确认后再安装（请勾选 confirm）');
          setInstalling(false);
          return;
        }
        if (detail?.code === 'plan_id_required' && detail?.plan) {
          setPlan(detail.plan);
          toast.error('需要先获取 plan_id（请先点“预览计划”）');
          setInstalling(false);
          return;
        }
        if (detail?.code === 'approval_required' && detail?.approval_request_id) {
          setApprovalRequestId(String(detail.approval_request_id));
          toast.error(`需要审批：${detail.approval_request_id}`);
          try {
            window.open('/core/approvals', '_blank', 'noopener,noreferrer');
          } catch {
            // ignore
          }
          setInstalling(false);
          return;
        }
      } catch {
        // ignore
      }
      toastGateError(e, '安装失败');
    } finally {
      setInstalling(false);
    }
  };

  const planColumns = [
    { key: 'skill_id', title: '目录ID', dataIndex: 'skill_id' },
    { key: 'name', title: '名称', dataIndex: 'name' },
    { key: 'kind', title: '类型', dataIndex: 'kind', width: 110, render: (v: string) => <Badge variant={'default' as any}>{v || '-'}</Badge> },
    { key: 'version', title: '版本', dataIndex: 'version', width: 120 },
    {
      key: 'limits',
      title: '限制检查',
      width: 120,
      render: (_: unknown, r: any) => (r?.limits_ok ? <Badge variant={'success' as any}>ok</Badge> : <Badge variant={'error' as any}>fail</Badge>),
    },
    {
      key: 'permissions',
      title: '权限声明',
      render: (_: unknown, r: any) => <span className="text-xs text-gray-400">{Array.isArray(r?.permissions) ? r.permissions.join(', ') : '-'}</span>,
    },
  ];

  const installedColumns = [
    { key: 'name', title: '名称', dataIndex: 'name' },
    { key: 'description', title: '描述', dataIndex: 'description', render: (v: string) => <span className="text-gray-500">{v || '-'}</span> },
    {
      key: 'status',
      title: '状态',
      width: 120,
      render: (_: unknown, r: any) => <Badge variant={(r?.enabled ? 'success' : 'warning') as any}>{r?.enabled ? 'enabled' : 'disabled'}</Badge>,
    },
    {
      key: 'actions',
      title: '操作',
      width: 220,
      render: (_: unknown, r: any) => (
        <div className="flex items-center gap-2 justify-end">
          <Button size="sm" variant="secondary" onClick={() => setUpdateModal({ open: true, skillId: String(r.id), ref: '' })}>
            更新
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={async () => {
              try {
                await workspaceSkillInstallerApi.uninstall(String(r.id), { delete_files: true });
                toast.success('已卸载');
                await loadInstalled();
              } catch (e: any) {
                toastGateError(e, '卸载失败');
              }
            }}
          >
            卸载
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-200">Skill Marketplace / Installer</h1>
        <p className="text-sm text-gray-500 mt-1">从 Git/Zip/本地路径导入开源技能（支持 plan → plan_id → install 的强约束流程）。</p>
      </div>

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div className="text-gray-300 font-medium md:col-span-2 border-b border-dark-border pb-1 mb-0.5">安装预览（浏览/导入 tab）</div>
          <div><span className="text-gray-300">目录ID</span><span className="ml-2 text-gray-600">Skill 的 skill_id 目录名</span></div>
          <div><span className="text-gray-300">名称</span><span className="ml-2 text-gray-600">SKILL.md 的 display_name</span></div>
          <div><span className="text-gray-300">类型</span><span className="ml-2 text-gray-600">Skill 的类型标签</span></div>
          <div><span className="text-gray-300">版本</span><span className="ml-2 text-gray-600">semver 版本号，用于更新/回滚判断</span></div>
          <div><span className="text-gray-300">限制检查</span><span className="ml-2 text-gray-600"><span className="text-green-400">ok</span> 通过，<span className="text-red-400">fail</span> 存在冲突或限制</span></div>
          <div><span className="text-gray-300">权限声明</span><span className="ml-2 text-gray-600">Skill 声明的权限列表</span></div>
          <div className="text-gray-300 font-medium md:col-span-2 border-b border-dark-border pb-1 mb-0.5 mt-1">已安装</div>
          <div><span className="text-gray-300">名称</span><span className="ml-2 text-gray-600">已安装 Skill 的显示名</span></div>
          <div><span className="text-gray-300">描述</span><span className="ml-2 text-gray-600">SKILL.md 的 description</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600"><span className="text-green-400">enabled</span> 已启用 · <span className="text-yellow-400">disabled</span> 已禁用</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">更新到最新版本 / 卸载此 Skill</span></div>
        </div>
      </details>

      <Tabs
        defaultActiveKey="browse"
        onChange={(k) => setActiveTab((k as any) === 'import' ? 'import' : (k as any) === 'installed' ? 'installed' : 'browse')}
        tabs={[
          {
            key: 'browse',
            label: '浏览',
            children: (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <Input
                    placeholder="搜索 Skill..."
                    value={catalogQuery}
                    onChange={(v: any) => setCatalogQuery(v?.target?.value || v || '')}
                    style={{ maxWidth: 300 }}
                  />
                  <Select
                    value={catalogCategory}
                    onChange={(v: any) => setCatalogCategory(v || '')}
                    options={[
                      { value: '', label: '全部分类' },
                      ...(SKILL_CATEGORIES || []).map((c: any) => ({ value: c, label: c })),
                    ]}
                  />
                  <Button variant="secondary" loading={catalogLoading} onClick={loadCatalog}>刷新</Button>
                </div>
                {catalogLoading ? (
                  <p className="text-sm text-gray-500">加载目录中...</p>
                ) : catalog.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    目录为空。将 Skill 条目添加到 ~/.aiplat/skills/catalog.yaml 即可在此浏览。
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {catalog.map((item: any, idx: number) => (
                      <div key={idx} className="bg-dark-card border border-dark-border rounded-xl p-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-gray-100">{item.name}</span>
                          {item.installed && <Badge variant="success">已安装</Badge>}
                        </div>
                        <p className="text-xs text-gray-400">{item.description}</p>
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <Badge variant="default">{item.category}</Badge>
                          {item.official && <Badge variant="info">官方</Badge>}
                          {(item.tags || []).slice(0, 3).map((t: string, ti: number) => (
                            <span key={ti} className="text-gray-600">{t}</span>
                          ))}
                        </div>
                        <Button
                          size="sm"
                          disabled={item.installed}
                          onClick={() => onBrowseInstall(item)}
                        >
                          {item.installed ? '已安装' : '一键安装'}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ),
          },
          {
            key: 'import',
            label: '导入',
            children: (
              <div className="bg-dark-card border border-dark-border rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-200">导入开源技能</div>
                  <div className="flex items-center gap-2">
                    <Button variant="secondary" loading={planning} onClick={onPlan}>
                      预览计划
                    </Button>
                    <Button loading={installing} onClick={onInstall}>
                      安装
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Select label="来源类型" value={sourceType} onChange={(v) => setSourceType(v as SourceType)} options={SOURCE_OPTIONS} />

                  {sourceType === 'git' ? (
                    <>
                      <Input label="Git URL" placeholder="https://github.com/owner/repo.git" value={url} onChange={(e) => setUrl(e.target.value)} />
                      <div className="flex items-end gap-2">
                        <div className="flex-1">
                          <Input label="Ref（tag/commit，必填）" placeholder="v1.2.3 或 commit sha" value={ref} onChange={(e) => setRef(e.target.value)} />
                        </div>
                        <Button
                          variant="secondary"
                          onClick={async () => {
                            const u = url.trim();
                            if (!u) {
                              toast.error('请先填写 Git URL');
                              return;
                            }
                            try {
                              const res: any = await workspaceSkillInstallerApi.resolveHead(u);
                              const sha = (res as any)?.head_sha || (res as any)?.headSha;
                              if (sha) {
                                setRef(String(sha));
                                toast.success('已填入最新 HEAD sha');
                              } else {
                                toast.error('未获取到 head_sha');
                              }
                            } catch (e: any) {
                              toastGateError(e, '获取 HEAD sha 失败');
                            }
                          }}
                        >
                          获取最新 HEAD
                        </Button>
                      </div>
                    </>
                  ) : sourceType === 'zip' ? (
                    <>
                      <div className="flex items-center gap-2">
                        <button onClick={() => { setZipUploadMode('upload'); setPath(''); setZipFile(null); }}
                          className={`text-xs px-3 py-1.5 rounded ${zipUploadMode === 'upload' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>
                          本地上传
                        </button>
                        <button onClick={() => { setZipUploadMode('server'); setZipFile(null); }}
                          className={`text-xs px-3 py-1.5 rounded ${zipUploadMode === 'server' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>
                          服务器路径
                        </button>
                      </div>
                      {zipUploadMode === 'upload' ? (
                        <>
                          <input ref={fileInputRef} type="file" accept=".zip" className="hidden"
                            onChange={(e) => { const f = e.target.files?.[0]; if (f) { setZipFile(f); setPath(f.name); } }} />
                          <div onClick={() => fileInputRef.current?.click()}
                            className="border-2 border-dashed border-dark-border rounded-xl p-6 text-center cursor-pointer hover:border-primary/50 transition-colors">
                            {zipFile ? (
                              <div>
                                <div className="text-lg mb-1">📦</div>
                                <div className="text-sm text-gray-200">{zipFile.name}</div>
                                <div className="text-xs text-gray-500 mt-1">{(zipFile.size / 1024).toFixed(0)} KB · 点击更换</div>
                              </div>
                            ) : (
                              <div>
                                <div className="text-lg mb-1">📤</div>
                                <div className="text-sm text-gray-300">点击选择 .zip 文件或拖拽到此处</div>
                                <div className="text-xs text-gray-500 mt-1">自动探测子目录并提取 SKILL.md</div>
                              </div>
                            )}
                          </div>
                        </>
                      ) : (
                        <Input label="服务器本地路径" placeholder="/var/tmp/skills.zip" value={path} onChange={(e) => setPath(e.target.value)} />
                      )}
                    </>
                  ) : (
                    <Input label="服务器本地路径" placeholder="/var/tmp/skills_bundle 或 /var/tmp/skills.zip" value={path} onChange={(e) => setPath(e.target.value)} />
                  )}

                  <Input label="subdir（可选）" placeholder="例如 .opencode/skills 或 skills（留空可自动探测）" value={subdir} onChange={(e) => setSubdir(e.target.value)} />
                  <Input label="skill_id（可选，仅导入一个）" placeholder="目录名或 SKILL.md frontmatter name" value={skillId} onChange={(e) => setSkillId(e.target.value)} />

                  <Textarea label="metadata（JSON，可选）" rows={4} value={metadataJson} onChange={(e) => setMetadataJson(e.target.value)} />
                  <Textarea label="审批/审计详情（可选）" rows={4} value={details} onChange={(e) => setDetails(e.target.value)} />

                  <div className="flex items-center justify-between bg-dark-bg border border-dark-border rounded-lg px-3 py-2">
                    <div className="text-sm text-gray-300">自动探测 subdir</div>
                    <Switch checked={autoDetect} onChange={() => setAutoDetect(!autoDetect)} />
                  </div>
                  <div className="flex items-center justify-between bg-dark-bg border border-dark-border rounded-lg px-3 py-2">
                    <div className="text-sm text-gray-300">允许覆盖（overwrite）</div>
                    <Switch checked={allowOverwrite} onChange={() => setAllowOverwrite(!allowOverwrite)} />
                  </div>

                  <div className="flex items-center justify-between bg-dark-bg border border-dark-border rounded-lg px-3 py-2">
                    <div className="text-sm text-gray-300">confirm（确认落盘）</div>
                    <Switch checked={confirm} onChange={() => setConfirm(!confirm)} />
                  </div>
                  <div className="flex items-center justify-between bg-dark-bg border border-dark-border rounded-lg px-3 py-2">
                    <div className="text-sm text-gray-300">require_approval（安装需审批）</div>
                    <Switch checked={requireApproval} onChange={() => setRequireApproval(!requireApproval)} />
                  </div>

                  <Input label="approval_request_id（可选）" placeholder="若已审批通过，填入该 id 再点安装" value={approvalRequestId} onChange={(e) => setApprovalRequestId(e.target.value)} />
                </div>

                {plan && (
                  <div className="mt-4 space-y-3">
                    <div className="text-sm font-medium text-gray-200">安装计划</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                      <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
                        <div className="text-gray-500">detected_subdir</div>
                        <div className="text-gray-200 mt-1">{(plan as any)?.detected_subdir || '-'}</div>
                      </div>
                      <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
                        <div className="text-gray-500">planned_skills_digest</div>
                        <div className="text-gray-200 mt-1 font-mono text-xs break-all">{(plan as any)?.planned_skills_digest || '-'}</div>
                      </div>
                      <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
                        <div className="text-gray-500">plan_id</div>
                        <div className="text-gray-200 mt-1 font-mono text-xs break-all">{(plan as any)?.plan_id || '(未配置 secret，未签发 plan_id)'}</div>
                      </div>
                      <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
                        <div className="text-gray-500">plan_expires_at</div>
                        <div className="text-gray-200 mt-1">{(plan as any)?.plan_expires_at ? new Date(((plan as any).plan_expires_at as number) * 1000).toLocaleString() : '-'}</div>
                      </div>
                    </div>

                    {Array.isArray((plan as any)?.warnings) && (plan as any).warnings.length > 0 && (
                      <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
                        <div className="text-gray-500 text-sm mb-1">warnings</div>
                        <ul className="text-sm text-gray-300 list-disc pl-5">
                          {(plan as any).warnings.map((w: string, idx: number) => (
                            <li key={idx}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <Table columns={planColumns as any} data={(plan as any)?.skills || []} rowKey={(r: any) => String(r.skill_id)} />
                  </div>
                )}
              </div>
            ),
          },
          {
            key: 'installed',
            label: '已安装',
            children: (
              <div className="bg-dark-card border border-dark-border rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-200">已安装 Skill</div>
                  <div className="flex items-center gap-2">
                    <Button variant="secondary" onClick={() => navigate('/workspace/skills')}>
                      打开 Skill库
                    </Button>
                    <Button variant="secondary" onClick={loadInstalled} loading={loadingInstalled}>
                      刷新
                    </Button>
                  </div>
                </div>
                <Table columns={installedColumns as any} data={installedSkills} rowKey={(r: any) => String(r.id)} loading={loadingInstalled} />
              </div>
            ),
          },
        ]}
      />

      <Modal open={updateModal.open} onClose={() => setUpdateModal({ open: false, skillId: '', ref: '' })} title="更新 Skill（从来源）">
        <div className="space-y-4">
          <Input label="skill_id" value={updateModal.skillId} disabled />
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                label="新 ref（可选）"
                placeholder="留空则使用 manifest 中的 ref"
                value={updateModal.ref}
                onChange={(e) => setUpdateModal({ ...updateModal, ref: e.target.value })}
              />
            </div>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  // best-effort: resolve HEAD from provenance (manifest) is not exposed;
                  // so we ask user to keep the Git URL in metadata or fill it in install form.
                  // For now, reuse the current Git URL input as the source of truth.
                  const u = url.trim();
                  if (!u) {
                    toast.error('请先在“导入开源技能”区域填写 Git URL（用于解析 HEAD）');
                    return;
                  }
                  const res: any = await workspaceSkillInstallerApi.resolveHead(u);
                  const sha = (res as any)?.head_sha || (res as any)?.headSha;
                  if (sha) {
                    setUpdateModal({ ...updateModal, ref: String(sha) });
                    toast.success('已填入最新 HEAD sha');
                  } else {
                    toast.error('未获取到 head_sha');
                  }
                } catch (e: any) {
                  toastGateError(e, '获取 HEAD sha 失败');
                }
              }}
            >
              获取最新 HEAD
            </Button>
          </div>
          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" onClick={() => setUpdateModal({ open: false, skillId: '', ref: '' })}>
              取消
            </Button>
            <Button
              onClick={async () => {
                try {
                  await workspaceSkillInstallerApi.update(updateModal.skillId, { ref: updateModal.ref.trim() || undefined });
                  toast.success('已触发更新');
                  setUpdateModal({ open: false, skillId: '', ref: '' });
                  await loadInstalled();
                } catch (e: any) {
                  toastGateError(e, '更新失败（可能没有 SKILL.manifest.json）');
                }
              }}
            >
              更新
            </Button>
            <Button
              onClick={async () => {
                const u = url.trim();
                if (!u) {
                  toast.error('请先在“导入开源技能”区域填写 Git URL（用于解析 HEAD）');
                  return;
                }
                try {
                  const res: any = await workspaceSkillInstallerApi.resolveHead(u);
                  const sha = (res as any)?.head_sha || (res as any)?.headSha;
                  if (!sha) {
                    toast.error('未获取到 head_sha');
                    return;
                  }
                  await workspaceSkillInstallerApi.update(updateModal.skillId, { ref: String(sha) });
                  toast.success('已更新到最新 HEAD');
                  setUpdateModal({ open: false, skillId: '', ref: '' });
                  await loadInstalled();
                } catch (e: any) {
                  toastGateError(e, '一键更新失败');
                }
              }}
            >
              一键更新到最新
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default SkillMarketplace;
