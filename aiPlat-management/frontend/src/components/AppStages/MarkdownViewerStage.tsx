/**
 * MarkdownViewerStage — 展示 LLM 生成的 markdown/纯文本产物（2026-08-25 新增组件）。
 *
 * 解决"搭积木"缺组件：原 5 种组件无纯展示型，LLM 产物（报告/总结/分析）只能
 * 塞进 result_dashboard 的 text_block。本组件让 agent 模式能直接渲染 markdown。
 *
 * app_page.json 用法：
 *   { "component": "markdown_viewer", "config": { "title": "分析报告", "source": "stage_id 或 inline" } }
 *   - source: 上游 stage id（取其输出的 markdown/文本字段）或省略（展示 execute 返回）
 */
import React, { useState, useEffect } from 'react';
import { Button, Card } from '../ui';
import { FileText, RefreshCw } from 'lucide-react';

interface StageConfig {
  title?: string;
  source?: string;        // 上游 stage id，取其输出展示
  field?: string;         // 从上游输出取哪个字段（默认 raw_output/markdown/content）
  refreshable?: boolean;  // 是否允许手动刷新重新执行
}

interface Props {
  config: StageConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  projectId?: string;
  stageInput?: Record<string, any>;
  onNext?: (result: any) => void;
}

export const MarkdownViewerStage: React.FC<Props> = ({ config, onExecute, skill, stageInput = {}, onNext }) => {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const extractText = (raw: any): string => {
    if (raw == null) return '';
    if (typeof raw === 'string') return raw;
    if (typeof raw === 'object') {
      // 常见字段：raw_output / markdown / content / text / result
      for (const k of ['raw_output', 'markdown', 'content', 'text', 'result', 'output']) {
        const v = raw[k];
        if (typeof v === 'string' && v.trim()) return v;
      }
      try { return JSON.stringify(raw, null, 2); } catch { return ''; }
    }
    return String(raw);
  };

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      // 1) 有 source 配置 → 从上游 stageInput 取
      if (config.source) {
        const src = stageInput[config.source] ?? stageInput;
        setContent(extractText(src));
        setLoading(false);
        return;
      }
      // 2) 否则执行 skill 获取内容
      const resp = await onExecute(skill, stageInput);
      const text = extractText(resp);
      if (!text) setError('未获取到内容');
      else setContent(text);
      onNext?.(resp);
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-primary" />
          {config.title || '内容'}
        </h3>
        {config.refreshable && (
          <Button variant="ghost" size="sm" onClick={load} loading={loading} icon={<RefreshCw className="w-3 h-3" />}>
            刷新
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-xs text-gray-400">加载中...</p>
      ) : error ? (
        <p className="text-xs text-red-400">{error}</p>
      ) : (
        <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed max-h-[50vh] overflow-y-auto markdown-body">
          {content}
        </div>
      )}
    </Card>
  );
};

export default MarkdownViewerStage;
