import React from 'react';
import { motion } from 'framer-motion';
import { ChevronUp, ChevronDown, X, CheckCircle, ArrowRight } from 'lucide-react';
import type { PipelineStageConfig } from '../../services';
import { Card, CardHeader, CardContent, Button } from '../../components/ui';

interface Props {
  stages: PipelineStageConfig[];
  onUpdate: (stages: PipelineStageConfig[]) => void;
}

export const TeamCanvas: React.FC<Props> = ({ stages, onUpdate }) => {

  const move = (idx: number, dir: -1 | 1) => {
    const next = [...stages];
    const target = idx + dir;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    next[idx].order = idx;
    next[target].order = target;
    onUpdate(next);
  };

  const remove = (idx: number) => {
    onUpdate(stages.filter((_, i) => i !== idx));
  };

  const toggleHitl = (idx: number) => {
    const next = [...stages];
    next[idx] = { ...next[idx], hitl: !next[idx].hitl };
    onUpdate(next);
  };

  const setRetryTarget = (idx: number, targetId: string) => {
    const next = [...stages];
    next[idx] = { ...next[idx], retry_target_id: targetId };
    onUpdate(next);
  };

  if (stages.length === 0) {
    return (
      <Card>
        <CardHeader title="团队画布" />
        <CardContent>
          <div className="text-sm text-gray-500 text-center py-8">
            从左侧角色池点击 <span className="text-primary">＋</span> 添加角色到团队
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="团队画布" extra={
        <span className="text-xs text-gray-500">{stages.length} 个角色</span>
      } />
      <CardContent className="space-y-1.5">
        {stages.map((stage, idx) => (
          <motion.div
            key={stage.id}
            layout
            className="flex items-center gap-2 p-2 rounded-lg border border-dark-border bg-dark-card group"
          >
            {/* Order number + arrow */}
            <div className="flex flex-col items-center gap-0.5">
              <Button size="sm" variant="ghost" disabled={idx === 0} onClick={() => move(idx, -1)}>
                <ChevronUp className="w-3 h-3" />
              </Button>
              <span className="text-[10px] font-mono text-gray-500 w-4 text-center">{idx + 1}</span>
              <Button size="sm" variant="ghost" disabled={idx === stages.length - 1} onClick={() => move(idx, 1)}>
                <ChevronDown className="w-3 h-3" />
              </Button>
            </div>

            {/* Arrow between stages */}
            {idx > 0 && <ArrowRight className="w-4 h-4 text-gray-600 -ml-1" />}

            {/* Agent info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-sm font-semibold text-gray-100">{stage.agent_name}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">{stage.category}</span>
              </div>
              <div className="text-xs text-gray-400 line-clamp-2">
                {stage.description || '暂无描述'}
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <Button
                size="sm"
                variant={stage.hitl ? 'primary' : 'ghost'}
                onClick={() => toggleHitl(idx)}
                title="需要用户确认"
              >
                <CheckCircle className={`w-3 h-3 ${stage.hitl ? 'text-green-400' : 'text-gray-500'}`} />
              </Button>
              <select
                className="text-[10px] bg-dark-hover border border-dark-border rounded px-1 py-0.5 text-gray-400"
                value={stage.retry_target_id}
                onChange={(e) => setRetryTarget(idx, e.target.value)}
                title="默认回退目标（AI 判定优先。未命中时退回此处）"
              >
                <option value="">AI 自动判定</option>
                {stages.filter((s) => s.id !== stage.id).map((s) => (
                  <option key={s.id} value={s.id}>{s.agent_name}</option>
                ))}
              </select>
              <Button size="sm" variant="ghost" onClick={() => remove(idx)}>
                <X className="w-3 h-3 text-red-400" />
              </Button>
            </div>
          </motion.div>
        ))}
      </CardContent>
    </Card>
  );
};
