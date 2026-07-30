import React, { useMemo, useState } from 'react';
import { Modal, Button, Input, Table, Textarea, toast, Tabs } from '../ui';
import { memoryApi, type LongTermMemoryItem } from '../../services';

interface LongTermMemoryModalProps {
  open: boolean;
  onClose: () => void;
}

const LongTermMemoryModal: React.FC<LongTermMemoryModalProps> = ({ open, onClose }) => {
  const [tab, setTab] = useState<'list' | 'search' | 'add'>('list');

  const [userId, setUserId] = useState('system');
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<LongTermMemoryItem[]>([]);

  const [addKey, setAddKey] = useState('');
  const [addContent, setAddContent] = useState('');
  const [addMetaText, setAddMetaText] = useState('{}');

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editKey, setEditKey] = useState('');
  const [editMetaText, setEditMetaText] = useState('{}');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const columns = useMemo(
    () => [
      {
        title: 'id',
        key: 'id',
        width: 140,
        render: (_: unknown, r: LongTermMemoryItem) => (
          <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{r.id?.slice(-12) || r.id}</code>
        ),
      },
      {
        title: 'key',
        key: 'key',
        width: 120,
        render: (_: unknown, r: LongTermMemoryItem) => <span className="text-gray-300">{r.key || '-'}</span>,
      },
      {
        title: 'content',
        key: 'content',
        render: (_: unknown, r: LongTermMemoryItem) => (
          <div
            className="text-sm text-gray-300 whitespace-pre-wrap break-words cursor-pointer hover:text-gray-200"
            onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
          >
            {String(r.content || '').slice(0, expandedId === r.id ? 9999 : 160)}
            {String(r.content || '').length > 160 && expandedId !== r.id && (
              <span className="text-xs text-blue-400 ml-1">展开</span>
            )}
          </div>
        ),
      },
      {
        title: '标签',
        key: 'source_tag',
        width: 80,
        render: (_: unknown, r: LongTermMemoryItem) => (
          <span className="text-xs text-purple-400">{r.source_tag || '-'}</span>
        ),
      },
      {
        title: '信任',
        key: 'trust_weight',
        width: 60,
        render: (_: unknown, r: LongTermMemoryItem) => (
          <span className="text-xs text-blue-400">{r.trust_weight != null ? r.trust_weight.toFixed(2) : '-'}</span>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 100,
        render: (_: unknown, r: LongTermMemoryItem) => (
          <div className="flex gap-1">
            <button
              className="text-xs text-blue-400 hover:text-blue-300 px-1.5 py-0.5 rounded"
              onClick={() => startEdit(r)}
            >
              编辑
            </button>
            <button
              className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded"
              onClick={() => doDelete(r.id)}
            >
              删除
            </button>
          </div>
        ),
      },
    ],
    [items],
  );

  const doList = async () => {
    setLoading(true);
    try {
      const res = await memoryApi.listLongTerm({ user_id: userId || 'system', limit: 50 });
      setItems(res.items || []);
    } catch (e: any) {
      toast.error('获取列表失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await memoryApi.searchLongTerm({ user_id: userId || 'system', query: query.trim(), limit });
      setItems(res.items || []);
    } catch (e: any) {
      toast.error('搜索失败', String(e?.message || ''));
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  const doAdd = async () => {
    if (!addContent.trim()) return;
    setLoading(true);
    try {
      let metadata: Record<string, unknown> | undefined = undefined;
      try {
        metadata = addMetaText?.trim() ? JSON.parse(addMetaText) : undefined;
      } catch (e: any) {
        throw new Error(`metadata 不是合法 JSON：${e?.message || ''}`);
      }
      await memoryApi.addLongTerm({
        user_id: userId || 'system',
        key: addKey || undefined,
        content: addContent,
        metadata,
      });
      toast.success('已写入长期记忆');
      setAddKey('');
      setAddContent('');
      setAddMetaText('{}');
      setTab('list');
      doList();
    } catch (e: any) {
      toast.error('写入失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (item: LongTermMemoryItem) => {
    setEditingId(item.id);
    setEditContent(item.content || '');
    setEditKey(item.key || '');
    setEditMetaText(JSON.stringify(item.metadata || {}, null, 2));
  };

  const doUpdate = async () => {
    if (!editingId || !editContent.trim()) return;
    setLoading(true);
    try {
      let metadata: Record<string, unknown> | undefined = undefined;
      try {
        metadata = editMetaText?.trim() ? JSON.parse(editMetaText) : undefined;
      } catch (e: any) {
        throw new Error(`metadata 不是合法 JSON：${e?.message || ''}`);
      }
      await memoryApi.updateLongTerm(editingId, {
        content: editContent,
        key: editKey || undefined,
        metadata,
      });
      toast.success('已更新');
      setEditingId(null);
      doList();
    } catch (e: any) {
      toast.error('更新失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const doDelete = async (memoryId: string) => {
    if (!confirm('确认删除该条长期记忆？')) return;
    setLoading(true);
    try {
      await memoryApi.deleteLongTerm(memoryId);
      toast.success('已删除');
      doList();
    } catch (e: any) {
      toast.error('删除失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    onClose();
    setItems([]);
    setQuery('');
    setEditingId(null);
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="长期记忆"
      width={960}
      footer={
        <div className="flex gap-2">
          {editingId && (
            <>
              <Button variant="ghost" onClick={() => setEditingId(null)}>取消编辑</Button>
              <Button variant="primary" onClick={doUpdate} loading={loading}>保存编辑</Button>
            </>
          )}
          {!editingId && <Button onClick={handleClose}>关闭</Button>}
        </div>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Input label="user_id" value={userId} onChange={(e: any) => setUserId(e.target.value)} className="w-40" />
        </div>

        <Tabs
          defaultActiveKey={tab}
          onChange={(k) => { setTab((k as any) || 'list'); setEditingId(null); setExpandedId(null); }}
          tabs={[
            {
              key: 'list',
              label: '浏览',
              onEnter: doList,
              children: (
                <div className="space-y-3">
                  <div className="flex justify-end">
                    <Button variant="ghost" onClick={doList} loading={loading}>
                      刷新
                    </Button>
                  </div>
                  {/* Inline edit row */}
                  {editingId && (
                    <div className="bg-purple-500/5 border border-purple-500/30 rounded-lg p-3 space-y-2">
                      <div className="text-xs text-purple-400 font-medium">正在编辑: {editingId.slice(-12)}</div>
                      <Input label="key（可选）" value={editKey} onChange={(e: any) => setEditKey(e.target.value)} />
                      <Textarea label="content" rows={4} value={editContent} onChange={(e: any) => setEditContent(e.target.value)} />
                      <Textarea label="metadata（JSON）" rows={3} value={editMetaText} onChange={(e: any) => setEditMetaText(e.target.value)} />
                    </div>
                  )}
                  <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
                    <Table columns={columns} data={items} rowKey="id" loading={loading} emptyText="暂无数据，点击刷新" />
                  </div>
                  {/* Expanded row detail panel */}
                  {expandedId && (() => {
                    const item = items.find(i => i.id === expandedId);
                    if (!item) return null;
                    const decay = item.relevance_decay;
                    const decayColor = decay != null ? (decay > 0.7 ? 'text-green-400' : decay > 0.3 ? 'text-yellow-400' : 'text-red-400') : 'text-gray-400';
                    return (
                      <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 space-y-2 text-xs">
                        <div className="grid grid-cols-4 gap-2">
                          <div>
                            <span className="text-gray-500">来源标签:</span>
                            <span className="text-purple-400 ml-1">{item.source_tag || '—'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">信任权重:</span>
                            <span className="text-blue-400 ml-1">{item.trust_weight?.toFixed(2) || '—'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">衰减因子:</span>
                            <span className={`${decayColor} ml-1`}>{decay?.toFixed(4) || '—'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">溯源:</span>
                            <span className="text-gray-300 ml-1">{item.provenance || '—'}</span>
                          </div>
                        </div>
                        <div>
                          <span className="text-gray-500">metadata:</span>
                          <pre className="text-gray-300 mt-1 p-2 bg-dark-hover rounded text-xs overflow-auto max-h-32">
                            {JSON.stringify(item.metadata || {}, null, 2)}
                          </pre>
                        </div>
                        <div className="text-right">
                          <button className="text-blue-400 hover:text-blue-300" onClick={() => setExpandedId(null)}>收起</button>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ),
            },
            {
              key: 'search',
              label: '搜索',
              children: (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="输入关键词（FTS query）..."
                      className="flex-1 h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm"
                      onKeyDown={(e) => e.key === 'Enter' && doSearch()}
                    />
                    <Input
                      label="limit"
                      type="number"
                      value={String(limit)}
                      onChange={(e: any) => setLimit(Number(e.target.value || 10))}
                    />
                    <Button variant="primary" onClick={doSearch} loading={loading}>
                      搜索
                    </Button>
                  </div>
                  <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
                    <Table columns={columns} data={items} rowKey="id" loading={loading} emptyText="暂无结果" />
                  </div>
                  {/* Expanded detail for search tab */}
                  {expandedId && (() => {
                    const item = items.find(i => i.id === expandedId);
                    if (!item) return null;
                    const decay = item.relevance_decay;
                    const decayColor = decay != null ? (decay > 0.7 ? 'text-green-400' : decay > 0.3 ? 'text-yellow-400' : 'text-red-400') : 'text-gray-400';
                    return (
                      <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 space-y-2 text-xs">
                        <div className="grid grid-cols-4 gap-2">
                          <div><span className="text-gray-500">来源标签:</span><span className="text-purple-400 ml-1">{item.source_tag || '—'}</span></div>
                          <div><span className="text-gray-500">信任权重:</span><span className="text-blue-400 ml-1">{item.trust_weight?.toFixed(2) || '—'}</span></div>
                          <div><span className="text-gray-500">衰减因子:</span><span className={`${decayColor} ml-1`}>{decay?.toFixed(4) || '—'}</span></div>
                          <div><span className="text-gray-500">溯源:</span><span className="text-gray-300 ml-1">{item.provenance || '—'}</span></div>
                        </div>
                        <div><span className="text-gray-500">metadata:</span><pre className="text-gray-300 mt-1 p-2 bg-dark-hover rounded text-xs overflow-auto max-h-32">{JSON.stringify(item.metadata || {}, null, 2)}</pre></div>
                        <div className="text-right"><button className="text-blue-400 hover:text-blue-300" onClick={() => setExpandedId(null)}>收起</button></div>
                      </div>
                    );
                  })()}
                </div>
              ),
            },
            {
              key: 'add',
              label: '新增',
              children: (
                <div className="space-y-3">
                  <Input label="key（可选）" value={addKey} onChange={(e: any) => setAddKey(e.target.value)} />
                  <Textarea label="content（必填）" rows={6} value={addContent} onChange={(e: any) => setAddContent(e.target.value)} />
                  <Textarea label="metadata（JSON，可选）" rows={5} value={addMetaText} onChange={(e: any) => setAddMetaText(e.target.value)} />
                  <div className="flex justify-end">
                    <Button variant="primary" onClick={doAdd} loading={loading}>
                      写入
                    </Button>
                  </div>
                </div>
              ),
            },
          ]}
        />
      </div>
    </Modal>
  );
};

export default LongTermMemoryModal;
