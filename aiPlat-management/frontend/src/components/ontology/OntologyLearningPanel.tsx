import React, { useEffect, useState } from 'react';
import { Download, Lightbulb, RefreshCw } from 'lucide-react';
import { Button, Modal, toast } from '../../components/ui';

const ONTO_API = '/api/core/ontology';

interface Suggestion {
  id: string;
  type: string;
  status: string;
  description: string;
  confidence?: number;
  subject?: string;
  parent?: string;
}

const TYPE_META: Record<string, { label: string; cls: string }> = {
  new_class: { label: '新类', cls: 'bg-blue-500/20 text-blue-300' },
  new_property: { label: '新属性', cls: 'bg-purple-500/20 text-purple-300' },
  new_subclass: { label: '子类', cls: 'bg-green-500/20 text-green-300' },
  merge_classes: { label: '合并', cls: 'bg-amber-500/20 text-amber-300' },
};

/** 本体学习面板 — 展示 pending 建议 + OWL 导出（P-补全 2026-08-19） */
export default function OntologyLearningPanel({ collection = 'default' }: { collection?: string }) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [ttl, setTtl] = useState('');
  const [ttlOpen, setTtlOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${ONTO_API}/suggestions?collection=${collection}`);
      const d = await r.json();
      setSuggestions(Array.isArray(d.suggestions) ? d.suggestions : []);
    } catch (e: any) {
      toast.error('加载本体建议失败: ' + (e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [collection]);

  const exportOwl = async () => {
    try {
      const r = await fetch(`${ONTO_API}/export/learned?collection=${collection}`);
      const d = await r.json();
      if (d.ttl) { setTtl(d.ttl); setTtlOpen(true); toast.success(`已生成 OWL：${d.classes} 类 / ${d.properties} 属性`); }
      else toast.info('当前无待学习建议，无 OWL 输出');
    } catch (e: any) {
      toast.error('OWL 导出失败: ' + (e?.message || e));
    }
  };

  return (
    <div className="rounded-lg border border-dark-border/30 bg-dark-bg/50 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-yellow-400" />
          <h3 className="text-sm font-medium text-gray-200">本体学习（文档 → OWL/TTL）</h3>
          <span className="text-xs text-gray-500">pending {suggestions.length} 条建议</span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={load} icon={<RefreshCw className="w-3.5 h-3.5" />} disabled={loading}>刷新</Button>
          <Button size="sm" onClick={exportOwl} icon={<Download className="w-3.5 h-3.5" />}>导出 OWL</Button>
        </div>
      </div>
      {suggestions.length === 0 ? (
        <p className="text-xs text-gray-500">暂无待审查建议。运行本体演化或语义建议生成后此处会展示高频概念 / is-a 层次 / 属性建议。</p>
      ) : (
        <ul className="space-y-1.5 max-h-64 overflow-auto">
          {suggestions.map(s => {
            const meta = TYPE_META[s.type] || { label: s.type, cls: 'bg-gray-500/20 text-gray-300' };
            return (
              <li key={s.id} className="flex items-center gap-2 text-xs">
                <span className={`px-1.5 py-0.5 rounded ${meta.cls}`}>{meta.label}</span>
                <span className="text-gray-300 truncate flex-1">{s.description}</span>
                {typeof s.confidence === 'number' && (
                  <span className="text-gray-500">{(s.confidence * 100).toFixed(0)}%</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <Modal open={ttlOpen} onClose={() => setTtlOpen(false)} title="学习本体 (Turtle)">
        <pre className="text-xs text-gray-300 bg-dark-bg border border-dark-border/30 rounded p-3 max-h-96 overflow-auto whitespace-pre-wrap">{ttl}</pre>
      </Modal>
    </div>
  );
}
