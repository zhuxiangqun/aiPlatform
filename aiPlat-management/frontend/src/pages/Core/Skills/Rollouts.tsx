import React, { useEffect, useMemo, useState } from 'react';
import { Badge, Button, Card, Input, Modal, Select, Table, Textarea, toast } from '../../../components/ui';
import { workspaceSkillApi } from '../../../services/coreApi';

type AssetType = 'skill_spec_v2_schema' | 'permissions_catalog';

const assetOptions = [
  { value: 'skill_spec_v2_schema', label: 'SkillSpec v2 Schema' },
  { value: 'permissions_catalog', label: 'Permissions Catalog' },
];

const scopeOptions = [
  { value: 'workspace', label: 'workspace（应用库）' },
  { value: 'engine', label: 'engine（引擎）' },
];

const channelOptions = [
  { value: 'stable', label: 'stable（稳定）' },
  { value: 'canary', label: 'canary（灰度）' },
];

const fmtTs = (t?: number) => {
  if (!t) return '-';
  try {
    return new Date(t * 1000).toLocaleString();
  } catch {
    return String(t);
  }
};

const Rollouts: React.FC = () => {
  const [tenantId, setTenantId] = useState(() => localStorage.getItem('active_tenant_id') || 'default');
  const [activeChannel, setActiveChannel] = useState(() => localStorage.getItem('active_release_channel') || 'stable');
  const [assetType, setAssetType] = useState<AssetType>('skill_spec_v2_schema');
  const [scope, setScope] = useState<'workspace' | 'engine'>('workspace');
  const [channel, setChannel] = useState<'stable' | 'canary'>('stable');

  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<any>(null);
  const [versions, setVersions] = useState<any[]>([]);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewVersion, setPreviewVersion] = useState<string>('');
  const [previewPayload, setPreviewPayload] = useState<any>(null);
  const [note, setNote] = useState('');
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffInfo, setDiffInfo] = useState<any>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [confirmExpected, setConfirmExpected] = useState<string>('');
  const [pendingPublish, setPendingPublish] = useState<{ version: string } | null>(null);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approvalRequestId, setApprovalRequestId] = useState<string>('');
  const [diffKeyword, setDiffKeyword] = useState<string>('');

  const refresh = async () => {
    setLoading(true);
    try {
      const [st, vs] = await Promise.all([
        workspaceSkillApi.configRegistryStatus({ asset_type: assetType, scope, tenant_id: tenantId, channel }),
        workspaceSkillApi.configRegistryVersions({ asset_type: assetType, scope, tenant_id: tenantId, limit: 50, offset: 0 }),
      ]);
      setStatus(st);
      setVersions(Array.isArray((vs as any)?.items) ? (vs as any).items : []);
    } catch (e: any) {
      toast.error('加载失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // support deep link from approvals page
    try {
      const q = new URLSearchParams(window.location.search);
      const t = q.get('tenant_id');
      const sc = q.get('scope');
      const ch = q.get('channel');
      const at = q.get('asset_type');
      if (t) setTenantId(t);
      if (sc === 'workspace' || sc === 'engine') setScope(sc);
      if (ch === 'stable' || ch === 'canary') setChannel(ch);
      if (at === 'skill_spec_v2_schema' || at === 'permissions_catalog') setAssetType(at as any);
    } catch {
      // ignore
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, assetType, scope, channel]);

  const published = status?.published;
  const publishedVersion = published?.version || '（未发布）';
  const publishedPrev = published?.prev_version || '-';

  const columns = useMemo(
    () => [
      { key: 'version', title: '版本', dataIndex: 'version', width: 180 },
      { key: 'created_at', title: '创建时间', dataIndex: 'created_at', render: (v: any) => fmtTs(Number(v)), width: 190 },
      { key: 'created_by', title: '创建人', dataIndex: 'created_by', width: 140 },
      { key: 'note', title: '备注', dataIndex: 'note' },
      {
        key: 'actions',
        title: '操作',
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  const res = await workspaceSkillApi.configRegistryAsset({ asset_type: assetType, scope, tenant_id: tenantId, version: String(r.version) });
                  setPreviewVersion(String(r.version));
                  setPreviewPayload((res as any)?.item?.payload);
                  setPreviewOpen(true);
                } catch {
                  toast.error('获取版本内容失败');
                }
              }}
            >
              预览
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  const res = await workspaceSkillApi.configRegistryDiff({
                    asset_type: assetType,
                    scope,
                    tenant_id: tenantId,
                    channel,
                    from_ref: 'published',
                    to_version: String(r.version),
                  });
                  setDiffInfo(res);
                  setDiffOpen(true);
                } catch (e: any) {
                  toast.error('对比失败', String(e?.message || ''));
                }
              }}
            >
              对比
            </Button>
            <Button
              variant="primary"
              onClick={async () => {
                try {
                  const res = await workspaceSkillApi.configRegistryDiff({
                    asset_type: assetType,
                    scope,
                    tenant_id: tenantId,
                    channel,
                    from_ref: 'published',
                    to_version: String(r.version),
                  });
                  const assessment = (res as any)?.assessment || {};
                  if (assessment?.requires_approval) {
                    // Create approval request by calling publish (server will 409 with envelope)
                    try {
                      await workspaceSkillApi.configRegistryPublish(
                        { asset_type: assetType, scope, tenant_id: tenantId, channel },
                        { version: String(r.version), note: note || undefined }
                      );
                    } catch (e2: any) {
                      const detail = e2?.payload?.detail || e2?.detail;
                      const rid = detail?.approval_request_id || '';
                      setApprovalRequestId(String(rid || ''));
                      setApprovalOpen(true);
                      toast.warning('需要审批', '已创建审批请求，请在审批中心通过后点击“重放”执行发布。');
                      return;
                    }
                    return;
                  }
                  if (assessment?.requires_confirmation) {
                    setConfirmExpected(String(assessment.confirm_phrase || ''));
                    setPendingPublish({ version: String(r.version) });
                    setConfirmPhrase('');
                    setConfirmOpen(true);
                    return;
                  }
                  await workspaceSkillApi.configRegistryPublish(
                    { asset_type: assetType, scope, tenant_id: tenantId, channel },
                    { version: String(r.version), note: note || undefined }
                  );
                  toast.success('发布成功');
                  refresh();
                } catch (e: any) {
                  toast.error('发布失败', String(e?.message || ''));
                }
              }}
            >
              发布到 {channel}
            </Button>
          </div>
        ),
        width: 220,
      },
    ],
    [assetType, scope, tenantId, channel, note]
  );

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xl font-semibold text-gray-100">Skill 灰度发布</div>
          <div className="text-sm text-gray-500">对 schema / permissions catalog 进行 stable/canary 发布与回滚（按 tenant 维度）。</div>
        </div>
        <div className="flex items-center gap-2">
          <Select label="当前使用通道" value={activeChannel} options={channelOptions} onChange={(v: string) => {
            setActiveChannel(v as any);
            localStorage.setItem('active_release_channel', v);
            toast.success('已切换通道（会影响管理台后续请求）');
          }} />
          <Button variant="secondary" onClick={refresh} disabled={loading}>
            刷新
          </Button>
        </div>
      </div>

      <Card>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Input label="tenant_id" value={tenantId} onChange={(e: any) => setTenantId(String(e.target.value || '').trim() || 'default')} />
          <Select label="scope" value={scope} options={scopeOptions} onChange={(v: string) => setScope(v as any)} />
          <Select label="asset" value={assetType} options={assetOptions} onChange={(v: string) => setAssetType(v as any)} />
          <Select label="发布通道" value={channel} options={channelOptions} onChange={(v: string) => setChannel(v as any)} />
        </div>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input label="发布备注（可选）" value={note} onChange={(e: any) => setNote(e.target.value)} />
          <div className="flex items-end gap-2">
            <Button
              variant="primary"
              onClick={async () => {
                try {
                  await workspaceSkillApi.configRegistryPublish({ asset_type: assetType, scope, tenant_id: tenantId, channel }, { note: note || undefined });
                  toast.success('已发布默认版本');
                  refresh();
                } catch (e: any) {
                  toast.error('发布失败', String(e?.message || ''));
                }
              }}
            >
              发布默认到 {channel}
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  await workspaceSkillApi.configRegistryRollback({ asset_type: assetType, scope, tenant_id: tenantId, channel });
                  toast.success('已回滚');
                  refresh();
                } catch (e: any) {
                  const detail = e?.payload?.detail || e?.detail;
                  if (detail?.code === 'approval_required' && detail?.approval_request_id) {
                    setApprovalRequestId(String(detail.approval_request_id));
                    setApprovalOpen(true);
                    toast.warning('需要审批', '已创建审批请求，请在审批中心通过后点击 replay 执行回滚。');
                    return;
                  }
                  toast.error('回滚失败', String(e?.message || ''));
                }
              }}
            >
              回滚 {channel}
            </Button>
          </div>
          <div className="flex items-center gap-2 md:justify-end">
            <Badge variant={'secondary' as any}>published: {publishedVersion}</Badge>
            <Badge variant={'secondary' as any}>prev: {publishedPrev}</Badge>
            <Badge variant={published ? ('success' as any) : ('warning' as any)}>{published ? '已发布' : '未发布'}</Badge>
          </div>
        </div>
        {published && (
          <div className="mt-2 text-xs text-gray-500">
            updated_at={fmtTs(Number(published.updated_at))} · updated_by={published.updated_by || '-'} · note={published.note || '-'}
          </div>
        )}
      </Card>

      <Card>
        <div className="text-sm font-medium text-gray-200 mb-3">历史版本</div>
        <Table columns={columns as any} data={versions} rowKey="version" loading={loading} emptyText="暂无历史版本（你可以先发布默认版本）" />
      </Card>

      <Modal open={previewOpen} onClose={() => setPreviewOpen(false)} title={`预览版本：${previewVersion}`} width={980}>
        <Textarea rows={22} value={JSON.stringify(previewPayload ?? null, null, 2)} readOnly />
      </Modal>

      <Modal open={diffOpen} onClose={() => setDiffOpen(false)} title={`对比：published → ${diffInfo?.to_version || ''}`} width={980}>
        <div className="space-y-3">
          <Card>
            <div className="text-sm font-medium text-gray-200 mb-2">风险评估</div>
            <div className="text-sm text-gray-300">risk_level: {diffInfo?.assessment?.risk_level || '-'}</div>
            <div className="text-sm text-gray-300">requires_confirmation: {String(Boolean(diffInfo?.assessment?.requires_confirmation))}</div>
            <div className="text-sm text-gray-300">requires_approval: {String(Boolean(diffInfo?.assessment?.requires_approval))}</div>
            {diffInfo?.assessment?.confirm_phrase && <div className="text-sm text-gray-300">confirm_phrase: <code>{diffInfo.assessment.confirm_phrase}</code></div>}
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-200">Breaking changes</div>
                {Array.isArray(diffInfo?.assessment?.breaking_changes) && diffInfo.assessment.breaking_changes.length > 0 ? (
                  <div className="space-y-2">
                    {diffInfo.assessment.breaking_changes.slice(0, 20).map((it: any, idx: number) => {
                      const kw = String(it?.field || it?.permission || it?.type || '').trim();
                      return (
                        <div key={idx} className="flex items-center justify-between gap-2 bg-dark-bg border border-dark-border rounded px-2 py-1">
                          <code className="text-xs text-gray-200">{JSON.stringify(it)}</code>
                          <Button variant="ghost" onClick={() => setDiffKeyword(kw || String(it?.type || ''))}>
                            定位
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">无</div>
                )}
              </div>
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-200">Warnings</div>
                {Array.isArray(diffInfo?.assessment?.warnings) && diffInfo.assessment.warnings.length > 0 ? (
                  <div className="space-y-2">
                    {diffInfo.assessment.warnings.slice(0, 20).map((it: any, idx: number) => {
                      const kw = String(it?.field || it?.permission || it?.type || '').trim();
                      return (
                        <div key={idx} className="flex items-center justify-between gap-2 bg-dark-bg border border-dark-border rounded px-2 py-1">
                          <code className="text-xs text-gray-200">{JSON.stringify(it)}</code>
                          <Button variant="ghost" onClick={() => setDiffKeyword(kw || String(it?.type || ''))}>
                            定位
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">无</div>
                )}
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <div className="text-xs text-gray-500">提示：点击“定位”会在 diff 中搜索关键字并显示片段。</div>
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    const summary = [
                      `asset=${assetType} scope=${scope} tenant=${tenantId} channel=${channel}`,
                      `from=${diffInfo?.from_version ?? ''} to=${diffInfo?.to_version ?? ''}`,
                      `risk=${diffInfo?.assessment?.risk_level ?? ''}`,
                      `requires_approval=${Boolean(diffInfo?.assessment?.requires_approval)}`,
                      `requires_confirmation=${Boolean(diffInfo?.assessment?.requires_confirmation)}`,
                      `breaking=${JSON.stringify(diffInfo?.assessment?.breaking_changes || [])}`,
                      `warnings=${JSON.stringify(diffInfo?.assessment?.warnings || [])}`,
                    ].join('\n');
                    await navigator.clipboard.writeText(summary);
                    toast.success('已复制摘要');
                  } catch {
                    toast.error('复制失败');
                  }
                }}
              >
                复制摘要
              </Button>
            </div>
          </Card>
          {diffKeyword ? (
            <Card>
              <div className="text-sm font-medium text-gray-200 mb-2">定位片段：{diffKeyword}</div>
              <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
                {(() => {
                  const diff = String(diffInfo?.diff || '');
                  const lines = diff.split('\n');
                  const idx = lines.findIndex((l) => l.includes(diffKeyword));
                  if (idx < 0) return '未找到匹配行（可尝试换一个关键词）';
                  const start = Math.max(0, idx - 6);
                  const end = Math.min(lines.length, idx + 7);
                  return lines.slice(start, end).join('\n');
                })()}
              </pre>
            </Card>
          ) : null}
          <Textarea label="Unified Diff（完整）" rows={18} value={String(diffInfo?.diff || '')} readOnly />
        </div>
      </Modal>

      <Modal
        open={approvalOpen}
        onClose={() => setApprovalOpen(false)}
        title="需要审批（stable 高风险发布）"
        width={720}
        footer={
          <>
            <Button variant="secondary" onClick={() => setApprovalOpen(false)}>
              关闭
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                window.location.href = '/core/approvals';
              }}
            >
              打开审批中心
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="text-sm text-gray-300">该变更属于 stable 通道高风险发布，已转为审批流程。</div>
          <div className="text-sm text-gray-300">
            请在审批中心通过后，点击该审批单的 <code>重放（replay）</code> 来执行发布。
          </div>
          {approvalRequestId && (
            <div className="text-sm text-gray-300">
              approval_request_id：<code>{approvalRequestId}</code>
            </div>
          )}
        </div>
      </Modal>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="高风险发布确认"
        width={720}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={async () => {
                if (!pendingPublish) return;
                try {
                  await workspaceSkillApi.configRegistryPublish(
                    { asset_type: assetType, scope, tenant_id: tenantId, channel },
                    { version: pendingPublish.version, note: note || undefined, confirm_phrase: confirmPhrase }
                  );
                  toast.success('发布成功');
                  setConfirmOpen(false);
                  setPendingPublish(null);
                  refresh();
                } catch (e: any) {
                  const expected = e?.payload?.detail?.confirm_phrase || e?.detail?.confirm_phrase || confirmExpected;
                  toast.error('发布失败', expected ? `需要确认短语：${expected}` : String(e?.message || ''));
                }
              }}
              disabled={!confirmPhrase.trim()}
            >
              确认发布
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="text-sm text-gray-300">该变更被评估为高风险（breaking change 或高风险默认项）。请输入确认短语后继续：</div>
          {confirmExpected && (
            <div className="text-sm text-gray-300">
              需要输入：<code>{confirmExpected}</code>
            </div>
          )}
          <Input label="confirm_phrase" value={confirmPhrase} onChange={(e: any) => setConfirmPhrase(e.target.value)} placeholder={confirmExpected || '请输入确认短语'} />
        </div>
      </Modal>
    </div>
  );
};

export default Rollouts;
