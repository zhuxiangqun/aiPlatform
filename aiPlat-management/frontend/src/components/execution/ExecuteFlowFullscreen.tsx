import React, { useEffect, useMemo, useState } from 'react';
import { Button } from '../ui';
import ExecutionViewer, { StructuredDetail } from '../ExecutionViewer/ExecutionViewer';
import { VERDICT_BADGE_CLASS, type RunVerdict } from './runVerdict';

type Props = {
  open: boolean;
  runId: string;
  title: string;
  verdict?: RunVerdict | null;
  status?: string;
  running?: boolean;
  onClose: () => void;
  /** Stop in-flight execution (shown next to 关闭 when provided). */
  onStop?: () => void | Promise<void>;
  stopping?: boolean;
  onLiveStatusChange?: (status: 'disconnected' | 'connecting' | 'streaming' | 'done' | 'error') => void;
  /** Optional bottom summary (result text / error). */
  footer?: React.ReactNode;
};

function isSkillSessionRoot(node: any): boolean {
  if (!node) return false;
  const t = String(node.type || '').toLowerCase();
  const role = String(node.details?.role || '');
  const sem = String(node.details?.semanticName || '');
  if (sem === 'skill_start' || sem === 'skill_end') return true;
  if (role === 'container' && (t === 'skill' || /Skill ·/i.test(String(node.name || '')))) return true;
  // Standalone skill work root (no parent) — same as主路径 chip
  if (t === 'skill' && !node.parentId) return true;
  return false;
}

/**
 * Agent-aligned fullscreen execution flow overlay.
 * Single detail surface in the footer — ExecutionViewer uses detailMode=none.
 */
const ExecuteFlowFullscreen: React.FC<Props> = ({
  open,
  runId,
  title,
  verdict,
  status,
  running,
  onClose,
  onStop,
  stopping,
  onLiveStatusChange,
  footer,
}) => {
  const [selectedNode, setSelectedNode] = useState<any>(null);

  useEffect(() => {
    setSelectedNode(null);
  }, [runId, open]);

  // Skill session root duplicates title + RunVerdictBanner error — skip
  const showNodeDetail = useMemo(() => {
    if (!selectedNode) return false;
    if (isSkillSessionRoot(selectedNode) && footer) return false;
    return true;
  }, [selectedNode, footer]);

  const hasFooter = !!footer || showNodeDetail;
  const height = Math.max(240, (typeof window !== 'undefined' ? window.innerHeight : 800) - (hasFooter ? 320 : 100));

  if (!open || !runId) return null;

  return (
    <div className="fixed inset-0 z-[60] bg-dark-bg flex flex-col">
      <div className="h-10 flex items-center justify-between px-4 border-b border-dark-border bg-dark-card flex-shrink-0">
        <span className="text-sm font-medium text-gray-200">▶ {title}</span>
        <div className="flex items-center gap-2">
          {verdict && (
            <span className={`text-xs px-2 py-0.5 rounded ${VERDICT_BADGE_CLASS[verdict.tone]}`} title={status}>
              {verdict.label}
            </span>
          )}
          {status ? <span className="text-[10px] text-gray-500 font-mono hidden sm:inline">{status}</span> : null}
          {onStop ? (
            <Button
              variant="danger"
              onClick={() => { void onStop(); }}
              loading={!!stopping}
              disabled={!running && !['running', 'accepted', 'queued'].includes(String(status || '').toLowerCase())}
              title={running || ['running', 'accepted', 'queued'].includes(String(status || '').toLowerCase()) ? '停止当前执行' : '暂无执行中的任务'}
            >
              ⏹ 停止
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onClose}>
            ✕ 关闭
          </Button>
        </div>
      </div>
      <div className="flex-1 min-h-0 flex flex-col p-2">
        <div className="flex-1 min-h-0">
          <ExecutionViewer
            runId={runId}
            live={true}
            running={running || verdict?.kind === 'running'}
            title=""
            height={height}
            detailMode="none"
            onNodeClick={(node: any) => setSelectedNode(node)}
            onLiveStatusChange={onLiveStatusChange}
          />
        </div>
        {hasFooter && (
          <div className="flex-shrink-0 border-t border-dark-border bg-dark-card p-3 max-h-[min(55vh,40rem)] overflow-y-auto mt-2 rounded-lg space-y-2">
            {footer}
            {showNodeDetail && selectedNode && (
              <div className="border-t border-dark-border/60 pt-2">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold" style={{ color: selectedNode.color || '#e5e7eb' }}>
                    {selectedNode.icon} {selectedNode.name}
                  </span>
                  <button onClick={() => setSelectedNode(null)} className="text-gray-500 hover:text-gray-300 text-lg">
                    ✕
                  </button>
                </div>
                <div className="flex gap-3 text-[11px] text-gray-400 mb-2">
                  <span>类型: {selectedNode.type}</span>
                  <span>状态: {selectedNode.status}</span>
                  {selectedNode.duration ? (
                    <span>
                      耗时:{' '}
                      {selectedNode.duration >= 1000
                        ? `${(selectedNode.duration / 1000).toFixed(1)}s`
                        : `${Math.round(selectedNode.duration)}ms`}
                    </span>
                  ) : null}
                </div>
                <StructuredDetail node={selectedNode} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ExecuteFlowFullscreen;
