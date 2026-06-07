import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronUp, ChevronDown, X, CheckCircle, ArrowRight, GitFork, Plus } from 'lucide-react';
import type { PipelineStageConfig } from '../../services';
import { Card, CardHeader, CardContent, Button } from '../../components/ui';

interface Props {
  stages: PipelineStageConfig[];
  onUpdate: (stages: PipelineStageConfig[]) => void;
}

export const TeamCanvas: React.FC<Props> = ({ stages, onUpdate }) => {
  const [expandedRouting, setExpandedRouting] = useState<Set<number>>(new Set());

  const toggleRouting = (idx: number) => {
    setExpandedRouting(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const addRoutingRule = (idx: number) => {
    const next = [...stages];
    const rules = next[idx].routing_rules || [];
    next[idx] = { ...next[idx], routing_rules: [...rules, { condition: 'status=="ok"', next: '' }] };
    onUpdate(next);
  };

  const updateRoutingRule = (stageIdx: number, ruleIdx: number, field: 'condition' | 'next', value: string) => {
    const next = [...stages];
    const rules = [...(next[stageIdx].routing_rules || [])];
    rules[ruleIdx] = { ...rules[ruleIdx], [field]: value };
    next[stageIdx] = { ...next[stageIdx], routing_rules: rules };
    onUpdate(next);
  };

  const removeRoutingRule = (stageIdx: number, ruleIdx: number) => {
    const next = [...stages];
    const rules = [...(next[stageIdx].routing_rules || [])];
    rules.splice(ruleIdx, 1);
    next[stageIdx] = { ...next[stageIdx], routing_rules: rules };
    onUpdate(next);
  };

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
              {/* Routing rules */}
              <div style={{ marginTop: 4 }}>
                <button
                  onClick={() => toggleRouting(idx)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 3,
                    background: 'none', border: 'none', color: expandedRouting.has(idx) ? '#8b5cf6' : '#6b7280',
                    cursor: 'pointer', fontSize: 10, padding: 0,
                  }}
                >
                  <GitFork size={10} />
                  条件路由{expandedRouting.has(idx) ? ' ▲' : ' ▼'}
                  {(stage.routing_rules || []).length > 0 && (
                    <span style={{ color: '#8b5cf6', fontWeight: 600 }}>
                      ({(stage.routing_rules || []).length})
                    </span>
                  )}
                </button>
                {expandedRouting.has(idx) && (
                  <div style={{
                    marginTop: 6, marginLeft: 4, padding: '6px 8px',
                    background: '#111827', borderRadius: 6, border: '1px solid #374151',
                  }}>
                    {(stage.routing_rules || []).map((rule, ri) => (
                      <div key={ri} style={{
                        display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4,
                      }}>
                        <span style={{ fontSize: 10, color: '#6b7280', whiteSpace: 'nowrap' }}>当</span>
                        <input
                          value={rule.condition}
                          onChange={e => updateRoutingRule(idx, ri, 'condition', e.target.value)}
                          placeholder='status=="ok"'
                          style={{
                            width: 130, fontSize: 10, background: '#1f2937', border: '1px solid #374151',
                            borderRadius: 3, padding: '2px 6px', color: '#e5e7eb', fontFamily: 'monospace',
                          }}
                        />
                        <span style={{ fontSize: 10, color: '#6b7280' }}>跳转到</span>
                        <select
                          value={rule.next}
                          onChange={e => updateRoutingRule(idx, ri, 'next', e.target.value)}
                          style={{
                            fontSize: 10, background: '#1f2937', border: '1px solid #374151',
                            borderRadius: 3, padding: '2px 4px', color: '#e5e7eb', maxWidth: 120,
                          }}
                        >
                          <option value="">-- 选择阶段 --</option>
                          {stages.filter(s => s.id !== stage.id).map(s => (
                            <option key={s.id} value={s.id}>{s.agent_name}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => removeRoutingRule(idx, ri)}
                          style={{
                            background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer',
                            fontSize: 12, padding: '0 2px',
                          }}
                          title="删除规则"
                        >✕</button>
                      </div>
                    ))}
                    <button
                      onClick={() => addRoutingRule(idx)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 3,
                        background: 'none', border: '1px dashed #374151', borderRadius: 4,
                        color: '#8b5cf6', cursor: 'pointer', fontSize: 10, padding: '2px 8px',
                        width: '100%', justifyContent: 'center',
                      }}
                    >
                      <Plus size={10} /> 添加条件
                    </button>
                    <div style={{ fontSize: 9, color: '#6b7280', marginTop: 4 }}>
                      支持: status=="ok", result.pass_rate &gt; 0.8, error is not None, 多个 and 组合
                    </div>
                  </div>
                )}
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
