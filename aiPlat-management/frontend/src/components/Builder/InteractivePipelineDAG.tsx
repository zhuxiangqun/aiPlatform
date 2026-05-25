import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle, XCircle, Loader2, Clock, ChevronDown } from 'lucide-react';
import type { BuilderSession, PipelineStageConfig } from '../../services';

interface Props {
  session: BuilderSession;
  teamStages?: PipelineStageConfig[];
  onStageClick?: (stageKey: string) => void;
}

interface DagNode {
  key: string;
  label: string;
  phase: string;
  skills: string[];
  status: 'passed' | 'running' | 'failed' | 'awaiting' | 'waiting';
  isCurrent: boolean;
}

function buildDagNodes(teamStages?: PipelineStageConfig[], session?: BuilderSession): DagNode[] {
  const raw = session as Record<string, unknown> | undefined;
  const stages = (teamStages || []).map((s, idx) => {
    const key = s.output_artifact || `stage_${idx}`;
    const val = raw?.[key];
    const isCurrent = raw?.['_current_stage_idx'] === idx;

    let status: DagNode['status'] = 'waiting';
    if (session?.phase === 'failed') {
      status = 'failed';
    } else if (isCurrent && (session?.phase?.includes('approval') || session?.phase === 'paused')) {
      status = 'awaiting';
    } else if (isCurrent && session?.phase === 'executing') {
      status = 'running';
    } else if (val != null) {
      if (typeof val === 'object' && 'recommendation' in (val as any)) {
        status = (val as any).recommendation === 'APPROVED' ? 'passed' : 'failed';
      } else if (typeof val === 'object' && Object.keys(val as object).length > 0) {
        status = 'passed';
      } else if (typeof val === 'string' && val.length > 0) {
        status = 'passed';
      }
    }

    return {
      key,
      label: (s as any).agent_name || s.agent_id || `Stage ${idx + 1}`,
      phase: (s as any).phase || '',
      skills: (s as any).required_skills || [],
      status,
      isCurrent,
    };
  });
  return stages;
}

const statusColors: Record<string, { bg: string; border: string; icon: string; text: string; label: string }> = {
  passed: { bg: 'bg-green-500/10', border: 'border-green-500/40', icon: 'text-green-400', text: 'text-green-300', label: '已完成' },
  running: { bg: 'bg-blue-500/10', border: 'border-blue-500/40', icon: 'text-blue-400', text: 'text-blue-300', label: '执行中' },
  failed: { bg: 'bg-red-500/10', border: 'border-red-500/40', icon: 'text-red-400', text: 'text-red-300', label: '失败' },
  awaiting: { bg: 'bg-amber-500/10', border: 'border-amber-500/40', icon: 'text-amber-400', text: 'text-amber-300', label: '待审批' },
  waiting: { bg: 'bg-gray-500/5', border: 'border-gray-500/20', icon: 'text-gray-600', text: 'text-gray-500', label: '等待中' },
};

const PhaseBadge: React.FC<{ phase: string }> = ({ phase }) => {
  if (!phase) return null;
  const phaseColors: Record<string, string> = {
    planning: 'bg-blue-500/15 text-blue-300 border-blue-500/25',
    design: 'bg-purple-500/15 text-purple-300 border-purple-500/25',
    development: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
    testing: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
    review: 'bg-pink-500/15 text-pink-300 border-pink-500/25',
    deployment: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/25',
    scaffold: 'bg-teal-500/15 text-teal-300 border-teal-500/25',
    management: 'bg-gray-500/15 text-gray-300 border-gray-500/25',
    operations: 'bg-orange-500/15 text-orange-300 border-orange-500/25',
    support: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/25',
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${phaseColors[phase] || 'bg-gray-500/10 text-gray-400 border-gray-500/20'}`}>
      {phase}
    </span>
  );
};

const InteractivePipelineDAG: React.FC<Props> = ({ session, teamStages, onStageClick }) => {
  const nodes = useMemo(() => buildDagNodes(teamStages, session), [teamStages, session]);

  if (nodes.length === 0) return null;

  // Legend
  const usedStatuses = [...new Set(nodes.map(n => n.status))];

  return (
    <div className="rounded-xl border border-dark-border bg-dark-card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Pipeline 拓扑图</span>
        <div className="flex items-center gap-2">
          {usedStatuses.map(s => {
            const c = statusColors[s];
            return (
              <span key={s} className="flex items-center gap-1 text-[10px] text-gray-500">
                <span className={`w-2 h-2 rounded-full ${c.bg} border ${c.border}`} />
                {c.label}
              </span>
            );
          })}
        </div>
      </div>

      <div className="flex items-start gap-2 overflow-x-auto pb-2">
        {nodes.map((node, idx) => {
          const c = statusColors[node.status];
          const isLast = idx === nodes.length - 1;

          return (
            <React.Fragment key={node.key}>
              {/* Stage Node */}
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: idx * 0.08 }}
                onClick={() => onStageClick?.(node.key)}
                className={`flex-shrink-0 w-36 rounded-lg border p-3 cursor-pointer transition-all hover:scale-105 ${c.bg} ${c.border} ${node.isCurrent ? 'ring-2 ring-blue-400/50' : ''}`}
              >
                {/* Status icon + Number */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-bold text-gray-500">{(idx + 1).toString().padStart(2, '0')}</span>
                  {node.status === 'passed' && <CheckCircle className={`w-3.5 h-3.5 ${c.icon}`} />}
                  {node.status === 'running' && <Loader2 className={`w-3.5 h-3.5 ${c.icon} animate-spin`} />}
                  {node.status === 'failed' && <XCircle className={`w-3.5 h-3.5 ${c.icon}`} />}
                  {node.status === 'awaiting' && <Clock className={`w-3.5 h-3.5 ${c.icon}`} />}
                  {node.status === 'waiting' && <span className={`w-3.5 h-3.5 rounded-full border ${c.border}`} />}
                </div>

                {/* Agent Name */}
                <div className="text-xs font-medium text-gray-100 truncate mb-1" title={node.label}>
                  {node.label}
                </div>

                {/* Phase Badge */}
                {node.phase && (
                  <div className="mb-1">
                    <PhaseBadge phase={node.phase} />
                  </div>
                )}

                {/* Skills Count */}
                {node.skills.length > 0 && (
                  <div className="text-[10px] text-gray-500">
                    {node.skills.length} skill{node.skills.length > 1 ? 's' : ''}
                  </div>
                )}
              </motion.div>

              {/* Arrow between nodes */}
              {!isLast && (
                <div className="flex-shrink-0 flex flex-col items-center justify-center pt-8">
                  <motion.div
                    animate={node.status === 'running' ? { y: [0, 4, 0] } : {}}
                    transition={{ repeat: Infinity, duration: 1 }}
                  >
                    <ChevronDown className={`w-4 h-4 ${
                      node.status === 'passed' ? 'text-green-400' :
                      node.status === 'running' ? 'text-blue-400' :
                      'text-gray-600'
                    }`} />
                  </motion.div>
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

export default InteractivePipelineDAG;
