import React, { useEffect, useMemo, useState } from 'react';
import { Copy, Eye, GitCompare, RefreshCw } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Table, toast } from '../../../components/ui';
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
        width: 240,
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
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchList} loading={loading}>
          刷新
        </Button>
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
            <div className="text-xs text-gray-500">name: {current.name} / version: {current.version}</div>
            <pre className="text-[11px] text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[420px]">
              {String(current.template || '')}
            </pre>
            <pre className="text-[11px] text-gray-400 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto max-h-[240px]">
              {JSON.stringify(parseJson(current.metadata_json) || {}, null, 2)}
            </pre>
          </div>
        )}
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
