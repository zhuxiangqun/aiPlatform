import React, { useMemo, useState } from 'react';
import { Modal, Button, Input, Table, Textarea, toast, Tabs } from '../ui';
import { memoryApi, type LongTermMemoryItem } from '../../services';

interface LongTermMemoryModalProps {
  open: boolean;
  onClose: () => void;
}

const LongTermMemoryModal: React.FC<LongTermMemoryModalProps> = ({ open, onClose }) => {
  const [tab, setTab] = useState<'search' | 'add'>('search');

  const [userId, setUserId] = useState('system');
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<LongTermMemoryItem[]>([]);

  const [addKey, setAddKey] = useState('');
  const [addContent, setAddContent] = useState('');
  const [addMetaText, setAddMetaText] = useState('{}');

  const columns = useMemo(
    () => [
      {
        title: 'id',
        key: 'id',
        width: 180,
        render: (_: unknown, r: LongTermMemoryItem) => (
          <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{r.id}</code>
        ),
      },
      {
        title: 'key',
        key: 'key',
        width: 160,
        render: (_: unknown, r: LongTermMemoryItem) => <span className="text-gray-300">{r.key || '-'}</span>,
      },
      {
        title: 'content',
        key: 'content',
        render: (_: unknown, r: LongTermMemoryItem) => (
          <div className="text-sm text-gray-300 whitespace-pre-wrap break-words">{String(r.content || '').slice(0, 240)}</div>
        ),
      },
      {
        title: 'created_at',
        key: 'created_at',
        width: 120,
        render: (_: unknown, r: LongTermMemoryItem) => <span className="text-gray-400">{r.created_at ?? '-'}</span>,
      },
    ],
    [],
  );

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
      setTab('search');
    } catch (e: any) {
      toast.error('写入失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    onClose();
    setItems([]);
    setQuery('');
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="长期记忆"
      width={900}
      footer={<Button onClick={handleClose}>关闭</Button>}
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input label="user_id（可选；默认 system）" value={userId} onChange={(e: any) => setUserId(e.target.value)} />
          <div className="text-xs text-gray-500 flex items-end pb-2">
            Long-term memory 基于 FTS/LIKE 搜索（后端自动降级）。
          </div>
        </div>

        <Tabs
          defaultActiveKey={tab}
          onChange={(k) => setTab((k as any) || 'search')}
          tabs={[
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
