import React, { useCallback, useEffect, useState } from 'react';
import { RotateCcw, FileDiff, RefreshCw, FolderOpen } from 'lucide-react';
import { motion } from 'framer-motion';
import { Button, Input, Modal, Table, toast, toastGateError } from '../../../components/ui';
import { checkpointApi } from '../../../services';

interface CheckpointItem {
  checkpoint_id?: string;
  id?: string;
  path?: string;
  session_id?: string;
  created_at?: number;
  timestamp?: number;
  size?: number;
  [key: string]: any;
}

const FileCheckpoints: React.FC = () => {
  const [items, setItems] = useState<CheckpointItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [sessionFilter, setSessionFilter] = useState('');
  const [pathFilter, setPathFilter] = useState('');
  const [detailModal, setDetailModal] = useState<{ open: boolean; data: any }>({ open: false, data: null });
  const [detailLoading, setDetailLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await checkpointApi.list({
        session_id: sessionFilter || undefined,
        path: pathFilter || undefined,
      });
      setItems(res.items || []);
    } catch (e) {
      toastGateError(e as any);
    } finally {
      setLoading(false);
    }
  }, [sessionFilter, pathFilter]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleView = async (item: CheckpointItem) => {
    const cpId = item.checkpoint_id || item.id || '';
    if (!cpId) return;
    setDetailLoading(true);
    setDetailModal({ open: true, data: null });
    try {
      const data = await checkpointApi.get(cpId, item.session_id || '');
      setDetailModal({ open: true, data });
    } catch (e) {
      toastGateError(e as any);
      setDetailModal({ open: false, data: null });
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRestore = async (item: CheckpointItem) => {
    const cpId = item.checkpoint_id || item.id || '';
    if (!cpId) return;
    if (!window.confirm(`恢复文件到 checkpoint 时点？\n${item.path || ''}`)) return;
    setRestoring(cpId);
    try {
      const res = await checkpointApi.restore(cpId, item.session_id || '');
      toast.success(res?.message || '文件已恢复');
    } catch (e) {
      toastGateError(e as any);
    } finally {
      setRestoring(null);
    }
  };

  const fmtTime = (ts?: number) => {
    if (!ts) return '-';
    try {
      const d = ts > 1e12 ? new Date(ts) : new Date(ts * 1000);
      return d.toLocaleString();
    } catch {
      return String(ts);
    }
  };

  return (
    <div className="p-6">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-xl font-semibold mb-1">文件 Checkpoint</h1>
        <p className="text-sm text-gray-500">
          文件写/编辑覆盖前自动捕获的物理安全网（Hermes Layer 1）——列出、查看内容、一键恢复。
        </p>
      </motion.div>

      <div className="flex items-center gap-3 mb-4">
        <Input
          placeholder="session_id 过滤"
          value={sessionFilter}
          onChange={(e) => setSessionFilter(e.target.value)}
          className="w-56"
        />
        <Input
          placeholder="路径过滤"
          value={pathFilter}
          onChange={(e) => setPathFilter(e.target.value)}
          className="w-64"
        />
        <Button variant="outline" onClick={fetchList} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> 刷新
        </Button>
      </div>

      <Table>
        <thead>
          <tr>
            <th>文件路径</th>
            <th>session</th>
            <th>创建时间</th>
            <th>大小</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && !loading && (
            <tr><td colSpan={5} className="text-center text-gray-400 py-6">暂无 checkpoint</td></tr>
          )}
          {items.map((item, idx) => (
            <tr key={item.checkpoint_id || item.id || idx}>
              <td className="font-mono text-xs">{item.path || '-'}</td>
              <td className="text-xs">{item.session_id || '-'}</td>
              <td className="text-xs">{fmtTime(item.created_at ?? item.timestamp)}</td>
              <td className="text-xs">{item.size ? `${(item.size / 1024).toFixed(1)}KB` : '-'}</td>
              <td>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleView(item)}>
                    <FileDiff className="w-3.5 h-3.5 mr-1" /> 查看
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => handleRestore(item)} disabled={restoring === (item.checkpoint_id || item.id)}>
                    <RotateCcw className="w-3.5 h-3.5 mr-1" /> {restoring === (item.checkpoint_id || item.id) ? '恢复中…' : '恢复'}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      <Modal
        open={detailModal.open}
        onClose={() => setDetailModal({ open: false, data: null })}
        title="Checkpoint 内容"
        width="xl"
      >
        <div className="p-4 space-y-3">
          {detailLoading && <p className="text-gray-400">加载中…</p>}
          {detailModal.data && (
            <>
              <div className="text-xs text-gray-500 flex items-center gap-2">
                <FolderOpen className="w-3.5 h-3.5" />
                <span className="font-mono">{detailModal.data.path || 'unknown path'}</span>
              </div>
              <pre className="bg-gray-900 text-green-300 text-xs p-3 rounded overflow-auto max-h-96 whitespace-pre-wrap">
                {typeof detailModal.data.content === 'string'
                  ? detailModal.data.content
                  : JSON.stringify(detailModal.data, null, 2)}
              </pre>
              {detailModal.data.content && (
                <Button size="sm" variant="primary" onClick={() => handleRestore(detailModal.data)}>
                  <RotateCcw className="w-3.5 h-3.5 mr-1" /> 恢复此 checkpoint
                </Button>
              )}
            </>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default FileCheckpoints;
