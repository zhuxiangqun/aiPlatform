import React, { useState, useEffect } from 'react';
import { Card, Button } from '../ui';
import { RefreshCw, ChevronLeft, ChevronRight, Trash2 } from 'lucide-react';

interface ColumnConfig {
  key: string;
  label: string;
  sortable?: boolean;
  type?: string;
  format?: string;
  actions?: { label: string; action: string; param?: string; confirm?: boolean }[];
  badge_map?: Record<string, string>;
}

interface PaginationConfig {
  page_size: number;
  page_size_options?: number[];
}

interface SortConfig {
  field: string;
  order: 'asc' | 'desc';
}

interface StageConfig {
  columns?: ColumnConfig[];
  pagination?: PaginationConfig;
  sort?: SortConfig;
  batch_actions?: { label: string; action: string; confirm?: boolean }[];
  empty_hint?: string;
}

interface Props {
  config: StageConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  projectId?: string;
  onNext?: (result: any) => void;
}

export const DataTableStage: React.FC<Props> = ({ config, onExecute, skill, projectId = '', onNext }) => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [sortField, setSortField] = useState(config.sort?.field);
  const [sortOrder, setSortOrder] = useState(config.sort?.order || 'desc');
  const pageSize = config.pagination?.page_size || 20;

  useEffect(() => {
    setLoading(true);
    onExecute(skill, { page, page_size: pageSize, sort_field: sortField, sort_order: sortOrder })
      .then((res: any) => {
        setData(Array.isArray(res) ? res : (res?.items || res?.data || []));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, sortField, sortOrder]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortOrder(o => o === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const handleAction = async (action: string, item?: any) => {
    if (action === 'delete_record' && item) {
      if (window.confirm('确认删除？')) {
        await onExecute(skill, { action: 'delete', record_id: item.id || item.task_id });
        setData(prev => prev.filter(d => (d.id || d.task_id) !== (item.id || item.task_id)));
      }
    } else if (action === 'view_result' && item) {
      onNext?.(item);
    }
  };

  const renderBadge = (value: string, colorMap?: Record<string, string>) => {
    const colors: Record<string, string> = { success: 'bg-green-500/20 text-green-300', info: 'bg-blue-500/20 text-blue-300', error: 'bg-red-500/20 text-red-300', warning: 'bg-amber-500/20 text-amber-300' };
    const mapped = colorMap?.[value];
    return <span className={`px-1.5 py-0.5 rounded text-[10px] ${mapped ? colors[mapped] || '' : 'bg-dark-hover text-gray-300'}`}>{value}</span>;
  };

  return (
    <Card className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">{data.length} 条记录</span>
        <button onClick={() => { setLoading(true); onExecute(skill, { page, page_size: pageSize }).then((res: any) => { setData(Array.isArray(res) ? res : (res?.items || [])); }).finally(() => setLoading(false)); }}
          className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-1">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> 刷新
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-dark-border text-gray-500">
              {config.columns?.map(c => (
                <th key={c.key} className={`text-left py-1.5 px-2 ${c.sortable ? 'cursor-pointer hover:text-gray-300' : ''}`}
                  onClick={() => c.sortable && handleSort(c.key)}>
                  {c.label} {c.sortable && sortField === c.key && (sortOrder === 'asc' ? '↑' : '↓')}
                </th>
              ))}
              {(config.columns?.some(c => c.actions?.length)) && <th className="text-right py-1.5 px-2">操作</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={99} className="py-4 text-center text-gray-500">加载中...</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan={99} className="py-4 text-center text-gray-500">{config.empty_hint || '暂无数据'}</td></tr>
            ) : data.map((item, i) => (
              <tr key={i} className="border-b border-dark-border/50 text-gray-300">
                {config.columns?.map(c => (
                  <td key={c.key} className="py-1.5 px-2">
                    {c.type === 'badge' ? renderBadge(item[c.key], c.badge_map) : c.format === 'datetime' && item[c.key] ? new Date(item[c.key] * 1000).toLocaleString() : (item[c.key] ?? '—')}
                  </td>
                ))}
                {config.columns?.some(c => c.actions?.length) && (
                  <td className="py-1.5 px-2 text-right">
                    {config.columns?.find(c => c.actions?.length)?.actions?.map(a => (
                      <button key={a.action} onClick={() => handleAction(a.action, item)}
                        className="text-[10px] text-blue-400 hover:text-blue-300 ml-1.5">
                        {a.label}
                      </button>
                    ))}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-[10px] text-gray-500">
        <span>第 {page * pageSize + 1}-{Math.min((page + 1) * pageSize, data.length || 0)} 条</span>
        <div className="flex gap-1">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="p-1 rounded hover:bg-dark-hover disabled:opacity-30"><ChevronLeft className="w-3 h-3" /></button>
          <button onClick={() => setPage(p => p + 1)} disabled={data.length < pageSize}
            className="p-1 rounded hover:bg-dark-hover disabled:opacity-30"><ChevronRight className="w-3 h-3" /></button>
        </div>
      </div>
    </Card>
  );
};
