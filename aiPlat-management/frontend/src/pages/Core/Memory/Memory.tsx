import React, { useState, useEffect } from 'react';
import { Plus, RotateCw, Search, Download, Upload, Eye } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Button, Modal, Input, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';
import { CreateSessionModal, SessionDetailModal, SearchMemoryModal, LongTermMemoryModal } from '../../../components/core';
import { useMemoryStore } from '../../../stores';
import type { MemorySession } from '../../../services';
import { memoryApi } from '../../../services';

const Memory: React.FC = () => {
  const { sessions, loading, selectedSession, fetchSessions, getDetail, deleteSession, clearSelectedSession, clearSearchResults } = useMemoryStore();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [longTermOpen, setLongTermOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; sessionId: string | null }>({ open: false, sessionId: null });
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importPreview, setImportPreview] = useState<any>(null);
  const [importFile, setImportFile] = useState<any>(null);
  const [importMerge, setImportMerge] = useState(false);
  const [importing, setImporting] = useState(false);
  const [inspectModalOpen, setInspectModalOpen] = useState(false);
  const [inspectData, setInspectData] = useState<any>(null);
  const [inspectNamespace, setInspectNamespace] = useState('');
  const [inspectLoading, setInspectLoading] = useState(false);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleViewDetail = async (sessionId: string) => {
    try {
      await getDetail(sessionId);
      setDetailModalOpen(true);
    } catch {
      toast.error('获取详情失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.sessionId) return;
    try {
      await deleteSession(deleteConfirm.sessionId);
      toast.success('会话已删除');
      setDeleteConfirm({ open: false, sessionId: null });
    } catch {
      toast.error('删除失败');
    }
  };

  const handleExport = async () => {
    try {
      const data = await memoryApi.exportAll();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aiplat-memory-export-${(data as any).exported_at?.replace(/[:.]/g, '-') || Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('记忆导出完成');
      setExportModalOpen(false);
    } catch (e) { toastGateError(e, '导出失败'); }
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      setImportFile(data);
      const validation = await memoryApi.validateImport({ data });
      setImportPreview(validation);
    } catch (e) { toastGateError(e, '文件解析失败'); }
  };

  const handleImport = async () => {
    if (!importFile) return;
    setImporting(true);
    try {
      await memoryApi.importFrom({ data: importFile, merge: importMerge });
      toast.success('记忆导入完成');
      setImportModalOpen(false);
      setImportFile(null);
      setImportPreview(null);
      fetchSessions();
    } catch (e) { toastGateError(e, '导入失败'); }
    finally { setImporting(false); }
  };

  const handleInspect = async () => {
    setInspectLoading(true);
    try {
      const data = await memoryApi.inspect(inspectNamespace || undefined);
      setInspectData(data);
      setInspectModalOpen(true);
    } catch (e) { toastGateError(e, '检查失败'); }
    finally { setInspectLoading(false); }
  };

  const columns = [
    {
      title: '会话ID',
      dataIndex: 'session_id',
      key: 'session_id',
      render: (id: string) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{id.slice(0, 16)}...</code>
      ),
    },
    {
      title: '消息数',
      dataIndex: 'message_count',
      key: 'message_count',
      width: 120,
      align: 'center' as const,
      render: (count: number) => count ?? '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: MemorySession) => (
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleViewDetail(record.session_id)}
            className="px-2 py-1 rounded-lg text-sm text-primary hover:bg-primary-light transition-colors"
          >
            详情
          </button>
          <button
            onClick={() => setDeleteConfirm({ open: true, sessionId: record.session_id })}
            className="px-2 py-1 rounded-lg text-sm text-error hover:bg-error-light transition-colors"
          >
            删除
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">Memory管理</h1>
          <p className="text-sm text-gray-500 mt-1">管理AI代理的对话记忆与会话上下文</p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<Download className="w-4 h-4" />} onClick={() => setExportModalOpen(true)}>
            导出
          </Button>
          <Button icon={<Upload className="w-4 h-4" />} onClick={() => setImportModalOpen(true)}>
            导入
          </Button>
          <Button icon={<Eye className="w-4 h-4" />} onClick={handleInspect} loading={inspectLoading}>检查</Button>
          <Button icon={<Search className="w-4 h-4" />} onClick={() => setSearchModalOpen(true)}>搜索</Button>
          <Button onClick={() => setLongTermOpen(true)}>
            长期记忆
          </Button>
          <Button
            icon={<RotateCw className="w-4 h-4" />}
            onClick={fetchSessions}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            variant="primary"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => setAddModalOpen(true)}
          >
            创建会话
          </Button>
        </div>
      </div>

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">会话ID</span><span className="ml-2 text-gray-600">Agent 会话唯一标识</span></div>
          <div><span className="text-gray-300">消息数</span><span className="ml-2 text-gray-600">该会话中的消息总数</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">查看详情/删除会话</span></div>
        </div>
      </details>

      {/* Table Card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={sessions}
          rowKey="session_id"
          loading={loading}
          emptyText="暂无会话数据"
        />
      </motion.div>

      {/* Delete Confirmation Modal */}
      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, sessionId: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteConfirm({ open: false, sessionId: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除会话 "{deleteConfirm.sessionId?.slice(0, 16)}..." 吗？此操作不可撤销，请谨慎操作。
        </p>
      </Modal>

      <CreateSessionModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={fetchSessions}
      />

      <SessionDetailModal
        open={detailModalOpen}
        session={selectedSession}
        onClose={() => { setDetailModalOpen(false); clearSelectedSession(); }}
      />

      <SearchMemoryModal
        open={searchModalOpen}
        onClose={() => { setSearchModalOpen(false); clearSearchResults(); }}
      />

      <LongTermMemoryModal
        open={longTermOpen}
        onClose={() => setLongTermOpen(false)}
      />

      {/* Export Modal */}
      <Modal open={exportModalOpen} onClose={() => setExportModalOpen(false)} title="导出全部记忆"
        footer={<><Button onClick={() => setExportModalOpen(false)}>取消</Button><Button variant="primary" onClick={handleExport}>下载 JSON</Button></>}>
        <p className="text-gray-400 text-sm">导出包含：情景记忆摘要、语义/长期记忆、L3 任务技能记忆。可用于实例迁移或备份。</p>
      </Modal>

      {/* Import Modal */}
      <Modal open={importModalOpen} onClose={() => { setImportModalOpen(false); setImportFile(null); setImportPreview(null); }}
        title="导入记忆" footer={importFile ? <><Button onClick={() => setImportModalOpen(false)}>取消</Button>
        <Button variant="primary" onClick={handleImport} loading={importing}>{importMerge ? '合并导入' : '覆盖导入'}</Button></> : undefined}>
        {!importFile ? (
          <div className="space-y-3">
            <p className="text-gray-400 text-sm">选择之前导出的 aiplat-memory-export-*.json 文件</p>
            <input type="file" accept=".json" onChange={handleImportFile} className="text-sm text-gray-300" />
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">预览：</p>
            <div className="text-xs text-gray-400 space-y-1">
              <p>版本: {importPreview?.version || '?'}</p>
              <p>语义记忆: {importPreview?.preview?.semantic_items || 0} 条</p>
              <p>任务技能: {importPreview?.preview?.task_skills || 0} 条</p>
              <p>情景摘要: {importPreview?.preview?.episodic_has_summary ? '有' : '无'}</p>
              {importPreview?.warnings?.length > 0 && <p className="text-amber-400">⚠ {importPreview.warnings.join('; ')}</p>}
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input type="checkbox" checked={importMerge} onChange={(e) => setImportMerge(e.target.checked)} /> 合并模式（保留现有记忆）
            </label>
          </div>
        )}
      </Modal>

      {/* Inspect Modal */}
      <Modal open={inspectModalOpen} onClose={() => { setInspectModalOpen(false); setInspectData(null); setInspectNamespace(''); }}
        title="记忆检查器" width="720px" footer={<Button onClick={() => setInspectModalOpen(false)}>关闭</Button>}>
        <div className="space-y-4 max-h-96 overflow-y-auto">
          <div className="flex items-center gap-2">
            <Input placeholder="命名空间 (如 pm_agent)" value={inspectNamespace} onChange={(v: any) => setInspectNamespace(v?.target?.value || '')} style={{ maxWidth: 200 }} />
            <Button size="sm" onClick={handleInspect} loading={inspectLoading}>刷新</Button>
          </div>
          {inspectData ? (
            <div className="space-y-3 text-sm">
              <div className="bg-dark-hover rounded p-3">
                <span className="font-medium text-gray-200">当前工作记忆</span>
                <p className="text-gray-400 text-xs">Token: {inspectData.working?.token_count}, 消息: {inspectData.working?.message_count}</p>
              </div>
              <div className="bg-dark-hover rounded p-3">
                <span className="font-medium text-gray-200">情景记忆</span>
                <p className="text-gray-400 text-xs">{inspectData.episodic?.summary || '(空)'}</p>
              </div>
              <div className="bg-dark-hover rounded p-3">
                <span className="font-medium text-gray-200">语义记忆 ({inspectData.semantic?.total_items || 0} 条)</span>
                {(inspectData.semantic?.items || []).slice(0, 10).map((item: any, i: number) => (
                  <details key={i} className="text-xs text-gray-400 mt-1">
                    <summary className="cursor-pointer">{item.key}</summary>
                    <p className="ml-2">{item.content}</p>
                  </details>
                ))}
              </div>
              <div className="bg-dark-hover rounded p-3">
                <span className="font-medium text-gray-200">技能记忆 ({inspectData.task_skills?.total || 0} 条)</span>
                {(inspectData.task_skills?.skills || []).map((s: any, i: number) => (
                  <p key={i} className="text-xs text-gray-400">ID: {s.skill_id} pass_rate: {s.pass_rate}</p>
                ))}
              </div>
            </div>
          ) : <p className="text-gray-500 text-sm">点击检查加载记忆数据</p>}
        </div>
      </Modal>
    </div>
  );
};

export default Memory;
