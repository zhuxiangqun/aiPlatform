import React, { useState, useEffect, useCallback } from 'react';
import { PenTool, Plus, Trash2, RefreshCw, ExternalLink } from 'lucide-react';
import { Button, Input, toast } from '../../components/ui';

interface Diagram {
  id: string;
  name: string;
  size: number;
  modified: string;
}

const API_BASE = '/api/core';

const DiagramStudio: React.FC = () => {
  const [diagrams, setDiagrams] = useState<Diagram[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [modifyDesc, setModifyDesc] = useState('');
  const [loading, setLoading] = useState(false);
  const [viewerKey, setViewerKey] = useState(0);

  const fetchDiagrams = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/diagrams`);
      const data = await res.json();
      setDiagrams(data.diagrams || []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => { fetchDiagrams(); }, [fetchDiagrams]);

  const generate = async () => {
    if (!description.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/diagrams/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
      const data = await res.json();
      if (data.diagram_id) {
        setSelectedId(data.diagram_id);
        setViewerKey(k => k + 1);
        setDescription('');
        fetchDiagrams();
        toast.success('图表生成成功');
      } else {
        toast.error('生成失败');
      }
    } catch {
      toast.error('生成失败');
    } finally {
      setLoading(false);
    }
  };

  const modify = async () => {
    if (!modifyDesc.trim() || !selectedId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/diagrams/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: modifyDesc, modify_id: selectedId }),
      });
      const data = await res.json();
      if (data.diagram_id) {
        setSelectedId(data.diagram_id);
        setViewerKey(k => k + 1);
        setModifyDesc('');
        fetchDiagrams();
        toast.success('图表已更新');
      } else {
        toast.error('修改失败');
      }
    } catch {
      toast.error('修改失败');
    } finally {
      setLoading(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await fetch(`${API_BASE}/diagrams/${id}`, { method: 'DELETE' });
      if (selectedId === id) setSelectedId(null);
      fetchDiagrams();
      toast.success('已删除');
    } catch {
      toast.error('删除失败');
    }
  };

  return (
    <div className="h-full flex flex-col p-4">
      <h1 className="text-xl font-bold mb-4 flex items-center gap-2">
        <PenTool size={20} /> 图表工作室
        <span className="text-xs text-gray-500 font-normal">
          AI 生成 draw.io 图表 · 零外部依赖
        </span>
      </h1>

      {/* Generate Bar */}
      <div className="mb-4 p-3 rounded-lg border border-primary/20 bg-dark-card">
        <div className="flex gap-2">
          <Input
            placeholder="描述你想要的图表，如：用户登录 + MFA + 会话管理流程图"
            value={description}
            onChange={(e: any) => setDescription(e.target.value)}
            onKeyDown={(e: any) => e.key === 'Enter' && generate()}
            className="flex-1"
            disabled={loading}
          />
          <Button variant="primary" onClick={generate} loading={loading} disabled={!description.trim()}>
            <Plus size={14} className="mr-1" /> 生成
          </Button>
        </div>
      </div>

      {/* Modify Bar (shown when a diagram is selected) */}
      {selectedId && (
        <div className="mb-4 p-2 rounded-lg border border-dark-border bg-dark-bg">
          <div className="flex gap-2">
            <Input
              placeholder="修改需求，如：把数据库拆成独立模块"
              value={modifyDesc}
              onChange={(e: any) => setModifyDesc(e.target.value)}
              onKeyDown={(e: any) => e.key === 'Enter' && modify()}
              className="flex-1"
              disabled={loading}
            />
            <Button variant="secondary" onClick={modify} loading={loading} disabled={!modifyDesc.trim()}>
              <RefreshCw size={14} className="mr-1" /> 修改
            </Button>
          </div>
        </div>
      )}

      {/* Main: sidebar + viewer */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Sidebar */}
        <div className="w-56 flex-shrink-0 overflow-y-auto rounded-lg border border-dark-border bg-dark-card p-2">
          <div className="text-xs font-medium text-gray-400 mb-2">我的图表 ({diagrams.length})</div>
          {diagrams.map(d => (
            <div
              key={d.id}
              onClick={() => { setSelectedId(d.id); setViewerKey(k => k + 1); }}
              className={`group p-2 rounded cursor-pointer mb-1 flex items-center justify-between ${
                selectedId === d.id
                  ? 'bg-primary/20 border-l-2 border-primary'
                  : 'hover:bg-dark-bg'
              }`}
            >
              <div className="truncate text-sm flex-1">{d.name}</div>
              <button
                onClick={(e) => { e.stopPropagation(); remove(d.id); }}
                className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400"
                style={{ background: 'none', border: 'none', cursor: 'pointer' }}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          {diagrams.length === 0 && (
            <div className="text-xs text-gray-600 p-2">暂无图表。输入描述生成第一个。</div>
          )}
        </div>

        {/* Viewer */}
        <div className="flex-1 rounded-lg border border-dark-border bg-white overflow-hidden">
          {selectedId ? (
            <iframe
              key={viewerKey}
              src={`/api/core/diagrams/viewer/${selectedId}`}
              className="w-full h-full border-none"
              title="diagram"
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              <div className="text-center">
                <PenTool size={40} className="mx-auto mb-2 opacity-30" />
                <p>选择一个图表或输入描述生成新图表</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DiagramStudio;
