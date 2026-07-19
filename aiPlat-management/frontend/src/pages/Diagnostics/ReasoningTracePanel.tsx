import { useState } from 'react';
import { ChevronDown, ChevronRight, Check, X, AlertTriangle, Clock } from 'lucide-react';

interface TraceStep {
  step: number;
  action: string;
  output?: Record<string, any>;
  duration_ms?: number;
  success?: boolean;
  error?: string;
}

const actionLabels: Record<string, string> = {
  task_understanding: '任务理解',
  path_planning: '路径规划',
  graph_query: '图查询',
  scoring: '规则评分',
  nl_output: 'NL 输出',
};

const actionIcons: Record<string, string> = {
  task_understanding: '🔍',
  path_planning: '🗺️',
  graph_query: '🔗',
  scoring: '📊',
  nl_output: '💬',
};

interface Props {
  trace: TraceStep[];
  totalMs?: number;
}

export default function ReasoningTracePanel({ trace, totalMs }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set([1]));
  if (!trace?.length) return null;

  const toggle = (step: number) => {
    const next = new Set(expanded);
    if (next.has(step)) next.delete(step);
    else next.add(step);
    setExpanded(next);
  };

  const percentOf = (ms?: number) => {
    if (!totalMs || !ms) return 0;
    return Math.round((ms / totalMs) * 100);
  };

  return (
    <div style={{ fontFamily: 'monospace', fontSize: 12, marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 600, color: '#aaa' }}>
          🔍 推理过程 {totalMs ? `(耗时 ${totalMs}ms)` : ''}
        </span>
      </div>

      {/* Time bar */}
      {totalMs && (
        <div style={{ display: 'flex', height: 4, borderRadius: 2, overflow: 'hidden', marginBottom: 10, background: '#222' }}>
          {trace.map((s, i) => (
            <div key={i}
              style={{
                width: `${Math.max(percentOf(s.duration_ms), 5)}%`,
                background: s.success === false ? '#a44' : s.success ? '#4a4' : '#888',
                transition: 'width 0.3s',
              }}
            />
          ))}
        </div>
      )}

      {trace.map((step, i) => {
        const isExpanded = expanded.has(step.step);
        const label = actionLabels[step.action] || step.action;
        const icon = actionIcons[step.action] || '📋';
        const succeeded = step.success !== false;

        return (
          <div key={i} style={{ marginBottom: 4 }}>
            <div
              onClick={() => toggle(step.step)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
                borderRadius: 4, cursor: 'pointer',
                background: succeeded ? '#111' : '#311',
                border: `1px solid ${succeeded ? '#333' : '#633'}`,
              }}
            >
              {isExpanded ? <ChevronDown size={12} color="#888" /> : <ChevronRight size={12} color="#888" />}
              <span style={{ color: succeeded ? '#4a4' : '#a44' }}>
                {succeeded ? <Check size={12} style={{ display: 'inline' }} /> : <X size={12} style={{ display: 'inline' }} />}
              </span>
              <span style={{ color: '#ccc' }}>{icon} {step.step}. {label}</span>
              {step.duration_ms && (
                <span style={{ marginLeft: 'auto', color: '#888', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Clock size={10} />{step.duration_ms}ms
                </span>
              )}
            </div>
            {isExpanded && step.output && (
              <div style={{
                marginLeft: 32, padding: '6px 10px', background: '#0a0a0a',
                borderRadius: '0 0 4px 4px', border: '1px solid #222', borderTop: 0,
                fontSize: 11, color: '#aaa',
              }}>
                {renderOutput(step.action, step.output)}
                {step.error && (
                  <div style={{ color: '#f88', marginTop: 4 }}>
                    <AlertTriangle size={10} style={{ display: 'inline' }} /> {step.error}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function renderOutput(action: string, output: Record<string, any>) {
  switch (action) {
    case 'task_understanding':
      return (
        <div>
          <div>域: {output.domain_id || '—'}</div>
          <div>实体: {(output.entities || []).join(', ') || '—'}</div>
          <div>意图: {output.intent || '—'}</div>
          <div>置信度: {output.confidence != null ? `${(output.confidence * 100).toFixed(0)}%` : '—'}</div>
        </div>
      );
    case 'path_planning':
      return (
        <div>
          <div>候选路径: {output.candidate_count || 0} 条</div>
          <div>选择: {output.top_path || '—'}</div>
          <div>匹配方式: {output.match_reason || '—'}</div>
        </div>
      );
    case 'graph_query':
      return (
        <div>
          <div>完成: {output.completed ? '✅' : '❌'}</div>
          <div>终端实体: {output.terminal_count || 0} 个</div>
          <div>跳数: {output.hops || 0}</div>
          <div>尝试路径: {output.tried_paths || 1} 条</div>
        </div>
      );
    case 'scoring':
      return (
        <div>
          <div>评分实体: {output.scored_entities || 0} 个</div>
          <div>评分模型: {output.model || '—'}</div>
        </div>
      );
    default:
      return <div style={{ whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>{JSON.stringify(output, null, 2).slice(0, 500)}</div>;
  }
}
