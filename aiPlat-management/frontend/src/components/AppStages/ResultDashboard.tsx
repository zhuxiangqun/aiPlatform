import React, { useState, useEffect } from 'react';
import { Card, Badge } from '../ui';
import { Copy, Download, ExternalLink } from 'lucide-react';

interface SectionConfig {
  key: string;
  label: string;
  type: 'tag_cloud' | 'text_block' | 'markdown' | 'timeline' | 'table';
}

interface ResultConfig {
  sections?: SectionConfig[];
  input?: Record<string, string>;
}

interface Props {
  config: ResultConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  stageInput?: Record<string, any>;
}

export const ResultDashboard: React.FC<Props> = ({ config, onExecute, skill, stageInput }) => {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const params = { ...(config.input || {}), ...(stageInput || {}) };
        const res = await onExecute(skill, params);
        const parsed = typeof res === 'string' ? (() => { try { return JSON.parse(res); } catch { return { reply: res }; } })() : res;
        setData(parsed);
      } catch (e: any) {
        setError(e?.message || '加载失败');
      } finally {
        setLoading(false);
      }
    })();
  }, [skill, config, stageInput, onExecute]);

  if (loading) return <Card className="p-6"><div className="text-sm text-gray-400">加载结果中...</div></Card>;
  if (error) return <Card className="p-6"><div className="text-sm text-red-400">{error}</div></Card>;
  if (!data) return null;

  const sections = config.sections || Object.keys(data).map(k => ({ key: k, label: k, type: 'text_block' as const }));

  const renderSection = (s: SectionConfig, val: any) => {
    switch (s.type) {
      case 'tag_cloud':
        const tags = Array.isArray(val) ? val : typeof val === 'string' ? val.split(',').map(t => t.trim()) : [];
        return <div className="flex flex-wrap gap-2">{tags.map((t: string, i: number) => <Badge key={i} variant="default" className="text-xs">{t}</Badge>)}</div>;
      case 'text_block':
        return <p className="text-sm text-gray-300 whitespace-pre-wrap">{typeof val === 'string' ? val : JSON.stringify(val, null, 2)}</p>;
      case 'markdown':
        return <div className="text-sm text-gray-300 prose prose-invert max-w-none" dangerouslySetInnerHTML={{ __html: String(val).replace(/\n/g, '<br/>') }} />;
      case 'table':
        const rows = Array.isArray(val) ? val : [];
        const cols = rows.length > 0 ? Object.keys(rows[0]) : [];
        return (
          <table className="w-full text-sm">
            <thead><tr>{cols.map(c => <th key={c} className="text-left text-gray-400 py-1">{c}</th>)}</tr></thead>
            <tbody>{rows.map((r: any, i: number) => <tr key={i}>{cols.map(c => <td key={c} className="py-1 text-gray-300">{String(r[c] || '')}</td>)}</tr>)}</tbody>
          </table>
        );
      default:
        return <p className="text-sm text-gray-400">{JSON.stringify(val).slice(0, 200)}</p>;
    }
  };

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold mb-4 text-gray-100">分析结果</h2>
      <div className="space-y-4">
        {sections.map(s => {
          const val = data[s.key] ?? data;
          return (
            <div key={s.key} className="border-t border-dark-border pt-3 first:border-0 first:pt-0">
              <h3 className="text-xs font-semibold text-gray-500 mb-2">{s.label}</h3>
              {renderSection(s, val)}
            </div>
          );
        })}
      </div>
      <div className="flex gap-2 mt-4 pt-3 border-t border-dark-border">
        <button onClick={() => navigator.clipboard.writeText(JSON.stringify(data, null, 2))} className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1">
          <Copy className="w-3 h-3" />复制
        </button>
      </div>
    </Card>
  );
};
