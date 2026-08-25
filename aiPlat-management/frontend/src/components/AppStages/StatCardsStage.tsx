/**
 * StatCardsStage — KPI 指标卡片组（2026-08-25 新增组件）。
 *
 * 解决"搭积木"缺组件：AGENT.md 声明了 stat_cards 但前端不存在 → 渲染"未知组件"。
 * 本组件让 agent 模式能渲染 KPI/统计指标。
 *
 * app_page.json 用法：
 *   { "component": "stat_cards", "config": { "metrics": [{key,label,unit}] } }
 */
import React, { useState, useEffect } from 'react';
import { Card } from '../ui';

interface Metric { key: string; label: string; unit?: string }
interface StageConfig { metrics?: Metric[]; source?: string; title?: string }
interface Props {
  config: StageConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  projectId?: string;
  stageInput?: Record<string, any>;
}

export const StatCardsStage: React.FC<Props> = ({ config, onExecute, skill, stageInput = {} }) => {
  const [values, setValues] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        // 1) source 配置 → 从上游 stageInput 取
        if (config.source) {
          const src = stageInput[config.source] ?? stageInput;
          setValues(typeof src === 'object' ? src : { value: src });
          return;
        }
        // 2) 否则执行 skill 获取指标
        const resp = await onExecute(skill, stageInput);
        setValues(resp && typeof resp === 'object' ? resp : { value: resp });
      } catch { /* parent handles */ }
      finally { setLoading(false); }
    })();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const metrics = config.metrics || Object.entries(values).map(([k]) => ({ key: k, label: k }));

  return (
    <Card className="p-4">
      {config.title && <h3 className="text-sm font-semibold text-gray-100 mb-3">{config.title}</h3>}
      {loading ? (
        <p className="text-xs text-gray-400">加载中...</p>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {metrics.map(m => {
            const v = values[m.key];
            return (
              <div key={m.key} className="rounded border border-dark-border bg-dark-hover p-3 text-center">
                <div className="text-xl font-bold text-primary">{v ?? '—'}{m.unit ? <span className="text-xs text-gray-400 ml-0.5">{m.unit}</span> : null}</div>
                <div className="text-[10px] text-gray-400 mt-1">{m.label}</div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};

export default StatCardsStage;
