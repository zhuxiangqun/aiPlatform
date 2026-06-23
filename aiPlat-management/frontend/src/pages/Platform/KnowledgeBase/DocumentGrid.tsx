import React, { useEffect, useState } from 'react';
import { Button, Badge, Modal, toast } from '../../../components/ui';
import { kbApi } from '../../../services';
import type { KBDocument } from '../../../services';
import { useKBStore } from '../../../stores';

interface Props {
  documents: KBDocument[];
  loading: boolean;
  total: number;
  selectedDocIds: Set<string>;
  wikiDocIds?: Set<string>;
}

const CAT_LABELS: Record<string, string> = {
  budget_investment: '预算投资', technical_doc: '技术文档',
  meeting_notes: '会议纪要', general: '通用',
};

const _fmtMs = (ms: any) => {
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return '0:00';
  const total = Math.floor(n / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
};

const _elementPos = (el: any) => {
  const meta = el.meta || {};
  const source = String(meta.source || '').toLowerCase();
  if (source === 'video_transcript' && (meta.start_ms != null || meta.end_ms != null)) {
    return `${_fmtMs(meta.start_ms)} - ${_fmtMs(meta.end_ms)}`;
  }
  if ((source === 'video_ocr' || source === 'video_keyframe') && meta.time_ms != null) {
    return _fmtMs(meta.time_ms);
  }
  return `p${el.page_idx ?? '-'}`;
};

export const DocumentGrid: React.FC<Props> = ({ documents, loading, total, selectedDocIds, wikiDocIds }) => {
  const { toggleDocumentSelection, fetchDocuments, fetchCategories } = useKBStore();
  const [deleting, setDeleting] = useState<string | null>(null);
  const [detailDoc, setDetailDoc] = useState<KBDocument | null>(null);
  const [detailParagraph, setDetailParagraph] = useState<any>(null);
  const [detailSegments, setDetailSegments] = useState<any[]>([]);
  const [detailSegmentsTotal, setDetailSegmentsTotal] = useState(0);
  const [detailSegmentsOffset, setDetailSegmentsOffset] = useState(0);
  const [showSegments, setShowSegments] = useState(false);
  const [detailElementsLoading, setDetailElementsLoading] = useState(false);
  const [segmentsLoading, setSegmentsLoading] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [summaryResult, setSummaryResult] = useState<any>(null);

  const DETAIL_PAGE_SIZE = 100;

  const openDetail = async (doc: KBDocument) => {
    setDetailDoc(doc);
    setDetailParagraph(null);
    setDetailSegments([]);
    setDetailSegmentsTotal(0);
    setDetailSegmentsOffset(0);
    setShowSegments(false);
    setSummaryResult(null);
    setDetailElementsLoading(true);
    try {
      const paraRes = await kbApi.listDocumentElements(doc.doc_id, 'paragraph', 1, 0);
      setDetailParagraph((paraRes.items || [])[0] || null);
    } catch { setDetailParagraph(null); }
    finally { setDetailElementsLoading(false); }
  };

  const toggleSegments = async () => {
    if (showSegments) { setShowSegments(false); return; }
    setShowSegments(true);
    if (detailSegments.length > 0) return;
    if (!detailDoc) return;
    setSegmentsLoading(true);
    try {
      const segRes = await kbApi.listDocumentElements(detailDoc.doc_id, undefined, DETAIL_PAGE_SIZE, 0);
      const segItems = (segRes.items || []).filter((el: any) => el.type !== 'paragraph');
      setDetailSegments(segItems);
      setDetailSegmentsTotal((segRes.total || 0) - (detailParagraph ? 1 : 0));
      setDetailSegmentsOffset(DETAIL_PAGE_SIZE);
    } catch {}
    finally { setSegmentsLoading(false); }
  };

  const loadMoreSegments = async () => {
    if (!detailDoc || segmentsLoading) return;
    setSegmentsLoading(true);
    try {
      const res = await kbApi.listDocumentElements(detailDoc.doc_id, undefined, DETAIL_PAGE_SIZE, detailSegmentsOffset);
      setDetailSegments(prev => [...prev, ...(res.items || []).filter((el: any) => el.type !== 'paragraph')]);
      setDetailSegmentsOffset(prev => prev + DETAIL_PAGE_SIZE);
    } catch {}
    finally { setSegmentsLoading(false); }
  };

  const handleSummarize = async () => {
    if (!detailDoc) return;
    setSummarizing(true); setSummaryResult(null);
    try { setSummaryResult(await kbApi.documentSummarize(detailDoc.doc_id, 'key_points', 8)); }
    catch (e: any) { toast.error(`摘要失败：${e?.message || e}`); }
    finally { setSummarizing(false); }
  };

  const handleDelete = async (docId: string) => {
    setDeleting(docId);
    try { await kbApi.deleteDocument(docId); toast.success('已删除'); await fetchDocuments(); await fetchCategories(); }
    catch (e: any) { toast.error(`删除失败：${e?.message || e}`); }
    finally { setDeleting(null); }
  };

  const handleReingest = async (docId: string) => {
    try { await kbApi.reingestDocument(docId); toast.success('已重新处理'); }
    catch (e: any) { toast.error(`重新处理失败：${e?.message || e}`); }
  };

  if (loading) return <div className="text-sm text-gray-400 py-12 text-center">加载中...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-200">文档列表</span>
        <span className="text-xs text-gray-500">共 {total} 份</span>
      </div>

      {documents.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <div className="text-4xl mb-2">📂</div>
          <div className="text-sm">暂无文档</div>
          <div className="text-xs mt-1">点击"上传资料"开始</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
          {documents.map((doc) => {
            const isSelected = selectedDocIds.has(doc.doc_id);
            const cls = doc.meta?.classification || {};
            const contentCat = cls.content_category || 'general';

            return (
              <div key={doc.doc_id}
                onClick={() => toggleDocumentSelection(doc.doc_id)}
                className={`rounded-lg border p-3 cursor-pointer transition-all ${
                  isSelected ? 'border-primary bg-primary/5 shadow-sm shadow-primary/10' : 'border-dark-border bg-dark-card hover:border-gray-600'
                }`}>
                <div className="flex items-start gap-3">
                  <span className="text-xl mt-0.5">{doc.kind === 'video' ? '🎬' : doc.kind === 'pdf' ? '📄' : '📋'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-200 truncate">
                      {String(doc.meta?.name || doc.meta?.title || doc.source_uri || doc.doc_id).split('/').pop()}
                    </div>
                    <div className="text-xs text-gray-500 truncate mt-0.5">{String(doc.source_uri || '')}</div>
                    <div className="flex items-center gap-1.5 mt-1.5">
                      {wikiDocIds?.has(doc.doc_id) ? (
                        <Badge variant="success" className="text-[10px] px-1.5 py-0">已入库 · 已关联</Badge>
                      ) : doc.status === 'ready' ? (
                        <Badge variant="success" className="text-[10px] px-1.5 py-0">已入库</Badge>
                      ) : (
                        <Badge variant="warning" className="text-[10px] px-1.5 py-0">{doc.status}</Badge>
                      )}
                      <span className="text-[10px] text-gray-500">{CAT_LABELS[contentCat] || contentCat}</span>
                      {(doc.element_count ?? 0) > 0 && <span className="text-[10px] text-gray-600">{doc.element_count} 元素</span>}
                    </div>
                    {/* Wiki indicator: unified ✅ badge */}
                    {wikiDocIds?.has(doc.doc_id) && (
                      <span className="text-[11px] text-green-500/80 ml-1" title="已生成知识页面">✅</span>
                    )}
                  </div>
                  <div className="flex gap-0.5 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="sm" onClick={() => openDetail(doc)}>详情</Button>
                    <Button variant="ghost" size="sm" onClick={() => handleReingest(doc.doc_id)}>重处理</Button>
                    <Button variant="ghost" size="sm" loading={deleting === doc.doc_id} onClick={() => handleDelete(doc.doc_id)}>删除</Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {detailDoc && (
        <Modal open={!!detailDoc} onClose={() => setDetailDoc(null)} title="文档详情">
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <div><span className="text-gray-400">类型: </span><span className="text-gray-200">{detailDoc.kind}</span></div>
              <div><span className="text-gray-400">状态: </span><span className="text-gray-200">{detailDoc.status}</span></div>
              <div><span className="text-gray-400">元素: </span><span className="text-gray-200">{detailDoc.element_count ?? '-'} 文本 · {detailDoc.embedding_count ?? '-'} 向量</span></div>
              {detailDoc.meta?.classification && (
                <div><span className="text-gray-400">分类: </span><span className="text-gray-200">{CAT_LABELS[detailDoc.meta.classification.content_category || ''] || detailDoc.meta.classification.content_category || '通用'}</span></div>
              )}
            </div>
            <div><span className="text-gray-400">来源: </span><span className="text-gray-200 break-all text-xs">{detailDoc.source_uri}</span></div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400">内容预览</span>
                <Button variant="ghost" size="sm" loading={summarizing} onClick={handleSummarize}>生成摘要</Button>
              </div>
              {summaryResult ? (
                <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
                  <div className="text-xs text-gray-500 mb-2">{summaryResult.summary || summaryResult.output?.summary || ''}</div>
                  {(summaryResult.points || summaryResult.output?.points || []).slice(0, 8).map((p: any, i: number) => (
                    <div key={i} className="text-xs text-gray-300 mt-1 flex gap-2">
                      <span className="text-gray-500 w-5">{p.idx || i + 1}.</span>
                      <span className="flex-1">{p.text}</span>
                      {p.page_idx != null && <span className="text-gray-500">p{p.page_idx}</span>}
                    </div>
                  ))}
                </div>
              ) : detailElementsLoading && !detailParagraph ? (
                <div className="text-xs text-gray-500">加载中...</div>
              ) : (
                <div className="space-y-3">
                  {detailParagraph ? (
                    <div className="rounded-lg border border-dark-border bg-dark-bg p-3">
                      <div className="text-xs text-gray-500 mb-1">转录全文</div>
                      <div className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap max-h-[60vh] overflow-auto">{String(detailParagraph.text || '')}</div>
                    </div>
                  ) : <div className="text-xs text-gray-500">无内容</div>}
                  {((detailDoc?.element_count ?? 0) - (detailParagraph ? 1 : 0)) > 0 && (
                    <div>
                      <button onClick={toggleSegments} className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1">
                        <span>{showSegments ? '▾' : '▸'}</span> 查看索引分段 ({(detailDoc?.element_count ?? 0) - (detailParagraph ? 1 : 0)})
                      </button>
                      {showSegments && (
                        <div className="mt-2">
                          {segmentsLoading ? <div className="text-xs text-gray-500">加载中...</div> :
                           detailSegments.length > 0 ? (
                            <div className="space-y-1 max-h-80 overflow-auto">
                              {detailSegments.map((el: any, i: number) => (
                                <div key={i} className="rounded border border-dark-border bg-dark-bg p-2">
                                  <div className="text-xs text-gray-500 mb-1">{el.type} · {_elementPos(el)}</div>
                                  <div className="text-xs text-gray-300 whitespace-pre-wrap">{String(el.text || '')}</div>
                                </div>
                              ))}
                              {detailSegments.length < (detailSegmentsTotal || 0) && (
                                <Button variant="ghost" size="sm" loading={segmentsLoading} onClick={loadMoreSegments} className="mt-2 w-full">
                                  加载更多 ({detailSegments.length}/{detailSegmentsTotal})
                                </Button>
                              )}
                            </div>
                          ) : <div className="text-xs text-gray-500">无索引分段</div>}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Wiki backlinks */}
            {wikiDocIds?.has(detailDoc.doc_id) && (
              <WikiBacklinks docId={detailDoc.doc_id} />
            )}
          </div>
        </Modal>
      )}
    </div>
  );
};

// ── Wiki backlinks for document detail ──

const WikiBacklinks = ({ docId }: { docId: string }) => {
  const [pages, setPages] = useState<any[]>([]);

  useEffect(() => {
    fetch(`/api/platform/kb/vault/wiki/backlinks?doc_id=${encodeURIComponent(docId)}`)
      .then(r => r.json())
      .then(d => setPages(d.pages || []))
      .catch(() => setPages([]));
  }, [docId]);

  return (
    <div className="mt-3 p-2 rounded bg-dark-hover">
      <div className="text-xs font-medium text-gray-400 mb-1">
        Wiki 反向链接 {pages.length > 0 && <span className="text-gray-600">({pages.length})</span>}
      </div>
      {pages.length > 0 ? (
        pages.map((p: any, i: number) => (
          <div key={i} className="flex items-center gap-1 text-xs py-0.5">
            <span className="text-primary font-medium">{p.title || '?'}</span>
            <span className="text-gray-600">({p.category || ''})</span>
            {p.summary && <span className="text-gray-500 truncate">- {String(p.summary).slice(0, 80)}</span>}
          </div>
        ))
      ) : (
        <div className="text-xs text-gray-600">暂无反向链接</div>
      )}
    </div>
  );
};

export default DocumentGrid;
