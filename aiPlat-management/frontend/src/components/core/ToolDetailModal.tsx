import React from 'react';
import { Modal, Button } from '../ui';

interface ToolDetailModalProps {
  open: boolean;
  tool: {
    name: string;
    description?: string;
    category?: string;
    config?: Record<string, unknown>;
    parameters?: Record<string, unknown>;
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
  if (!tool) return null;

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
      </div>
    </Modal>
  );
};

export default ToolDetailModal;