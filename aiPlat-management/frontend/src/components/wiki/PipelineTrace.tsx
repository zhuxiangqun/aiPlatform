import React, { useState } from 'react';

interface TraceStep {
  phase: string;
  detail: string;
  total_ms: number;
  domain_id?: string;
  quality?: string;
  sources?: number;
  matched_count?: number;
}

interface PipelineTraceProps {
  trace: TraceStep[];
}

const PHASE_COLORS: Record<string, { bg: string; text: string; bar: string }> = {
  '问题理解': { bg: 'bg-blue-900/20', text: 'text-blue-300', bar: 'bg-blue-500' },
  '域路由': { bg: 'bg-green-900/20', text: 'text-green-300', bar: 'bg-green-500' },
  '本体感知': { bg: 'bg-purple-900/20', text: 'text-purple-300', bar: 'bg-purple-500' },
  '多路检索': { bg: 'bg-orange-900/20', text: 'text-orange-300', bar: 'bg-orange-500' },
  '质量评估': { bg: 'bg-yellow-900/20', text: 'text-yellow-300', bar: 'bg-yellow-500' },
  '答案生成': { bg: 'bg-cyan-900/20', text: 'text-cyan-300', bar: 'bg-cyan-500' },
};

const DEFAULT_COLOR = { bg: 'bg-gray-900/20', text: 'text-gray-400', bar: 'bg-gray-500' };

function formatLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

/** Compute bar width as log scale of latency_ms */
function barWidth(ms: number, maxMs: number): number {
  if (maxMs <= 0) return 5;
  const logMax = Math.log2(maxMs + 1);
  const logVal = Math.log2(ms + 1);
  return Math.max(5, (logVal / logMax) * 100);
}

export const PipelineTrace: React.FC<PipelineTraceProps> = ({ trace }) => {
  const [expanded, setExpanded] = useState(false);

  if (!trace || trace.length === 0) return null;

  const maxMs = Math.max(...trace.map(t => t.total_ms || 0), 1);
  const totalMs = trace[trace.length - 1]?.total_ms || 0;

  return (
    <div className="mt-1 text-xs">
      <button
        className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-1"
        onClick={() => setExpanded(!expanded)}
      >
        🧠 思考链 ({trace.length} 步 · {formatLatency(totalMs)})
        <span className="text-gray-500">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-1 pl-1 border-l border-dark-border/50 ml-1">
          {trace.map((step, i) => {
            const colors = PHASE_COLORS[step.phase] || DEFAULT_COLOR;
            const width = barWidth(step.total_ms || 0, maxMs);
            const isLast = i === trace.length - 1;
            const indent = 0;
            return (
              <div key={i} className="flex items-start gap-2" style={{ paddingLeft: indent }}>
                {/* connector dot */}
                <div className="flex flex-col items-center pt-0.5">
                  <div className={`w-2 h-2 rounded-full ${colors.bar}`} />
                  {!isLast && <div className="w-px h-full min-h-[8px] bg-dark-border/50 mt-0.5" />}
                </div>
                {/* content */}
                <div className={`flex-1 min-w-0 ${colors.bg} rounded px-2 py-1 border border-dark-border/30`}>
                  <div className="flex items-center gap-2">
                    <span className={`font-medium ${colors.text}`}>{i + 1}. {step.phase}</span>
                    <div className="flex-1 h-1.5 bg-dark-border/40 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${colors.bar} transition-all`}
                        style={{ width: `${width}%` }} />
                    </div>
                    <span className="text-gray-500 w-14 text-right">{formatLatency(step.total_ms || 0)}</span>
                  </div>
                  <div className="text-gray-500 mt-0.5 leading-relaxed break-words">{step.detail}</div>
                  {/* metadata badges */}
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {step.domain_id && (
                      <span className="text-[9px] px-1 rounded bg-green-900/25 text-green-400">📍 {step.domain_id}</span>
                    )}
                    {step.quality && step.quality !== 'ok' && (
                      <span className={`text-[9px] px-1 rounded ${step.quality === 'low_evidence' ? 'bg-red-900/20 text-red-400' : 'bg-yellow-900/20 text-yellow-400'}`}>
                        ⚠️ {step.quality}
                      </span>
                    )}
                    {step.sources !== undefined && (
                      <span className="text-[9px] px-1 rounded bg-dark-border/30 text-gray-500">📄 {step.sources} 来源</span>
                    )}
                    {step.matched_count !== undefined && (
                      <span className="text-[9px] px-1 rounded bg-dark-border/30 text-gray-500">🔗 {step.matched_count} 匹配类</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
