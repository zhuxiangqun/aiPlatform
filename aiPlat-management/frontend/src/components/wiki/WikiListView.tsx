import React, { useState } from 'react';
import { BookOpen, Trash2 } from 'lucide-react';

interface WikiPage {
  title: string;
  category: string;
  tags: string[];
  related: string[];
  contradictions: string[];
  summary: string;
  source_articles: string[];
}

interface WikiListViewProps {
  pages: WikiPage[];
  onSelect: (title: string) => void;
  onDelete: (title: string) => void;
  sourceBadge: (cat: string) => string;
}

const WikiListView: React.FC<WikiListViewProps> = ({ pages, onSelect, onDelete, sourceBadge }) => {
  const [mode, setMode] = useState<'flat' | 'group'>('group');

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="text-xs text-gray-500">{pages.length} 个页面</div>
        <div className="flex-1" />
        <button onClick={() => setMode('flat')}
          className={`text-[10px] px-1.5 py-0.5 rounded ${mode === 'flat' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>平铺</button>
        <button onClick={() => setMode('group')}
          className={`text-[10px] px-1.5 py-0.5 rounded ${mode === 'group' ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>分类</button>
      </div>

      {mode === 'group' ? (
        <GroupedView pages={pages} onSelect={onSelect} />
      ) : (
        pages.map((p) => (
          <div key={p.title} onClick={() => onSelect(p.title)}
            className="p-3 rounded-lg border border-dark-border bg-dark-card cursor-pointer hover:border-gray-600">
            <div className="flex items-center gap-2 mb-1">
              <BookOpen className="w-3 h-3 text-gray-400" />
              <span className="text-sm font-medium text-gray-200">{p.title.length > 45 ? p.title.slice(0, 42) + '...' : p.title}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${sourceBadge(p.category)}`}>{p.category}</span>
              {p.related?.length > 0 && <span className="text-[10px] text-blue-500">↗ {p.related.length} 关联</span>}
              <div className="flex-1" />
              <button onClick={(e) => { e.stopPropagation(); onDelete(p.title); }}
                className="text-gray-600 hover:text-red-400 transition-colors" title="删除">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
            {p.summary && <div className="text-xs text-gray-500 line-clamp-1">{p.summary}</div>}
            <div className="flex gap-2 mt-1">
              {(p.tags || []).slice(0, 3).map((t: string) => (
                <span key={t} className="text-[10px] text-gray-600 bg-dark-bg px-1 rounded">{t}</span>
              ))}
              {p.contradictions?.length > 0 && (
                <span className="text-[10px] text-red-400">⚠{p.contradictions.length}</span>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
};

const GroupedView: React.FC<{ pages: WikiPage[]; onSelect: (t: string) => void }> = ({ pages, onSelect }) => {
  const groups: Record<string, WikiPage[]> = {};
  pages.forEach((p) => {
    const src = (p.source_articles || []).find((s: string) => s.startsWith('kb:')) || 'manual';
    const key = p.category + '||' + src;
    (groups[key] = groups[key] || []).push(p);
  });

  return (
    <>
      {Object.entries(groups).map(([key, gp]) => {
        const [cat, src] = key.split('||');
        const docLabel = src.replace('kb:', '').slice(0, 25);
        return (
          <details key={key} open className="rounded-lg border border-dark-border bg-dark-card">
            <summary className="px-3 py-2 text-xs cursor-pointer hover:text-gray-200 flex items-center gap-2 text-gray-300">
              <span className={`w-2 h-2 rounded-full ${cat === 'topics' ? 'bg-purple-500' : 'bg-blue-500'}`} />
              <span className={cat === 'topics' ? 'text-purple-400' : 'text-blue-400'}>{cat}</span>
              <span className="text-gray-600">· 📎 {docLabel}</span>
              <span className="text-gray-600 ml-auto">{gp.length} 页</span>
            </summary>
            <div className="px-3 pb-2 space-y-1">
              {gp.map((p) => (
                <div key={p.title} onClick={() => onSelect(p.title)}
                  className="ml-4 pl-2 py-1 border-l border-dark-border cursor-pointer hover:text-gray-200 text-xs text-gray-400">
                  {p.title.length > 45 ? p.title.slice(0, 42) + '...' : p.title}
                  {p.related?.length > 0 && <span className="ml-2 text-blue-500/70">↗{p.related.length}</span>}
                </div>
              ))}
            </div>
          </details>
        );
      })}
    </>
  );
};

export default WikiListView;
