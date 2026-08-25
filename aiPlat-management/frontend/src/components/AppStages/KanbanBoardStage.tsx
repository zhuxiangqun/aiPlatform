/**
 * KanbanBoardStage — 看板列展示（2026-08-25 新增组件）。
 *
 * 解决"搭积木"缺组件：AGENT.md 声明了 kanban_board 但前端不存在 → 渲染"未知组件"。
 * 用于"按状态/流转/阶段"类应用（如审批流、任务看板）。
 *
 * app_page.json 用法：
 *   { "component": "kanban_board", "config": { "lanes": [{status,label}], "source": "上游stage" } }
 */
import React, { useState, useEffect } from 'react';
import { Card } from '../ui';

interface Lane { status: string; label: string }
interface Item { id: string; title: string; status: string; [k: string]: any }
interface StageConfig { lanes?: Lane[]; source?: string; title?: string }
interface Props {
  config: StageConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  projectId?: string;
  stageInput?: Record<string, any>;
}

export const KanbanBoardStage: React.FC<Props> = ({ config, onExecute, skill, stageInput = {} }) => {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        let raw: any = null;
        if (config.source) raw = stageInput[config.source] ?? stageInput;
        else raw = await onExecute(skill, stageInput);
        const arr = Array.isArray(raw) ? raw : raw?.items || raw?.list || [];
        setItems(arr);
      } catch { /* parent handles */ }
      finally { setLoading(false); }
    })();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const lanes = config.lanes || [];

  return (
    <Card className="p-4">
      {config.title && <h3 className="text-sm font-semibold text-gray-100 mb-3">{config.title}</h3>}
      {loading ? (
        <p className="text-xs text-gray-400">加载中...</p>
      ) : (
        <div className="flex gap-3 overflow-x-auto">
          {lanes.map(lane => {
            const laneItems = items.filter(i => i.status === lane.status || i.lane === lane.status);
            return (
              <div key={lane.status} className="flex-1 min-w-[180px] rounded border border-dark-border bg-dark-hover p-2">
                <div className="text-xs font-semibold text-gray-300 mb-2 px-1">{lane.label} <span className="text-gray-500">({laneItems.length})</span></div>
                <div className="space-y-2">
                  {laneItems.map(item => (
                    <div key={item.id || item.title} className="rounded border border-dark-border bg-dark-surface p-2 text-xs text-gray-300">
                      {item.title || item.name || item.id}
                    </div>
                  ))}
                  {laneItems.length === 0 && <p className="text-[10px] text-gray-600 px-1">空</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};

export default KanbanBoardStage;
