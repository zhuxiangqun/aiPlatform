/**
 * TemplatePanel — 文档模板管理面板 (P0)
 *
 * 挂载 Word/Excel/MD 模板 → AI 按模板格式输出
 */
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, Button, Input, toast } from '../../components/ui';
import { FileText, Upload, Download, Eye, RefreshCw, Plus } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

const TemplatePanel: React.FC = () => {
  const [templates, setTemplates] = useState<any[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [tid, setTid] = useState('');
  const [tpath, setTpath] = useState('');
  const [tdesc, setTdesc] = useState('');
  const [renderData, setRenderData] = useState('{}');
  const [renderResult, setRenderResult] = useState<any>(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const r = await fetch(`${API_BASE}/templates`);
      const d = await r.json();
      setTemplates(d.templates || []);
    } catch {}
  };

  const register = async () => {
    try {
      await fetch(`${API_BASE}/templates/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: tid.trim(), path: tpath.trim(), description: tdesc }),
      });
      setShowAdd(false); setTid(''); setTpath(''); setTdesc('');
      load(); toast?.success?.('模板已注册');
    } catch (e: any) { toast?.error?.(e?.message || '注册失败'); }
  };

  const render = async (templateId: string) => {
    try {
      let data = {};
      try { data = JSON.parse(renderData); } catch {}
      const r = await fetch(`${API_BASE}/templates/render`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: templateId, data }),
      });
      setRenderResult(await r.json());
      toast?.success?.('渲染完成');
    } catch (e: any) { toast?.error?.(e?.message || '渲染失败'); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">文档模板</h2>
          <p className="text-xs text-gray-500">Word/Excel/MD 模板 → AI 按格式输出</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load}><RefreshCw className="w-3 h-3" /></Button>
          <Button variant="default" size="sm" onClick={() => setShowAdd(true)}><Plus className="w-3 h-3 mr-1" />注册模板</Button>
        </div>
      </div>

      {templates.map(t => (
        <Card key={t.template_id} className="border-gray-700/50">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-400" />
                <span className="text-sm text-gray-200 font-medium">{t.template_id}</span>
                <span className="text-[10px] bg-gray-700 text-gray-400 px-1 rounded">{t.format}</span>
                {t.placeholders?.length > 0 && (
                  <span className="text-[10px] text-gray-600">{t.placeholders.length} 占位符</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-1 py-0.5 w-48"
                  value={renderData} onChange={e => setRenderData(e.target.value)}
                  placeholder='{"key":"value"}' />
                <Button variant="ghost" size="sm" className="text-green-400 text-[10px]" onClick={() => render(t.template_id)}>
                  <Eye className="w-3 h-3 mr-1" />渲染
                </Button>
              </div>
            </div>
            {t.placeholders?.length > 0 && (
              <div className="mt-1 flex gap-1 flex-wrap">
                {t.placeholders.map((p: string) => (
                  <span key={p} className="text-[9px] bg-gray-800 text-gray-500 px-1 py-0.5 rounded font-mono">{`{{${p}}}`}</span>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {renderResult && (
        <Card className="border-green-500/20">
          <CardContent className="p-3">
            <div className="text-xs text-green-400">渲染完成: {renderResult.path} ({renderResult.size_bytes} bytes)</div>
          </CardContent>
        </Card>
      )}

      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm mx-4 p-5 space-y-3">
            <h3 className="text-sm font-semibold text-gray-200">注册模板</h3>
            <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
              value={tid} onChange={e => setTid(e.target.value)} placeholder="模板ID" />
            <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
              value={tpath} onChange={e => setTpath(e.target.value)} placeholder="文件路径 (如 ~/templates/report.docx)" />
            <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
              value={tdesc} onChange={e => setTdesc(e.target.value)} placeholder="描述" />
            <div className="flex gap-2">
              <button onClick={() => setShowAdd(false)} className="flex-1 px-3 py-1.5 text-sm rounded border border-gray-700 text-gray-400">取消</button>
              <button onClick={register} disabled={!tid.trim()} className="flex-1 px-3 py-1.5 text-sm rounded bg-blue-600 text-white disabled:opacity-50">注册</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TemplatePanel;
