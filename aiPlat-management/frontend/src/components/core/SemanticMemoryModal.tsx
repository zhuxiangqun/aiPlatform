import React, { useState } from 'react';
import { Modal, Button, Input, Table, toast } from '../ui';
import { memoryApi, type SemanticMemoryItem } from '../../services';

interface SemanticMemoryModalProps {
  open: boolean;
  onClose: () => void;
}

const SemanticMemoryModal: React.FC<SemanticMemoryModalProps> = ({ open, onClose }) => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<SemanticMemoryItem[]>([]);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await memoryApi.searchSemantic({ query: query.trim(), limit: 20 });
      setItems(res.items || []);
    } catch (e: any) {
      toast.error('搜索失败', String(e?.message || ''));
    } finally { setLoading(false); }
  };

  const doForget = async (key: string) => {
    if (!confirm(`软删除 "${key}"？可通过恢复功能找回。`)) return;
    setLoading(true);
    try {
      await memoryApi.forgetSemantic(key);
      toast.success(`已软删除: ${key}`);
      doSearch();
    } catch (e: any) {
      toast.error('删除失败', String(e?.message || ''));
    } finally { setLoading(false); }
  };

  const doRecover = async (key: string) => {
    setLoading(true);
    try {
      await memoryApi.recoverSemantic(key);
      toast.success(`已恢复: ${key}`);
      doSearch();
    } catch (e: any) {
      toast.error('恢复失败', String(e?.message || ''));
    } finally { setLoading(false); }
  };

  const columns = [
    {
      title: 'key',
      key: 'key',
      width: 160,
      render: (_: unknown, r: SemanticMemoryItem) => (
        <code
          className={`text-xs px-1.5 py-0.5 rounded cursor-pointer hover:underline ${r.is_deleted ? 'text-red-400/50 bg-red-500/10' : 'bg-dark-hover text-gray-200'}`}
          onClick={() => setExpandedKey(expandedKey === r.key ? null : r.key)}
        >
          {r.key || '-'}
        </code>
      ),
    },
    {
      title: 'content',
      key: 'content',
      render: (_: unknown, r: SemanticMemoryItem) => (
        <div className="text-sm text-gray-300 whitespace-pre-wrap break-words">
          {String(r.content || '').slice(0, 150)}
          {String(r.content || '').length > 150 && <span className="text-xs text-blue-400 ml-1">更多</span>}
        </div>
      ),
    },
    {
      title: '标签',
      key: 'source_tag',
      width: 80,
      render: (_: unknown, r: SemanticMemoryItem) => (
        <span className="text-xs text-purple-400">{r.source_tag || '-'}</span>
      ),
    },
    {
      title: '状态',
      key: 'is_deleted',
      width: 70,
      render: (_: unknown, r: SemanticMemoryItem) => (
        <span className={`text-xs ${r.is_deleted ? 'text-red-400' : 'text-green-400'}`}>
          {r.is_deleted ? '已删除' : '活跃'}
        </span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, r: SemanticMemoryItem) => (
        <div className="flex gap-1">
          {r.is_deleted ? (
            <button className="text-xs text-blue-400 hover:text-blue-300 px-1 py-0.5" onClick={() => doRecover(r.key)}>恢复</button>
          ) : (
            <button className="text-xs text-red-400 hover:text-red-300 px-1 py-0.5" onClick={() => doForget(r.key)}>删除</button>
          )}
        </div>
      ),
    },
  ];

  const handleClose = () => {
    onClose();
    setItems([]);
    setQuery('');
    setExpandedKey(null);
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="语义记忆"
      width={860}
      footer={<Button onClick={handleClose}>关闭</Button>}
    >
      <div className="space-y-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索语义记忆（向量+关键词）..."
            className="flex-1 h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm"
            onKeyDown={(e) => e.key === 'Enter' && doSearch()}
          />
          <Button variant="primary" onClick={doSearch} loading={loading}>搜索</Button>
        </div>

        {/* Expanded detail panel */}
        {expandedKey && (() => {
          const item = items.find(i => i.key === expandedKey);
          if (!item) return null;
          return (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 space-y-2 text-xs">
              <div className="grid grid-cols-4 gap-2">
                <div><span className="text-gray-500">来源:</span><span className="text-purple-400 ml-1">{item.source_tag || '—'}</span></div>
                <div><span className="text-gray-500">信任:</span><span className="text-blue-400 ml-1">{item.trust_weight?.toFixed(2) || '—'}</span></div>
                <div><span className="text-gray-500">访问次数:</span><span className="text-gray-300 ml-1">{item.access_count ?? '—'}</span></div>
                <div><span className="text-gray-500">溯源:</span><span className="text-gray-300 ml-1">{item.provenance || '—'}</span></div>
              </div>
              <div className="text-gray-300 whitespace-pre-wrap max-h-48 overflow-auto">{item.content}</div>
              {item.metadata && Object.keys(item.metadata).length > 0 && (
                <div><span className="text-gray-500">metadata:</span><pre className="text-gray-300 mt-1 p-2 bg-dark-hover rounded text-xs overflow-auto max-h-32">{JSON.stringify(item.metadata, null, 2)}</pre></div>
              )}
              <div className="text-right"><button className="text-blue-400 hover:text-blue-300" onClick={() => setExpandedKey(null)}>收起</button></div>
            </div>
          );
        })()}

        <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
          <Table columns={columns} data={items} rowKey="key" loading={loading} emptyText="输入关键词搜索语义记忆" />
        </div>
        <div className="text-xs text-gray-500">
          语义记忆：长期向量存储。删除 = 软删除（可恢复）。恢复 = 重新激活。
        </div>
      </div>
    </Modal>
  );
};

export default SemanticMemoryModal;
