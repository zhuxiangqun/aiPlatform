import React, { useState } from 'react';
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
  onLiveStatusChange?: (status: 'disconnected' | 'connecting' | 'streaming' | 'done' | 'error') => void;
  /** Optional bottom summary (result text / error). */
  footer?: React.ReactNode;
};

/**
 * Agent-aligned fullscreen execution flow overlay.
 */
const ExecuteFlowFullscreen: React.FC<Props> = ({
  open,
  runId,
  title,
  verdict,
  status,
  running,
  onClose,
  onLiveStatusChange,
  footer,
}) => {
  const [selectedNode, setSelectedNode] = useState<any>(null);
  if (!open || !runId) return null;

  const hasFooter = !!footer || !!selectedNode;
  const height = Math.max(240, (typeof window !== 'undefined' ? window.innerHeight : 800) - (hasFooter ? 320 : 100));

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
            onNodeClick={(node: any) => setSelectedNode(node)}
            onLiveStatusChange={onLiveStatusChange}
          />
        </div>
        {(footer || selectedNode) && (
          <div className="flex-shrink-0 border-t border-dark-border bg-dark-card p-3 max-h-[42vh] overflow-y-auto mt-2 rounded-lg space-y-2">
            {footer}
            {selectedNode && (
              <div className="border-t border-dark-border/60 pt-2">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold" style={{ color: selectedNode.color || '#e5e7eb' }}>
                    {selectedNode.icon} {selectedNode.name}
                  </span>
                  <button onClick={() => setSelectedNode(null)} className="text-gray-500 hover:text-gray-300 text-lg">
                    ✕
                  </button>
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
