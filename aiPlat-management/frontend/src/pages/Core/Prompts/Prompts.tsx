import React, { useEffect, useMemo, useState } from 'react';
import { Copy, Eye, GitCompare, RefreshCw, Pencil, Plus, Trash2, RotateCcw, ExternalLink, Megaphone } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Select, Table, Textarea, toast } from '../../../components/ui';
import { promptApi, type PromptTemplateRow } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

function parseJson(s: any): any {
  if (!s || typeof s !== 'string') return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

type EditForm = {
  template_id: string;
  name: string;
  template: string;
  require_approval: boolean;
  approval_request_id: string;
  details: string;
};

type ReleaseForm = {
  template_id: string;
  pinned_version: string;
  base_version: string;
  canary_version: string;
  canary_percent: number;
  require_approval: boolean;
  approval_request_id: string;
  details: string;
};

const Prompts: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<PromptTemplateRow[]>([]);
  const [q, setQ] = useState('');

  const [openView, setOpenView] = useState(false);
  const [viewLoading, setViewLoading] = useState(false);
  const [current, setCurrent] = useState<PromptTemplateRow | null>(null);
  const [selectedId, setSelectedId] = useState<string>('');

  const [openVersions, setOpenVersions] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);

  const [openDiff, setOpenDiff] = useState(false);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffText, setDiffText] = useState('');
  const [fromVer, setFromVer] = useState<string>('');
  const [toVer, setToVer] = useState<string>('');

  const [openEdit, setOpenEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [edit, setEdit] = useState<EditForm>({
    template_id: '',
    name: '',
    template: '',
    require_approval: true,
    approval_request_id: '',
    details: '',
  });

  const [rollingBack, setRollingBack] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [openRelease, setOpenRelease] = useState(false);
  const [releaseSaving, setReleaseSaving] = useState(false);
  const [releaseRollingBack, setReleaseRollingBack] = useState(false);
  const [release, setRelease] = useState<ReleaseForm>({
    template_id: '',
    pinned_version: '',
    base_version: '',
    canary_version: '',
    canary_percent: 0,
    require_approval: true,
    approval_request_id: '',
    details: '',
  });

  const fetchList = async () => {
    setLoading(true);
    try {
      const res = await promptApi.list({ limit: 200, offset: 0 });
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setItems([]);
      toastGateError(e, '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, []);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return items;
    return items.filter((r) => String(r.template_id || '').toLowerCase().includes(t) || String(r.name || '').toLowerCase().includes(t));
  }, [items, q]);

  const openTemplate = async (templateId: string) => {
    setSelectedId(String(templateId));
    setOpenView(true);
    setViewLoading(true);
    try {
      const tpl = await promptApi.get(templateId);
      setCurrent(tpl);
    } catch (e: any) {
      setCurrent(null);
      toastGateError(e, '加载模板失败');
    } finally {
      setViewLoading(false);
    }
  };

  const openCreate = () => {
    setSelectedId('');
    setCurrent(null);
    setEdit({
      template_id: '',
      name: '',
      template: '',
      require_approval: true,
      approval_request_id: '',
      details: '',
    });
    setOpenEdit(true);
  };

  const openEditExisting = async (templateId: string) => {
    setSelectedId(String(templateId));
    setOpenView(false);
    try {
      const tpl = await promptApi.get(templateId);
      setCurrent(tpl);
      setEdit({
        template_id: String(tpl?.template_id || templateId),
        name: String(tpl?.name || ''),
        template: String(tpl?.template || ''),
        require_approval: true,
        approval_request_id: '',
        details: '',
      });
      setOpenEdit(true);
    } catch (e: any) {
      toastGateError(e, '加载模板失败');
    }
  };

  const submitUpsert = async () => {
    if (!edit.template_id.trim()) {
      toast.error('template_id 不能为空');
      return;
    }
    if (!edit.name.trim()) {
      toast.error('name 不能为空');
      return;
    }
    setSaving(true);
    try {
      const res = await promptApi.upsert({
        template_id: edit.template_id.trim(),
        name: edit.name.trim(),
        template: edit.template || '',
        require_approval: !!edit.require_approval,
        approval_request_id: edit.approval_request_id.trim() || undefined,
        details: edit.details.trim() || undefined,
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.info(`已创建审批：${String(res.approval_request_id)}`);
      } else {
        toast.success(`已保存（change_id=${String(res?.change_id || '-') }）`);
      }
      setOpenEdit(false);
      await fetchList();
      if (edit.template_id) {
        await openTemplate(edit.template_id);
      }
    } catch (e: any) {
      toastGateError(e, '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const openTemplateVersions = async (templateId: string) => {
    setSelectedId(String(templateId));
    setOpenVersions(true);
    setVersionsLoading(true);
    setVersions([]);
    try {
      const res = await promptApi.versions(templateId, { limit: 50, offset: 0 });
      setVersions(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setVersions([]);
      toastGateError(e, '加载版本失败');
    } finally {
      setVersionsLoading(false);
    }
  };

  const rollbackTo = async (templateId: string, version: string) => {
    setRollingBack(true);
    try {
      const res = await promptApi.rollback(templateId, {
        template_id: templateId,
        version,
        require_approval: true,
        details: `rollback prompt template ${templateId} to ${version}`,
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.info(`已创建审批：${String(res.approval_request_id)}`);
      } else {
        toast.success(`已回滚（change_id=${String(res?.change_id || '-') }）`);
      }
      await fetchList();
      await openTemplate(templateId);
    } catch (e: any) {
      toastGateError(e, '回滚失败');
    } finally {
      setRollingBack(false);
    }
  };

  const deleteTemplate = async (templateId: string) => {
    setDeleting(true);
    try {
      const res = await promptApi.delete(templateId, { require_approval: true, details: `delete prompt template ${templateId}` });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.info(`已创建审批：${String(res.approval_request_id)}`);
      } else {
        toast.success(`已删除（change_id=${String(res?.change_id || '-') }）`);
      }
      setOpenView(false);
      await fetchList();
    } catch (e: any) {
      toastGateError(e, '删除失败');
    } finally {
      setDeleting(false);
    }
  };

  const openReleaseModal = async (templateId: string) => {
    setSelectedId(String(templateId));
    setOpenRelease(true);
    try {
      const tpl: any = await promptApi.get(templateId);
      setCurrent(tpl);
      const md = parseJson(tpl?.metadata_json) || {};
      const rel = md?.release && typeof md.release === 'object' ? md.release : {};
      const pinned = String(rel?.pinned_version || '');
      const rollout = Array.isArray(rel?.rollout) ? rel.rollout : [];
      const baseV = String(tpl?.version || '');
      let canaryV = '';
      let canaryP = 0;
      try {
        const r1 = rollout.find((x: any) => String(x?.version || '') && String(x?.version || '') !== baseV);
        if (r1) {
          canaryV = String(r1.version || '');
          canaryP = Number(r1.weight || 0);
        }
      } catch {
        // ignore
      }
      try {
        const res = await promptApi.versions(templateId, { limit: 100, offset: 0 });
        setVersions(Array.isArray(res?.items) ? res.items : []);
      } catch {
        // ignore
      }
      setRelease({
        template_id: String(tpl?.template_id || templateId),
        pinned_version: pinned,
        base_version: baseV,
        canary_version: canaryV,
        canary_percent: canaryP,
        require_approval: true,
        approval_request_id: '',
        details: `release prompt template ${templateId}`,
      });
    } catch (e: any) {
      toastGateError(e, '加载模板失败');
    }
  };

  const submitRelease = async () => {
    const tid = release.template_id.trim();
    if (!tid) return;
    setReleaseSaving(true);
    try {
      const pinned = release.pinned_version.trim();
      const canaryP = Math.max(0, Math.min(100, Number(release.canary_percent || 0)));
      const baseV = release.base_version.trim();
      const canaryV = release.canary_version.trim();
      let rollout: any[] = [];
      if (!pinned && canaryV && canaryP > 0 && baseV) {
        rollout = [
          { version: baseV, weight: 100 - canaryP },
          { version: canaryV, weight: canaryP },
        ];
      }
      const res: any = await promptApi.release(tid, {
        pinned_version: pinned || null,
        rollout,
        require_approval: !!release.require_approval,
        approval_request_id: release.approval_request_id.trim() || undefined,
        details: release.details.trim() || undefined,
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.info(`已创建审批：${String(res.approval_request_id)}`);
      } else {
        toast.success(`已更新发布设置（change_id=${String(res?.change_id || '-') }）`);
      }
      setOpenRelease(false);
      await fetchList();
      await openTemplate(tid);
    } catch (e: any) {
      toastGateError(e, '发布设置更新失败');
    } finally {
      setReleaseSaving(false);
    }
  };

  const rollbackRelease = async () => {
    const tid = release.template_id.trim();
    if (!tid) return;
    setReleaseRollingBack(true);
    try {
      const res: any = await promptApi.rollbackRelease(tid, {
        require_approval: true,
        approval_request_id: release.approval_request_id.trim() || undefined,
        details: `rollback prompt template release ${tid}`,
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.info(`已创建审批：${String(res.approval_request_id)}`);
      } else {
        toast.success(`已回滚发布设置（change_id=${String(res?.change_id || '-') }）`);
      }
      setOpenRelease(false);
      await fetchList();
      await openTemplate(tid);
    } catch (e: any) {
      toastGateError(e, '回滚发布设置失败');
    } finally {
      setReleaseRollingBack(false);
    }
  };

  const openTemplateDiff = async (templateId: string) => {
    setSelectedId(String(templateId));
    setOpenDiff(true);
    setDiffLoading(true);
    setDiffText('');
    setFromVer('');
    setToVer('');
    try {
      const res = await promptApi.diff(templateId);
      setDiffText(String(res?.diff || ''));
      setFromVer(String(res?.from_version || ''));
      setToVer(String(res?.to_version || ''));
    } catch (e: any) {
      setDiffText('');
      toastGateError(e, '加载 diff 失败');
    } finally {
      setDiffLoading(false);
    }
  };

  const reloadDiff = async () => {
    const tid = selectedId || current?.template_id;
    if (!tid) return;
    setDiffLoading(true);
    try {
      const res = await promptApi.diff(tid, { from_version: fromVer || undefined, to_version: toVer || undefined });
      setDiffText(String(res?.diff || ''));
      setFromVer(String(res?.from_version || fromVer || ''));
      setToVer(String(res?.to_version || toVer || ''));
    } catch (e: any) {
      toastGateError(e, '加载 diff 失败');
    } finally {
      setDiffLoading(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: 'template_id',
        title: 'template_id',
        dataIndex: 'template_id',
        width: 240,
        render: (v: any) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '')}</code>,
      },
      { key: 'name', title: 'name', dataIndex: 'name', width: 220 },
      { key: 'version', title: 'version', dataIndex: 'version', width: 110, render: (v: any) => <Badge variant="default">{String(v || '-')}</Badge> },
      {
        key: 'verification',
        title: 'verify',
        width: 130,
        render: (_: any, r: PromptTemplateRow) => {
          const md = parseJson(r.metadata_json);
          const st = String(md?.verification?.status || '-');
          const variant = st === 'verified' ? 'success' : st === 'pending' ? 'warning' : st === 'failed' ? 'danger' : 'default';
          return <Badge variant={variant as any}>{st}</Badge>;
        },
      },
      {
        key: 'actions',
        title: '',
        width: 340,
        render: (_: any, r: PromptTemplateRow) => (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              icon={<Copy size={14} />}
              onClick={() => {
                navigator.clipboard.writeText(String(r.template_id || ''));
                toast.success('已复制');
              }}
            />
            <Button variant="secondary" icon={<Eye size={14} />} onClick={() => openTemplate(String(r.template_id))}>
              查看
            </Button>
            <Button variant="secondary" icon={<Megaphone size={14} />} onClick={() => openReleaseModal(String(r.template_id))}>
              发布/灰度
            </Button>
            <Button variant="secondary" icon={<Pencil size={14} />} onClick={() => openEditExisting(String(r.template_id))}>
              编辑
            </Button>
            <Button
              variant="secondary"
              icon={<GitCompare size={14} />}
              onClick={async () => {
                const tid = String(r.template_id);
                // best-effort load template + diff
                openTemplate(tid);
                openTemplateDiff(tid);
              }}
            >
              diff
            </Button>
            <Button variant="secondary" onClick={() => openTemplateVersions(String(r.template_id))}>
              versions
            </Button>
          </div>
        ),
      },
    ],
    [items]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Prompt Templates</h1>
          <div className="text-sm text-gray-500 mt-1">版本 / diff / 验证状态（autosmoke）</div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" icon={<Plus size={16} />} onClick={openCreate}>
            新建
          </Button>
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchList} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="按 template_id / name 过滤" className="w-72" />
            <div className="text-xs text-gray-500">total={items.length}</div>
          </div>
        </CardHeader>
        <CardContent>
          <Table data={filtered} columns={columns as any} rowKey={(r: any) => String(r.template_id)} loading={loading} />
        </CardContent>
      </Card>

      {/* View */}
      <Modal open={openView} onClose={() => setOpenView(false)} title={`模板：${selectedId || current?.template_id || '-'}`} width={1000}>
        {viewLoading ? (
          <div className="text-sm text-gray-500">loading…</div>
        ) : !current ? (
          <div className="text-sm text-gray-500">未加载</div>
        ) : (
          <div className="space-y-3">
            {(() => {
              const md = parseJson(current.metadata_json) || {};
              const ver = md?.verification || {};
              const gov = md?.governance || {};
              const st = String(ver?.status || '-');
              const traceId = String(ver?.trace_id || '');
              const jobRunId = String(ver?.job_run_id || '');
              const latestChangeId = String(gov?.latest_change_id || '');
              return (
                <div className="text-xs text-gray-500 space-y-1">
                  <div>
                    name: {current.name} / version: {current.version} / verify: <code className="bg-dark-hover px-1 py-0.5 rounded">{st}</code>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    {latestChangeId ? (
                      <a className="underline inline-flex items-center gap-1" href={`/diagnostics/change-control/${encodeURIComponent(latestChangeId)}`}>
                        latest change_id: {latestChangeId} <ExternalLink size={12} />
                      </a>
                    ) : null}
                    {traceId ? (
                      <a className="underline inline-flex items-center gap-1" href={`/diagnostics/traces/${encodeURIComponent(traceId)}`}>
                        trace: {traceId} <ExternalLink size={12} />
                      </a>
                    ) : null}
                    {jobRunId ? <span>job_run_id: {jobRunId}</span> : null}
                  </div>
                </div>
              );
            })()}
            <pre className="text-[11px] text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[420px]">
              {String(current.template || '')}
            </pre>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" icon={<Megaphone size={14} />} onClick={() => openReleaseModal(String(current.template_id))}>
                发布/灰度
              </Button>
              <Button variant="secondary" icon={<Pencil size={14} />} onClick={() => openEditExisting(String(current.template_id))}>
                编辑
              </Button>
              <Button variant="secondary" icon={<RotateCcw size={14} />} onClick={() => openTemplateVersions(String(current.template_id))} loading={rollingBack}>
                回滚到版本…
              </Button>
              <Button variant="danger" icon={<Trash2 size={14} />} onClick={() => deleteTemplate(String(current.template_id))} loading={deleting}>
                删除
              </Button>
            </div>
            <pre className="text-[11px] text-gray-400 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto max-h-[240px]">
              {JSON.stringify(parseJson(current.metadata_json) || {}, null, 2)}
            </pre>
          </div>
        )}
      </Modal>

      {/* Release / Rollout */}
      <Modal
        open={openRelease}
        onClose={() => setOpenRelease(false)}
        title={`发布/灰度：${release.template_id || '-'}`}
        width={980}
      >
        <div className="space-y-3">
          <div className="text-xs text-gray-500">
            发布/灰度只修改 metadata.release（不改变模板内容）。灰度采用 deterministic bucketing（优先按 session_id，其次 user_id/tenant_id）。
          </div>

          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-200">版本 pin（最高优先级）</div>
            </CardHeader>
            <CardContent>
              <Select
                value={release.pinned_version}
                onChange={(v: any) => setRelease((p) => ({ ...p, pinned_version: String(v || '') }))}
                options={[
                  { label: '不固定（使用灰度/默认）', value: '' },
                  ...versions.map((x: any) => ({ label: String(x?.version || ''), value: String(x?.version || '') })),
                ]}
              />
              <div className="text-xs text-gray-500 mt-2">用于紧急强制固定/快速回滚发布影响面。</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-200">灰度（当未 pin 时生效）</div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                <div>
                  <div className="text-xs text-gray-500 mb-1">base_version</div>
                  <Select
                    value={release.base_version}
                    onChange={(v: any) => setRelease((p) => ({ ...p, base_version: String(v || '') }))}
                    options={versions.map((x: any) => ({ label: String(x?.version || ''), value: String(x?.version || '') }))}
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">canary_version</div>
                  <Select
                    value={release.canary_version}
                    onChange={(v: any) => setRelease((p) => ({ ...p, canary_version: String(v || '') }))}
                    options={[{ label: '不启用灰度', value: '' }, ...versions.map((x: any) => ({ label: String(x?.version || ''), value: String(x?.version || '') }))]}
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">canary_percent（0-100）</div>
                  <Input
                    value={String(release.canary_percent ?? 0)}
                    onChange={(e: any) => setRelease((p) => ({ ...p, canary_percent: Number(e.target.value || 0) }))}
                    placeholder="10"
                  />
                </div>
              </div>
              <div className="text-xs text-gray-500 mt-2">
                将生成 rollout：base={100 - Number(release.canary_percent || 0)}%，canary={Number(release.canary_percent || 0)}%。
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-200">审批</div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-3">
                <label className="text-xs text-gray-400 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={release.require_approval}
                    onChange={(e) => setRelease((p) => ({ ...p, require_approval: e.target.checked }))}
                  />
                  require_approval
                </label>
                {release.require_approval ? (
                  <Input
                    className="w-[320px]"
                    value={release.approval_request_id}
                    onChange={(e) => setRelease((p) => ({ ...p, approval_request_id: e.target.value }))}
                    placeholder="approval_request_id（可选：审批通过后再填重试）"
                  />
                ) : null}
                <Input
                  className="min-w-[360px]"
                  value={release.details}
                  onChange={(e) => setRelease((p) => ({ ...p, details: e.target.value }))}
                  placeholder="details（可选）"
                />
              </div>
            </CardContent>
          </Card>

          <div className="flex items-center justify-between gap-2">
            <Button variant="secondary" onClick={rollbackRelease} loading={releaseRollingBack}>
              回滚发布设置
            </Button>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setOpenRelease(false)}>
                取消
              </Button>
              <Button onClick={submitRelease} loading={releaseSaving}>
                保存发布设置
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Edit */}
      <Modal open={openEdit} onClose={() => setOpenEdit(false)} title={edit.template_id ? `编辑：${edit.template_id}` : '新建模板'} width={1000}>
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">template_id</div>
              <Input value={edit.template_id} onChange={(e) => setEdit((p) => ({ ...p, template_id: e.target.value }))} placeholder="例如 core.system.prompt.v1" />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">name</div>
              <Input value={edit.name} onChange={(e) => setEdit((p) => ({ ...p, name: e.target.value }))} />
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500 mb-1">template</div>
            <Textarea value={edit.template} onChange={(e) => setEdit((p) => ({ ...p, template: e.target.value }))} rows={12} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="text-xs text-gray-400 flex items-center gap-2">
              <input
                type="checkbox"
                checked={edit.require_approval}
                onChange={(e) => setEdit((p) => ({ ...p, require_approval: e.target.checked }))}
              />
              require_approval
            </label>
            {edit.require_approval ? (
              <Input
                className="w-[320px]"
                value={edit.approval_request_id}
                onChange={(e) => setEdit((p) => ({ ...p, approval_request_id: e.target.value }))}
                placeholder="approval_request_id（可选：审批通过后再填重试）"
              />
            ) : null}
            <Input
              className="min-w-[320px]"
              value={edit.details}
              onChange={(e) => setEdit((p) => ({ ...p, details: e.target.value }))}
              placeholder="details（可选）"
            />
          </div>

          <div className="flex items-center gap-2">
            <Button variant="primary" loading={saving} onClick={submitUpsert}>
              保存
            </Button>
            <Button variant="secondary" onClick={() => setOpenEdit(false)}>
              取消
            </Button>
          </div>
        </div>
      </Modal>

      {/* Versions */}
      <Modal open={openVersions} onClose={() => setOpenVersions(false)} title={`版本列表：${selectedId || current?.template_id || '-'}`} width={820}>
        <Table
          loading={versionsLoading}
          data={versions}
          rowKey={(r: any) => String(r.version || r.created_at || Math.random())}
          columns={[
            { key: 'version', title: 'version', dataIndex: 'version', width: 120 },
            { key: 'created_at', title: 'created_at', dataIndex: 'created_at', width: 180 },
            { key: 'template_sha256', title: 'template_sha256', dataIndex: 'template_sha256' },
            {
              key: 'actions',
              title: '',
              width: 150,
              render: (_: any, r: any) => (
                <Button
                  variant="secondary"
                  icon={<RotateCcw size={14} />}
                  loading={rollingBack}
                  onClick={() => rollbackTo(String(selectedId || current?.template_id || ''), String(r.version))}
                >
                  回滚
                </Button>
              ),
            },
          ]}
          emptyText="暂无版本"
        />
      </Modal>

      {/* Diff */}
      <Modal open={openDiff} onClose={() => setOpenDiff(false)} title={`Diff：${selectedId || current?.template_id || '-'}`} width={1100}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input value={fromVer} onChange={(e) => setFromVer(e.target.value)} placeholder="from_version（可空）" className="w-48" />
            <Input value={toVer} onChange={(e) => setToVer(e.target.value)} placeholder="to_version（可空）" className="w-48" />
            <Button variant="secondary" loading={diffLoading} onClick={reloadDiff}>
              刷新 diff
            </Button>
          </div>
          <pre className="text-[11px] text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[520px]">
            {diffLoading ? 'loading…' : diffText || '(empty)'}
          </pre>
        </div>
      </Modal>
    </div>
  );
};

export default Prompts;
