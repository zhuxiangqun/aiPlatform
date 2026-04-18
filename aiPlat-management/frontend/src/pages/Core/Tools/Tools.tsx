import React, { useState, useEffect } from 'react';
import { RotateCw, Wrench, Play, Settings } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Button } from '../../../components/ui';
import { ToolDetailModal, ExecuteToolModal, EditToolConfigModal } from '../../../components/core';
import { toolApi } from '../../../services';
import type { ToolInfo } from '../../../services';

const categoryConfig: Record<string, { color: string; text: string }> = {
  general: { color: 'bg-dark-hover text-gray-300 border-dark-border', text: '通用' },
  search: { color: 'bg-blue-50 text-blue-300 border-blue-200', text: '搜索' },
  calculation: { color: 'bg-green-50 text-green-300 border-green-200', text: '计算' },
  file_operations: { color: 'bg-amber-50 text-amber-300 border-amber-200', text: '文件操作' },
  code_execution: { color: 'bg-purple-50 text-purple-300 border-purple-200', text: '代码执行' },
  api: { color: 'bg-cyan-50 text-cyan-300 border-cyan-200', text: 'API调用' },
  data: { color: 'bg-rose-50 text-rose-300 border-rose-200', text: '数据处理' },
};

const Tools: React.FC = () => {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailTool, setDetailTool] = useState<ToolInfo | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [executeTool, setExecuteTool] = useState<ToolInfo | null>(null);
  const [executeOpen, setExecuteOpen] = useState(false);
  const [editTool, setEditTool] = useState<ToolInfo | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  const fetchTools = async () => {
    setLoading(true);
    try {
      const res = await toolApi.list();
      setTools(res.tools || []);
    } catch (error) {
      console.error('Failed to fetch tools:', error);
      setTools([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTools();
  }, []);

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: ToolInfo) => (
        <button
          onClick={() => { setDetailTool(record); setDetailOpen(true); }}
          className="text-primary hover:text-primary-hover font-medium"
        >
          {name}
        </button>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (desc: string) => <span className="text-gray-400">{desc || '-'}</span>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (category: string) => {
        const cfg = categoryConfig[category] || { color: 'bg-dark-hover text-gray-300 border-dark-border', text: category };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}`}>
            {cfg.text}
          </span>
        );
      },
    },
    {
      title: '调用次数',
      key: 'call_count',
      width: 100,
      render: (_: unknown, record: ToolInfo) => (
        <span className="text-gray-300">{record.stats?.call_count ?? 0}</span>
      ),
    },
    {
      title: '成功率',
      key: 'success_rate',
      width: 100,
      render: (_: unknown, record: ToolInfo) => {
        if (!record.stats || record.stats.call_count === 0) return <span className="text-gray-500">-</span>;
        const rate = ((record.stats.success_count / record.stats.call_count) * 100).toFixed(1);
        return <span className="text-green-300">{rate}%</span>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: ToolInfo) => {
        const isProtected = Boolean((record as any)?.protected === true);
        return (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => { setExecuteTool(record); setExecuteOpen(true); }}
            className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors"
            title="执行"
          >
            <Play className="w-4 h-4" />
          </button>
          {!isProtected && (
            <button
              onClick={() => { setEditTool(record); setEditOpen(true); }}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="编辑配置"
            >
              <Settings className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => { setDetailTool(record); setDetailOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="详情"
          >
            <Wrench className="w-4 h-4" />
          </button>
        </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">Tool管理</h1>
          <p className="text-sm text-gray-400 mt-1">查看和管理核心能力层注册的工具</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            icon={<RotateCw className="w-4 h-4" />}
            onClick={fetchTools}
            loading={loading}
          >
            刷新
          </Button>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        {tools.length === 0 && !loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Wrench className="w-12 h-12 mb-4 text-gray-500" />
            <p className="text-sm">暂无Tool数据</p>
            <p className="text-xs text-gray-500 mt-1">工具由系统自动注册，无需手动添加</p>
          </div>
        ) : (
          <Table
            columns={columns}
            data={tools}
            rowKey="name"
            loading={loading}
            emptyText="暂无Tool数据"
          />
        )}
      </motion.div>

      <ToolDetailModal
        open={detailOpen}
        tool={detailTool}
        onClose={() => setDetailOpen(false)}
      />

      <ExecuteToolModal
        open={executeOpen}
        tool={executeTool}
        onClose={() => setExecuteOpen(false)}
      />

      <EditToolConfigModal
        open={editOpen}
        tool={editTool}
        onClose={() => setEditOpen(false)}
        onSuccess={fetchTools}
      />
    </div>
  );
};

export default Tools;
