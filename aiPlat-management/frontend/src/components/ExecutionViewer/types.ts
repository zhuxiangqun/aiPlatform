export interface ExecutionNode {
  id: string;
  type: string;
  name: string;
  group?: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'warning';
  parentId?: string;
  parentSpanId?: string;
  startTime?: number;
  duration?: number;
  details?: Record<string, any>;
  color?: string;
  icon?: string;
  children?: ExecutionNode[];
  isSubFlow?: boolean;
}

export interface ExecutionSummary {
  pass: number;
  warn: number;
  fail: number;
  total: number;
}

export interface ExecutionViewerProps {
  nodes?: ExecutionNode[];
  title?: string;
  running?: boolean;
  elapsed?: number;
  summary?: ExecutionSummary;
  height?: number;
  onNodeClick?: (node: ExecutionNode) => void;
  live?: boolean;
  runId?: string;
  replayRunId?: string;
  /** Fired when live SSE/poll status changes (connecting/streaming/done/error) */
  onLiveStatusChange?: (status: 'disconnected' | 'connecting' | 'streaming' | 'done' | 'error') => void;
  /**
   * Where to render the node detail panel.
   * - inline (default): under the canvas inside the viewer
   * - none: parent owns detail (e.g. ExecuteFlowFullscreen footer) — avoid double panels
   */
  detailMode?: 'inline' | 'none';
}
