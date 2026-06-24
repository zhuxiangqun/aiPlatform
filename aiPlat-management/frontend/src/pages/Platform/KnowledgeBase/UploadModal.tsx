import React, { useRef, useState } from 'react';
import { Button, Input, Modal, toast } from '../../../components/ui';
import { kbApi } from '../../../services';
import { useKBStore } from '../../../stores';

interface Props {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

const ACCEPTED_TYPES: Record<string, { label: string; extensions: string[]; kind: string }> = {
  pdf: { label: 'PDF 文档', extensions: ['.pdf'], kind: 'pdf' },
  word: { label: 'Word 文档', extensions: ['.docx', '.doc'], kind: 'word' },
  ppt: { label: 'PPT 演示', extensions: ['.pptx', '.ppt'], kind: 'ppt' },
  markdown: { label: 'Markdown', extensions: ['.md', '.markdown'], kind: 'markdown' },
  xlsx: { label: 'Excel 表格', extensions: ['.xlsx', '.xls'], kind: 'xlsx' },
  csv: { label: 'CSV 数据表', extensions: ['.csv'], kind: 'csv' },
  html: { label: 'HTML 网页', extensions: ['.html', '.htm'], kind: 'html' },
  audio: { label: '音频', extensions: ['.mp3', '.wav', '.m4a', '.ogg', '.flac'], kind: 'audio' },
  image: { label: '图片', extensions: ['.png', '.jpg', '.jpeg', '.bmp', '.webp'], kind: 'image' },
  json: { label: 'JSON 数据', extensions: ['.json'], kind: 'json' },
  video: { label: '视频', extensions: ['.mp4', '.mov', '.mkv', '.avi'], kind: 'video' },
};

type UploadMode = 'file' | 'url' | 'directory';
type Step = 'input' | 'preview' | 'saving';

export const UploadModal: React.FC<Props> = ({ open, onClose, onComplete }) => {
  const { uploadDocument, uploadProgress } = useKBStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>('input');
  const [mode, setMode] = useState<UploadMode>('file');
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<'pdf' | 'video' | 'word' | 'ppt' | 'markdown'>('pdf');
  const [collectionId, setCollectionId] = useState('default');
  const [url, setUrl] = useState('');
  const [dirPath, setDirPath] = useState('');
  const [dirRecursive, setDirRecursive] = useState(true);
  const [dirPattern, setDirPattern] = useState('*.md');
  const [dirAutoSync, setDirAutoSync] = useState(false);
  const [showSegments, setShowSegments] = useState(false);
  const [loading, setLoading] = useState(false);

  // Sync result display
  const [syncResult, setSyncResult] = useState<{ total: number; cleaned: number; skipped: number } | null>(null);

  const [preview, setPreview] = useState<any>(null);
  const [tempFilePath, setTempFilePath] = useState('');
  const [editedContent, setEditedContent] = useState('');

  const reset = () => {
    setStep('input');
    setFile(null);
    setUrl('');
    setPreview(null);
    setTempFilePath('');
    setEditedContent('');
    setLoading(false);
    setShowSegments(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
    for (const [k] of Object.entries(ACCEPTED_TYPES)) {
      if (ACCEPTED_TYPES[k as keyof typeof ACCEPTED_TYPES].extensions.includes(ext)) {
        setKind(k as typeof kind);
        break;
      }
    }
    e.target.value = '';
  };

  const handlePreview = async () => {
    setLoading(true);
    setPreview(null);
    try {
      let result: any;
      if (mode === 'file' && file) {
        result = await kbApi.previewDocument(file, kind, collectionId);
      } else if (mode === 'url' && url.trim()) {
        result = await kbApi.previewDocumentByUrl(url.trim(), collectionId);
      } else {
        toast.error('请选择文件或输入链接');
        return;
      }
      setPreview(result);
      setTempFilePath(result.temp_file_path || '');
      const para = result?.elements?.find((e: any) => e.type === 'paragraph');
      setEditedContent(para?.text || result?.elements?.[0]?.text || '');
      setStep('preview');
    } catch (e: any) {
      toast.error(`预览失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDirectoryIngest = async () => {
    if (!dirPath.trim()) { toast.error('请输入目录路径'); return; }
    setLoading(true);
    try {
      const res = await fetch('/api/platform/documents/ingest-directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          directory: dirPath.trim(),
          collection_id: collectionId,
          recursive: dirRecursive,
          pattern: dirPattern,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error((data as any).detail || '导入失败');

      setSyncResult({ total: data.total || 0, cleaned: data.cleaned || 0, skipped: data.skipped || 0 });

      if (dirAutoSync) {
        await fetch('/api/platform/kb/watch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            directory: dirPath.trim(),
            collection_id: collectionId,
            recursive: dirRecursive,
            pattern: dirPattern,
          }),
        }).catch(() => {});
        toast.success(`已导入并开启同步：${data.total} 新/更新，${data.cleaned} 清理，${data.skipped || 0} 跳过`);
      } else {
        toast.success(`导入完成：${data.total} 新/更新，${data.cleaned} 清理，${data.skipped || 0} 跳过`);
      }
    } catch (e: any) {
      toast.error(`导入失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setStep('saving');
    try {
      const paraEl = preview?.elements?.find((e: any) => e.type === 'paragraph');
      const originalText = paraEl?.text || preview?.elements?.[0]?.text || '';
      const wasEdited = editedContent !== originalText;

      if (wasEdited && editedContent.trim()) {
        const baseUrl = (import.meta as any).env?.VITE_API_URL || '/api';
        const form = new FormData();
        const blob = new Blob([editedContent], { type: 'text/plain;charset=utf-8' });
        form.append('file', blob, (file?.name || 'document') + '.edited.txt');
        form.append('collection_id', collectionId);
        const headers: Record<string, string> = {};
        try {
          const t = localStorage.getItem('active_tenant_id') || '';
          if (t) headers['X-AIPLAT-TENANT-ID'] = t;
          headers['X-AIPLAT-ACTOR-ID'] = localStorage.getItem('active_actor_id') || 'admin';
          headers['X-AIPLAT-SCOPES'] = localStorage.getItem('active_scopes') || 'kb:read,kb:write';
          const k = localStorage.getItem('active_api_key') || '';
          if (k) headers['X-AIPLAT-API-KEY'] = k;
        } catch {}
        await fetch(`${baseUrl}/platform/documents/ingest`, { method: 'POST', body: form, headers });
      } else if (tempFilePath) {
        // Use cached preview results to avoid re-parsing (ffmpeg + whisper already done)
        await kbApi.ingestDocumentByFilePath(tempFilePath, collectionId, kind);
      } else if (mode === 'file' && file) {
        await uploadDocument(file, kind, collectionId);
      }
      reset();
      onComplete();
    } catch (e: any) {
      toast.error(`保存失败：${e?.message || e}`);
      setStep('preview');
    } finally {
      setLoading(false);
    }
  };

  const allAccept = Object.values(ACCEPTED_TYPES).flatMap((t) => t.extensions).join(',');

  // ── Preview step ──
  if (step === 'preview' || step === 'saving') {
    const els = preview?.elements || [];
    const cls = preview?.classification || {};
    const catLabel: Record<string, string> = {
      budget_investment: '预算投资', technical_doc: '技术文档',
      meeting_notes: '会议纪要', general: '通用',
    };

    return (
      <Modal
        open={open}
        onClose={handleClose}
        title="资料预览"
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setStep('input')} disabled={loading}>
              返回修改
            </Button>
            <Button variant="primary" onClick={handleSave} loading={loading}>
              保存到知识库
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap gap-2">
            <span className="px-2 py-1 rounded bg-dark-hover text-xs text-gray-300">
              {preview?.kind?.toUpperCase()} · {preview?.parser}
            </span>
            <span className="px-2 py-1 rounded bg-dark-hover text-xs text-gray-300">
              {preview?.element_count || 0} 个文本元素
            </span>
            {cls.content_category && (
              <span className="px-2 py-1 rounded bg-primary/20 text-xs text-primary">
                {catLabel[cls.content_category] || cls.content_category}
              </span>
            )}
            {cls.tags?.length > 0 && cls.tags.slice(0, 5).map((t: string) => (
              <span key={t} className="px-2 py-1 rounded bg-dark-hover text-xs text-gray-400">{t}</span>
            ))}
          </div>

          {preview?.diagnostics && (
            <div className="flex flex-wrap gap-2 text-xs">
              {preview.diagnostics.coverage_ratio != null && (
                <span className={`px-2 py-0.5 rounded ${
                  preview.diagnostics.coverage_ratio >= 0.85 ? 'bg-green-900/30 text-green-400' :
                  preview.diagnostics.coverage_ratio >= 0.5 ? 'bg-yellow-900/30 text-yellow-400' :
                  'bg-red-900/30 text-red-400'
                }`}>
                  覆盖率 {(preview.diagnostics.coverage_ratio * 100).toFixed(0)}%
                </span>
              )}
              <span className="px-2 py-0.5 rounded bg-dark-hover text-gray-400">
                模型 {preview.diagnostics.model_name || '?'}
              </span>
              {preview.diagnostics.fallback_used === 'chunked' && (
                <span className="px-2 py-0.5 rounded bg-blue-900/30 text-blue-400">
                  已触发分块回退
                </span>
              )}
              {preview.diagnostics.fallback_error && (
                <span className="px-2 py-0.5 rounded bg-red-900/30 text-red-400">
                  回退失败
                </span>
              )}
              {preview.diagnostics.coverage_ratio != null && preview.diagnostics.coverage_ratio < 0.85 && !preview.diagnostics.fallback_used && (
                <span className="px-2 py-0.5 rounded bg-yellow-900/20 text-yellow-500">
                  建议升级模型: export AIPLAT_VIDEO_WHISPER_MODEL=medium
                </span>
              )}
            </div>
          )}

          <div className="text-xs text-gray-500">
            {step === 'saving' ? '正在保存到知识库...' : '以下是解析出的核心内容，确认后点击"保存到知识库"'}
          </div>

          {(() => {
            const para = els.find((e: any) => e.type === 'paragraph');
            const segs = els.filter((e: any) => e.type === 'text');
            return (
              <div className="space-y-3">
                {/* Editable transcript/content */}
                {para && (
                  <div className="rounded-lg border border-dark-border bg-dark-bg p-4">
                    <textarea
                      className="w-full h-[40vh] bg-transparent text-xs text-gray-300 leading-relaxed whitespace-pre-wrap resize-none outline-none border-none"
                      value={editedContent}
                      onChange={(e) => setEditedContent(e.target.value)}
                      placeholder="编辑内容..."
                    />
                  </div>
                )}
                {!para && els.length > 0 && (
                  <div className="rounded-lg border border-dark-border bg-dark-bg p-4">
                    <textarea
                      className="w-full h-[40vh] bg-transparent text-xs text-gray-300 leading-relaxed whitespace-pre-wrap resize-none outline-none border-none"
                      value={editedContent}
                      onChange={(e) => setEditedContent(e.target.value)}
                      placeholder="编辑内容..."
                    />
                  </div>
                )}

                {/* Toggle for segment details */}
                {segs.length > 0 && (
                  <div>
                    <button
                      onClick={() => setShowSegments(!showSegments)}
                      className="text-[10px] text-gray-500 hover:text-gray-300"
                    >
                      {showSegments ? '▾ 收起时间片段' : `▸ 展开时间片段 (${segs.length} 段)`}
                    </button>
                    {showSegments && (
                      <div className="mt-2 space-y-1 max-h-[30vh] overflow-auto">
                        {segs.map((el: any, i: number) => (
                          <div key={i} className="flex gap-2 text-xs py-1">
                            <span className="text-gray-600 font-mono w-16 shrink-0 text-right">
                              {el.meta?.start_s != null ? `${el.meta.start_s.toFixed(1)}s` : ''}
                            </span>
                            <span className="text-gray-400">{el.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      </Modal>
    );
  }

  // ── Input step ──
  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="上传资料到知识库"
      footer={
        <div className="flex gap-2 justify-end">
          <Button variant="secondary" onClick={handleClose} disabled={loading}>取消</Button>
          {mode === 'directory' ? (
            <Button variant="primary" onClick={handleDirectoryIngest} loading={loading}
              disabled={!dirPath.trim()}>
              开始导入
            </Button>
          ) : (
            <Button variant="primary" onClick={handlePreview} loading={loading}
              disabled={(mode === 'file' && !file) || (mode === 'url' && !url.trim())}>
              预览内容
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-4">
        <div className="flex rounded-lg bg-dark-bg p-0.5">
          <button onClick={() => setMode('file')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
              mode === 'file' ? 'bg-dark-card text-gray-100 shadow' : 'text-gray-400 hover:text-gray-300'
            }`}>上传文件</button>
          <button onClick={() => setMode('url')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
              mode === 'url' ? 'bg-dark-card text-gray-100 shadow' : 'text-gray-400 hover:text-gray-300'
            }`}>资料链接</button>
          <button onClick={() => setMode('directory')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
              mode === 'directory' ? 'bg-dark-card text-gray-100 shadow' : 'text-gray-400 hover:text-gray-300'
            }`}>导入目录</button>
        </div>

        {mode === 'file' ? (
          <div onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-dark-border rounded-xl p-8 text-center cursor-pointer hover:border-primary/50 transition-colors">
            <input ref={fileInputRef} type="file" accept={allAccept} className="hidden" onChange={handleFileChange} />
            {file ? (
              <div>
                <div className="text-2xl mb-2">📎</div>
                <div className="text-sm text-gray-200">{file.name}</div>
                <div className="text-xs text-gray-500 mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
              </div>
        ) : (mode as string) === 'directory' ? (
          <div className="space-y-3">
            <Input label="目录路径" value={dirPath}
              onChange={(e: any) => {
                setDirPath(e.target.value);
                // Auto-name: use last path component as collection name if still default
                const path = e.target.value.trim();
                if (path && collectionId === 'default') {
                  const parts = path.split('/').filter(Boolean);
                  if (parts.length > 0) setCollectionId(parts[parts.length - 1]);
                }
              }}
              placeholder="/Users/apple/Documents/Obsidian Vault" />
            <div className="grid grid-cols-2 gap-3">
              <Input label="文件模式" value={dirPattern}
                onChange={(e: any) => setDirPattern(e.target.value)}
                placeholder="*.md" />
              <div className="flex items-center pt-6 gap-2">
                <input type="checkbox" checked={dirRecursive}
                  onChange={(e) => setDirRecursive(e.target.checked)}
                  className="w-3.5 h-3.5" />
                <span className="text-sm text-gray-400">递归子目录</span>
              </div>
            </div>
            <p className="text-xs text-gray-500">指定服务器上的一个目录路径，批量导入其中匹配的文件。适用于 Obsidian Vault、本地文档库等。</p>
            <div className="flex items-center gap-2 pt-1">
              <input type="checkbox" checked={dirAutoSync}
                onChange={(e) => setDirAutoSync(e.target.checked)}
                className="w-3.5 h-3.5" />
              <span className="text-sm text-gray-400">自动同步（每 30 秒检测变更并增量更新）</span>
            </div>
            {syncResult && (
              <div className="p-3 rounded bg-dark-hover border border-dark-border space-y-1">
                <div className="text-sm text-gray-300 font-medium">最近同步结果</div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="text-center">
                    <div className="text-green-400 font-semibold">{syncResult.total}</div>
                    <div className="text-gray-500">新/更新</div>
                  </div>
                  <div className="text-center">
                    <div className="text-amber-400 font-semibold">{syncResult.cleaned}</div>
                    <div className="text-gray-500">清理</div>
                  </div>
                  <div className="text-center">
                    <div className="text-gray-400 font-semibold">{syncResult.skipped}</div>
                    <div className="text-gray-500">跳过</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
              <div>
                <div className="text-3xl mb-2">📤</div>
                <div className="text-sm text-gray-300">点击选择文件或拖拽到此处</div>
                <div className="text-xs text-gray-500 mt-1">支持 PDF / Word / PPT / Markdown / 视频</div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <Input label="资料链接" value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/document.pdf" />
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Input label="集合" value={collectionId}
            onChange={(e) => setCollectionId(e.target.value)} placeholder="default" />
          {file && (
            <div>
              <div className="text-[10px] text-gray-500 mb-1">识别类型</div>
              <div className="h-10 flex items-center px-3 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-200">
                {ACCEPTED_TYPES[kind]?.label || kind}
              </div>
            </div>
          )}
        </div>

        {uploadProgress && (
          <div className="rounded-lg border border-dark-border bg-dark-card p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400">{uploadProgress.message}</span>
              <span className="text-xs text-gray-500">{Math.round(uploadProgress.pct)}%</span>
            </div>
            <div className="h-2 bg-dark-bg rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, uploadProgress.pct)}%` }} />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
