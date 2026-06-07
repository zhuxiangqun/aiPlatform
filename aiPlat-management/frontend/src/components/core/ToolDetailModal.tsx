import React, { useState } from 'react';
import { Modal, Button, toast } from '../ui';
import { toolApi } from '../../services';
import { toastGateError } from '../ui';
import { Clock } from 'lucide-react';

interface ToolDetailModalProps {
  open: boolean;
  tool: {
    name: string;
    description?: string;
    category?: string;
    config?: Record<string, unknown>;
    parameters?: Record<string, unknown>;
    protected?: boolean;
    scope?: string;
    stats?: {
      call_count: number;
      success_count: number;
      error_count: number;
      total_latency: number;
      avg_latency: number;
    };
  } | null;
  onClose: () => void;
}

const ToolDetailModal: React.FC<ToolDetailModalProps> = ({ open, tool, onClose }) => {
  const [signing, setSigning] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyItems, setHistoryItems] = useState<any[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  const fetchHistory = async () => {
    if (!tool?.name) return;
    setHistoryLoading(true);
    setHistoryOpen(true);
    try {
      const res = await fetch(`/api/core/syscalls/events?name=${tool.name}&kind=tool&limit=10&offset=0`);
      const data = await res.json();
      setHistoryItems(data.items || []);
    } catch { setHistoryItems([]); }
    finally { setHistoryLoading(false); }
  };
  const [signKey, setSignKey] = useState('');
  const [signResult, setSignResult] = useState<string | null>(null);

  if (!tool) return null;

  const handleSign = async () => {
    if (!tool.name || !signKey.trim()) return;
    setSigning(true);
    setSignResult(null);
    try {
      const res = await toolApi.sign(tool.name, { private_key: signKey.trim() });
      setSignResult(res.signature);
      toast.success('工具签名成功');
      setSignKey('');
    } catch (e: any) {
      toastGateError(e, '签名失败');
      setSignResult(null);
    } finally {
      setSigning(false);
    }
  };

  const configStr = tool.config && Object.keys(tool.config).length > 0
    ? JSON.stringify(tool.config, null, 2)
    : null;
  const paramsStr = tool.parameters && Object.keys(tool.parameters).length > 0
    ? JSON.stringify(tool.parameters, null, 2)
    : null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={tool.name}
      width={640}
      footer={
        <Button onClick={onClose}>关闭</Button>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-gray-400 mb-1">名称</div>
            <div className="text-sm text-gray-100 font-medium">{tool.name}</div>
          </div>
          <div>
            <div className="text-sm text-gray-400 mb-1">分类</div>
            <div className="text-sm text-gray-100">{tool.category || '-'}</div>
              </div>
            </div>
            <Button variant="secondary" size="sm" icon={<Clock className="w-3 h-3" />}
              onClick={fetchHistory} loading={historyLoading} className="mt-3">
              执行历史
            </Button>
            {historyOpen && (
              <div className="mt-3 max-h-48 overflow-y-auto border border-dark-border rounded-lg">
                {historyItems.length === 0 ? (
                  <div className="text-xs text-gray-500 p-3 text-center">暂无执行记录</div>
                ) : (
                  historyItems.map((item: any, i: number) => (
                    <div key={i} className="flex items-center justify-between px-3 py-1.5 text-xs border-b border-dark-border last:border-b-0">
                      <span className={`font-mono text-gray-300 truncate flex-1`}>{item.run_id?.slice(0, 20) || '?'}</span>
                      <span className={`px-1.5 py-0.5 rounded ${item.status === 'success' ? 'bg-green-900/30 text-green-300' : item.status === 'failed' ? 'bg-red-900/30 text-red-300' : 'bg-dark-hover text-gray-400'}`}>
                        {item.status || '?'}
                      </span>
                      <span className="text-gray-500 ml-2">{item.duration_ms != null ? `${item.duration_ms.toFixed(0)}ms` : '-'}</span>
                    </div>
                  ))
                )}
              </div>
            )}

        <div>
          <div className="text-sm text-gray-400 mb-1">描述</div>
          <div className="text-sm text-gray-300">{tool.description || '暂无描述'}</div>
        </div>

        {tool.stats && (
          <div>
            <div className="text-sm text-gray-400 mb-2">调用统计</div>
            <div className="grid grid-cols-4 gap-3">
              <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
                <div className="text-lg font-semibold text-gray-100">{tool.stats.call_count}</div>
                <div className="text-xs text-gray-400">调用次数</div>
              </div>
              <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
                <div className="text-lg font-semibold text-green-300">{tool.stats.success_count}</div>
                <div className="text-xs text-gray-400">成功次数</div>
              </div>
              <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
                <div className="text-lg font-semibold text-red-300">{tool.stats.error_count}</div>
                <div className="text-xs text-gray-400">失败次数</div>
              </div>
              <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
                <div className="text-lg font-semibold text-blue-300">{tool.stats.avg_latency.toFixed(1)}ms</div>
                <div className="text-xs text-gray-400">平均延迟</div>
              </div>
            </div>
          </div>
        )}

        {paramsStr && (
          <div>
            <div className="text-sm text-gray-400 mb-1">参数 Schema</div>
            <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto" style={{ maxHeight: 200 }}>
              {paramsStr}
            </pre>
          </div>
        )}

        {configStr && (
          <div>
            <div className="text-sm text-gray-400 mb-1">配置</div>
            <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto" style={{ maxHeight: 200 }}>
              {configStr}
            </pre>
          </div>
        )}

        {!(tool.protected === true || tool.scope === 'engine') && (
        <div>
          <div className="text-sm text-gray-400 mb-2">签名</div>
          {signResult ? (
            <div className="flex items-center gap-2 text-green-400 text-xs">
              <span>✓</span>
              <span className="font-mono">{signResult.slice(0, 16)}...</span>
              <button onClick={() => setSignResult(null)} className="text-gray-500 hover:text-gray-300 ml-2">重新签名</button>
            </div>
          ) : (
            <div className="flex items-start gap-2">
              <textarea
                className="flex-1 h-14 px-3 py-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
                placeholder="粘贴 Ed25519 私钥 PEM"
                value={signKey}
                onChange={(e) => setSignKey(e.target.value)}
              />
              <div className="flex flex-col gap-1">
                <button
                  className="px-3 py-1.5 rounded text-xs bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
                  onClick={handleSign}
                  disabled={!signKey.trim() || signing}
                >
                  {signing ? '签名中...' : '签名'}
                </button>
              </div>
            </div>
          )}
        </div>
        )}
      </div>
    </Modal>
  );
};

export default ToolDetailModal;