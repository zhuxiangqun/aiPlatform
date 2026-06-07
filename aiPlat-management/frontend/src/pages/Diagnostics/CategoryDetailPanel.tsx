import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, toast } from '../../components/ui';
import ExecutionViewer from '../../components/ExecutionViewer/ExecutionViewer';
import type { ExecutionNode } from '../../components/ExecutionViewer/types';
import { useLiveEvents } from '../../hooks/useLiveEvents';

interface Props {
  open: boolean;
  runId: string;
  categoryKey: string;
  categoryName: string;
  categoryResult: any;
  onClose: () => void;
}

const mapStatus = (s: string): ExecutionNode['status'] => {
  if (s === 'pass' || s === 'ok') return 'completed';
  if (s === 'warn' || s === 'warning') return 'warning';
  if (s === 'fail' || s === 'error') return 'failed';
  return 'idle';
};

const CategoryDetailPanel: React.FC<Props> = ({ open, runId: _runId, categoryKey, categoryName, categoryResult, onClose }) => {
  const [liveRunId, setLiveRunId] = useState('');
  const [runningFetch, setRunningFetch] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const ranRef = useRef(false);

  // Trigger single-category diagnostic on open
  useEffect(() => {
    if (!open || !categoryKey || ranRef.current) return;
    ranRef.current = true;
    setLiveRunId('');
    setFetchError('');
    setRunningFetch(true);

    (async () => {
      try {
        const res = await fetch('/api/core/diagnostics/run-single', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category: categoryKey }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        const data = await res.json();
        setLiveRunId(data.run_id || '');
      } catch (e: any) {
        setFetchError(e?.message || String(e));
        toast.error('执行失败', e?.message || e);
      } finally {
        setRunningFetch(false);
      }
    })();

    return () => { ranRef.current = false; };
  }, [open, categoryKey]);

  // Subscribe to SSE when we have a live run_id
  const { events: allEvents, status: sseStatus } = useLiveEvents(open && liveRunId ? liveRunId : null);

  const catEvents = useMemo(() => {
    return allEvents.filter((e: any) => !e.category || e.category === categoryKey);
  }, [allEvents, categoryKey]);

  // Fallback: if SSE events are empty and run completed, use cached result items
  const useFallback = sseStatus === 'done' || sseStatus === 'error' || (sseStatus === 'disconnected' && liveRunId && !runningFetch);

  const nodes: ExecutionNode[] = useMemo(() => {
    if (catEvents.length > 0) {
      const result: ExecutionNode[] = [];
      const seen = new Set<string>();

      for (const evt of catEvents) {
        if (evt.type === 'check_started') {
          result.push({
            id: `${categoryKey}_start`,
            type: 'diag',
            name: `${categoryName} · 检查中`,
            group: categoryKey,
            status: 'running',
            color: '#3b82f6',
          });
        } else if (evt.type === 'check_done') {
          result.push({
            id: `${categoryKey}_done`,
            type: 'diag',
            name: `${categoryName} · ${evt.status === 'pass' ? '通过' : evt.status === 'warn' ? '警告' : '失败'}`,
            group: categoryKey,
            status: mapStatus(evt.status || 'pass'),
          });
        } else if (evt.type === 'check_progress') {
          const skillName = (evt as any).skill;
          if (skillName) {
            const sk = (evt as any).skill;
            if (!seen.has(sk.name)) {
              seen.add(sk.name);
              result.push({
                id: `${categoryKey}_${sk.name}`,
                type: 'diag',
                name: sk.name.slice(0, 40),
                group: categoryKey,
                status: sk.errors > 0 ? 'warning' : 'completed',
              });
            }
          }
        }
      }
      return result;
    }

    // Fallback: build from categoryResult items
    if (useFallback || runningFetch) {
      const items = categoryResult?.items || [];
      if (items.length > 0) {
        return items.map((item: any, i: number) => ({
          id: `${categoryKey}_item_${i}`,
          type: 'diag',
          name: String(item.check || '检测项').slice(0, 40),
          group: categoryKey,
          status: (String(item.result || '').includes('❌') ? 'failed' :
                   String(item.result || '').includes('⚠') ? 'warning' : 'completed') as ExecutionNode['status'],
        }));
      }
    }
    return [];
  }, [catEvents, categoryKey, categoryName, categoryResult, useFallback, runningFetch]);

  const running = runningFetch || sseStatus === 'connecting' || sseStatus === 'streaming';

  return (
    <Modal open={open} onClose={onClose} title={`${categoryName} · 执行中`} width={900}>
      <div className="space-y-3" style={{ minHeight: '400px' }}>
        {fetchError ? (
          <div className="text-center py-16 text-red-400 flex flex-col items-center gap-3">
            <span className="text-3xl">❌</span>
            <p className="text-sm">执行失败</p>
            <p className="text-[10px] text-gray-500 max-w-md">{fetchError}</p>
            <p className="text-[10px] text-gray-600">请确保 aiPlat-core 后端（端口 8002）已重启</p>
          </div>
        ) : running && nodes.length === 0 ? (
          <div className="text-center py-16 text-gray-400 flex flex-col items-center gap-3">
            <div className="animate-spin text-3xl">⚙</div>
            <p className="text-sm">正在执行 {categoryName} 诊断...</p>
            <p className="text-[10px] text-gray-600">通过 SSE 接收实时执行事件</p>
          </div>
        ) : nodes.length > 0 ? (
          <ExecutionViewer
            nodes={nodes}
            title=""
            running={running}
            height={300}
          />
        ) : (
          <div className="text-center py-12 text-gray-500 text-sm">该类别暂无执行数据</div>
        )}
        {/* Summary footer */}
        {categoryResult && (
          <div className="flex items-center gap-4 bg-dark-bg rounded-lg p-3 text-xs">
            <span className={
              categoryResult.status === 'pass' ? 'text-green-400' :
              categoryResult.status === 'warn' ? 'text-yellow-400' : 'text-red-400'
            }>
              {categoryResult.status === 'pass' ? '✅ 通过' :
               categoryResult.status === 'warn' ? '⚠️ 警告' : '❌ 失败'}
            </span>
            {categoryResult.score != null && <span className="text-gray-300">评分: {categoryResult.score}</span>}
            {categoryResult.items && <span className="text-gray-500">{categoryResult.items.length} 检测项</span>}
          </div>
        )}
      </div>
    </Modal>
  );
};

export default CategoryDetailPanel;
