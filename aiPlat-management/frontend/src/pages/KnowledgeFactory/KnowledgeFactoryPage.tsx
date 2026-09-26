/**
 * KnowledgeFactoryPage — 知识工厂 (知识生产与本体治理聚合页)
 *
 * 流水线:
 *   ① 知识抽取 — 文档 → LLM 实体/关系 → 待审确认（可入队提案）
 *   ①b 代码/表头建议 — 粘贴代码/ER → 类建议提案草稿（禁自动 apply）
 *   ② 跨域解析 — 跨域同名/近义实体关联消歧
 *   ③ 本体演进 — 版本化 YAML 提案 → 审核 → 应用
 *
 * 表/CSV·webhook 入轨在 FDE⑦（写 GraphIndex），勿与本页「建说明书」混淆。
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import GovernanceLoopPanel from '../Knowledge/GovernanceLoopPanel';
import OrgL5Panel from '../Knowledge/OrgL5Panel';
import BusinessOntologyGuide from '../../components/knowledge/BusinessOntologyGuide';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import {
  Upload, FileText, ArrowRightLeft,
  RefreshCw, Brain, GitBranch, XCircle, Code2, Table2,
} from 'lucide-react';
import FactoryProgressGuide from './FactoryProgressGuide';

const API = (path: string) => `/api/platform/apps/fde${path}`;
const WIKI_DOMAINS_API = '/api/core/wiki/ontology/domains';
/** 常用交付域置顶；完整列表与「手动画类」同源（registry，当前约 20+） */
const PREFERRED_DOMAIN_ORDER = ['lock-service', 'it-ops', 'supply-chain', 'procurement-mvo', 'service-domain'];
const PLATFORM_DOMAIN_IDS = new Set([
  'default', 'ai-knowledge', 'ai-solution', 'aiplat-system',
  'enterprise-terms', 'fde-delivery', 'knowledge-atom',
]);
const DEFAULT_DOMAIN = 'lock-service';

type DomainId = string;
type DomainOption = { id: string; label: string; classCount?: number; description?: string };
type DomainFilter = 'preferred' | 'other' | 'bell' | 'platform' | 'all';

function domainGroup(id: string): Exclude<DomainFilter, 'all'> {
  if (PREFERRED_DOMAIN_ORDER.includes(id)) return 'preferred';
  if (id.startsWith('bell-')) return 'bell';
  if (PLATFORM_DOMAIN_IDS.has(id)) return 'platform';
  return 'other';
}

const FILTER_CHIPS: { id: DomainFilter; label: string; hint: string }[] = [
  { id: 'preferred', label: '常用交付', hint: '锁服务 / IT运维 / 供应链等，日常只看这些' },
  { id: 'other', label: '其他行业', hint: '金融/政务等样例' },
  { id: 'bell', label: 'Bell 业务线', hint: '演示客户多线种子' },
  { id: 'platform', label: '平台/系统', hint: '系统自用，勿当客户业务域' },
  { id: 'all', label: '全部', hint: '注册表全量' },
];

/** 展示当前域已有说明书，消除「像在新建」的错觉 */
const ExistingDomainBanner: React.FC<{ domainId: string; fallbackLabel?: string }> = ({
  domainId,
  fallbackLabel,
}) => {
  const [info, setInfo] = useState<{
    name: string;
    version?: string;
    classCount: number;
    propCount: number;
    classLabels: string[];
  } | null>(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    setErr('');
    fetch(`${WIKI_DOMAINS_API}/${encodeURIComponent(domainId)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        if (cancelled) return;
        const classes = Array.isArray(d.classes) ? d.classes : [];
        const labels = classes
          .map((c: any) => String(c.label || c.uri || '').trim())
          .filter(Boolean)
          .slice(0, 8);
        setInfo({
          name: String(d.name || fallbackLabel || domainId),
          version: d.version ? String(d.version) : undefined,
          classCount: classes.length,
          propCount: (d.object_properties?.length || 0) + (d.data_properties?.length || 0),
          classLabels: labels,
        });
      })
      .catch((e) => {
        if (!cancelled) setErr(e?.message || '加载失败');
      });
    return () => { cancelled = true; };
  }, [domainId, fallbackLabel]);

  return (
    <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-4 py-3 space-y-2">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[12px] text-emerald-200/90 font-medium">
            写入已有说明书 · 不会新建域
          </div>
          <div className="text-sm text-gray-100 mt-0.5">
            {info?.name || fallbackLabel || domainId}
            <span className="ml-2 font-mono text-[11px] text-gray-500">{domainId}</span>
            {info?.version && (
              <span className="ml-2 text-[11px] text-gray-500">v{info.version}</span>
            )}
          </div>
        </div>
        <Link
          to={`/knowledge/business?tab=domains&domain=${encodeURIComponent(domainId)}`}
          className="text-[12px] text-sky-400 hover:underline shrink-0"
        >
          在「手动画类」查看结构 →
        </Link>
      </div>
      {err && <div className="text-[11px] text-amber-300/90">{err}</div>}
      {info && (
        <>
          <div className="text-[11px] text-gray-400">
            已有 <strong className="text-gray-200 font-medium">{info.classCount}</strong> 个类 ·{' '}
            <strong className="text-gray-200 font-medium">{info.propCount}</strong> 个属性/关系
            {info.classCount === 0 && '（空骨架，文档写入会补类）'}
          </div>
          {info.classLabels.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {info.classLabels.map((lab) => (
                <span
                  key={lab}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-gray-900/70 border border-gray-700/60 text-gray-300"
                >
                  {lab}
                </span>
              ))}
              {info.classCount > info.classLabels.length && (
                <span className="text-[10px] text-gray-500 self-center">
                  +{info.classCount - info.classLabels.length}
                </span>
              )}
            </div>
          )}
          <p className="text-[11px] text-gray-500 leading-relaxed">
            本页只是往这份说明书<strong className="text-gray-400 font-medium">追加/修订草稿</strong>
            （提案经你同意后写入）。锁安等已建好的类会出现在上方标签里，无需也不应再「另建一个域」。
          </p>
        </>
      )}
      {!info && !err && (
        <div className="text-[11px] text-gray-500">正在读取已有类…</div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ① KnowledgeExtractionPanel — 文件上传 + 文本粘贴双模式
// ═══════════════════════════════════════════════════════════
const KnowledgeExtractionPanel: React.FC<{ domainId: DomainId }> = ({ domainId }) => {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [pending, setPending] = useState<any[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reloadPending = useCallback(() => {
    const q = domainId ? `?domain_id=${encodeURIComponent(domainId)}` : '';
    fetch(API(`/extractions/pending${q}`))
      .then((r) => r.json())
      .then((d) => setPending(d.pending || []))
      .catch(() => {});
  }, [domainId]);

  useEffect(() => {
    reloadPending();
  }, [reloadPending]);

  const mergePending = (incoming: any[]) => {
    const newPending = incoming.filter((e: any) => e.status === 'pending');
    if (!newPending.length) return;
    setPending((prev) => [
      ...newPending,
      ...prev.filter((p) => !newPending.find((n: any) => n.extraction_id === p.extraction_id)),
    ]);
  };

  const extractOne = async (payload: {
    file?: File;
    text?: string;
    docName: string;
  }) => {
    const formData = new FormData();
    if (payload.file) formData.append('file', payload.file);
    if (payload.text?.trim()) formData.append('text', payload.text);
    formData.append('domain_id', domainId || DEFAULT_DOMAIN);
    formData.append('doc_name', payload.docName);
    const r = await fetch(API('/extract'), { method: 'POST', body: formData });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `抽取失败：${payload.docName}`);
    return d as { extractions?: any[]; warning?: string; ok?: boolean };
  };

  const handleExtract = async () => {
    if (!text.trim() && files.length === 0) return;
    setLoading(true);
    setProgress('');
    const all: any[] = [];
    let failed = 0;
    let warnings: string[] = [];
    try {
      const jobs: { label: string; run: () => Promise<{ extractions?: any[]; warning?: string; ok?: boolean }> }[] = [];
      files.forEach((f) => {
        jobs.push({
          label: f.name,
          run: () => extractOne({ file: f, docName: f.name }),
        });
      });
      if (text.trim()) {
        jobs.push({
          label: '粘贴文本',
          run: () =>
            extractOne({
              text,
              docName: `粘贴文本-${new Date().toISOString().slice(0, 10)}`,
            }),
        });
      }

      for (let i = 0; i < jobs.length; i++) {
        const job = jobs[i];
        setProgress(`正在抽取 ${i + 1}/${jobs.length}：${job.label}`);
        try {
          const d = await job.run();
          const batch = d.extractions || [];
          all.push(...batch);
          mergePending(batch);
          if (d.warning) warnings.push(`${job.label}：${d.warning}`);
        } catch {
          failed += 1;
        }
      }

      setResults(all);
      if (files.length) setFiles([]);
      if (text.trim()) setText('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      // 以服务端为准刷新待确认（含 domain 过滤），避免只依赖本批 merge
      reloadPending();

      const entityTotal = all.reduce((s, r) => s + (r.entity_count || 0), 0);
      const pendingCount = all.filter((r) => r.status === 'pending').length;

      if (entityTotal > 0 && failed === 0) {
        toast?.success?.(
          `完成：${jobs.length} 份 · ${entityTotal} 实体` +
            (pendingCount ? ` · ${pendingCount} 条待确认` : ''),
        );
      } else if (entityTotal > 0 && failed > 0) {
        toast?.info?.(`部分完成：${entityTotal} 实体，失败 ${failed} 份`);
      } else if (warnings.length) {
        toast?.error?.(warnings[0]);
      } else if (failed > 0) {
        toast?.error?.('抽取请求失败，请检查平台服务与模型是否可用');
      } else {
        toast?.error?.(
          '抽取结果为空（0 实体）。常见原因：LLM 不可用，或 PDF 无法抽出文字。请改用粘贴纯文本重试。',
        );
      }
    } catch {
      toast?.error?.('抽取失败');
    } finally {
      setLoading(false);
      setProgress('');
    }
  };

  const handleConfirm = async (id: string) => {
    try {
      const r = await fetch(API(`/extractions/${id}/confirm`), { method: 'POST' });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || '确认失败');
      setPending(prev => prev.filter(p => p.extraction_id !== id));
      toast?.success?.(
        `已确认：信号 ${d.signal_id || '—'}` +
          (d.proposal_id ? ` · 提案 ${d.proposal_id}（见③）` : '') +
          (d.graph_write && !d.graph_write.error
            ? ` · 知识图 +${(d.graph_write.created_entities || []).length} 实体 / ${(d.graph_write.relations || []).length} 关系`
            : ' · 说明书 YAML 未改') +
          `；活本体未改`,
      );
      if (d.proposal_id && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('factory-proposal-enqueued', { detail: d.proposal_id }));
      }
    } catch (e: any) {
      toast?.error?.(e?.message || '确认失败');
    }
  };

  const handleReject = async (id: string) => {
    await fetch(API(`/extractions/${id}/reject`), { method: 'POST' });
    setPending(prev => prev.filter(p => p.extraction_id !== id));
    toast?.info?.('已忽略');
  };

  const addFiles = (list: FileList | File[] | null) => {
    if (!list || !list.length) return;
    const next = Array.from(list);
    setFiles((prev) => {
      const names = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const merged = [...prev];
      for (const f of next) {
        const key = `${f.name}:${f.size}`;
        if (!names.has(key)) {
          names.add(key);
          merged.push(f);
        }
      }
      return merged;
    });
    setText('');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(e.target.files);
    e.target.value = '';
  };

  const removeFileAt = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const clearFiles = () => {
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <Card id="factory-extract" className="border-blue-500/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-blue-500/10 text-blue-400">
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <span className="text-sm font-semibold text-gray-100">① 上传或粘贴文档</span>
            <span className="text-[11px] text-gray-500 ml-2">分析 → 确认 = 写入知识图（实体/关系）</span>
          </div>
          {pending.length > 0 && (
            <span className="text-[10px] bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded ml-auto">
              {pending.length} 条待你确认
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* File upload area */}
        <div
          className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
            files.length ? 'border-blue-500 bg-blue-500/5' : 'border-gray-700 hover:border-gray-500'
          }`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            addFiles(e.dataTransfer.files);
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt,.md,.pptx,.xlsx,.csv,.html,.json,.xml"
            onChange={handleFileChange}
            className="hidden"
          />
          {files.length > 0 ? (
            <div className="space-y-2 text-left" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between text-[11px] text-gray-400 px-0.5">
                <span>已选 {files.length} 个文件（可继续添加）</span>
                <button type="button" className="text-red-400/80 hover:text-red-300" onClick={clearFiles}>
                  清空
                </button>
              </div>
              <ul className="max-h-36 overflow-auto space-y-1">
                {files.map((f, i) => (
                  <li
                    key={`${f.name}-${f.size}-${i}`}
                    className="flex items-center gap-2 rounded bg-gray-900/60 px-2 py-1.5"
                  >
                    <FileText className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                    <span className="text-xs text-blue-200 truncate flex-1">{f.name}</span>
                    <span className="text-[10px] text-gray-500 shrink-0">{(f.size / 1024).toFixed(1)} KB</span>
                    <button
                      type="button"
                      className="text-gray-500 hover:text-red-400"
                      onClick={() => removeFileAt(i)}
                      title="移除"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="text-[10px] text-gray-500 text-center pt-1">
                点击空白处或拖拽可继续添加文件
              </div>
            </div>
          ) : (
            <div className="text-gray-500">
              <Upload className="w-5 h-5 mx-auto mb-1" />
              <span className="text-xs">拖拽多个文件至此，或点击多选上传 (PDF/Word/Markdown/Excel 等)</span>
            </div>
          )}
        </div>

        {/* Text paste area */}
        <div className="relative">
          <div className="text-[10px] text-gray-500 mb-1">
            或直接粘贴一段说明文字
          </div>
          <textarea
            className="w-full h-28 bg-gray-800 border border-gray-700 rounded p-2.5 text-xs text-gray-200 resize-y"
            placeholder="例如：产品手册、安装流程、告警说明…"
            value={text}
            onChange={e => setText(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="default"
            size="sm"
            loading={loading}
            onClick={handleExtract}
            disabled={!text.trim() && files.length === 0}
          >
            {files.length > 0
              ? `开始分析（${files.length} 个文件${text.trim() ? ' + 文字' : ''}）`
              : '开始分析'}
          </Button>
          {progress && <span className="text-[11px] text-sky-400">{progress}</span>}
          {results.length > 0 && !loading && (
            <span className="text-xs text-gray-400">
              最近找出{' '}
              <span className={results.some((r) => r.entity_count > 0) ? 'text-green-400' : 'text-amber-400'}>
                {results.reduce((s: number, r: any) => s + (r.entity_count || 0), 0)} 项
              </span>
            </span>
          )}
        </div>

        {results.length > 0 && !loading && results.every((r) => !(r.entity_count > 0)) && (
          <div className="rounded border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-100/90 leading-relaxed">
            这次没有找出可用内容，下方不会出现待确认列表。
            请确认模型可用，或改成粘贴纯文本再试。扫描版 PDF 往往读不出字。
          </div>
        )}

        {/* Pending confirmations */}
        {pending.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-gray-700/50">
            <div className="text-xs text-gray-500">
              待你确认（{pending.length}）
              <span className="text-[10px] text-gray-600 ml-1">— 点确认后才会进入「写入说明书」</span>
            </div>
            {pending.map((p: any) => {
              let preview: { name?: string; class_type?: string }[] = [];
              try {
                const raw = typeof p.entities_json === 'string' ? JSON.parse(p.entities_json) : p.entities_json;
                if (Array.isArray(raw)) preview = raw.slice(0, 6);
              } catch {
                preview = [];
              }
              if (!preview.length && Array.isArray(p.top_entities)) preview = p.top_entities.slice(0, 6);
              return (
                <div key={p.extraction_id} className="p-2.5 rounded bg-gray-800/50 border border-yellow-700/30">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-xs text-gray-200">{p.source_doc}</span>
                      <span className="text-[10px] text-gray-500 ml-2">
                        {((p.overall_confidence || 0) * 100).toFixed(0)}% · {p.entity_count}实体 · {p.relation_count}关系
                      </span>
                      {preview.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {preview.map((e, i) => (
                            <span
                              key={`${e.name || i}-${i}`}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-gray-900/80 text-amber-100/90 border border-amber-900/40"
                            >
                              {e.name || '?'}
                              {e.class_type ? (
                                <span className="text-gray-500 ml-1">{e.class_type}</span>
                              ) : null}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-green-400 text-[10px] py-0 h-6"
                        onClick={() => handleConfirm(p.extraction_id)}
                      >
                        确认
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 text-[10px] py-0 h-6"
                        onClick={() => handleReject(p.extraction_id)}
                      >
                        忽略
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};


const factoryRoleHeaders = (): Record<string, string> => ({
  'Content-Type': 'application/json',
  'X-AIPLAT-ROLE':
    (typeof localStorage !== 'undefined' && localStorage.getItem('aiplat_role')) || 'analyst',
});

// ═══════════════════════════════════════════════════════════
// ② CrossDomainResolutionPanel — 跨域实体解析
// ═══════════════════════════════════════════════════════════
const CrossDomainResolutionPanel: React.FC = () => {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [tickets, setTickets] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewName, setViewName] = useState('unified_customer');
  const [meta, setMeta] = useState<{ sources?: any[]; hint?: string }>({});

  const VIEWS = [
    { key: 'unified_customer', label: '锁安↔售后' },
    { key: 'bell_unified_client', label: 'Bell24统一客户' },
    { key: 'bell_unified_technology', label: 'Bell24技术资产' },
    { key: 'bell_group_structure', label: 'Bell24集团架构' },
  ];

  const reloadTickets = useCallback(() => {
    fetch(API('/resolution/tickets'))
      .then((r) => r.json())
      .then((d) => setTickets(d.items || d.tickets || []))
      .catch(() => setTickets([]));
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    fetch(API(`/resolution/candidates?view_name=${viewName}`))
      .then((r) => r.json())
      .then((d) => {
        setCandidates(d.candidates || []);
        setMeta({ sources: d.sources || [], hint: d.hint || '' });
      })
      .catch(() => {
        setCandidates([]);
        setMeta({});
      })
      .finally(() => setLoading(false));
    reloadTickets();
  }, [viewName, reloadTickets]);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleResolve = async (c: any) => {
    setLoading(true);
    try {
      const r = await fetch(API('/resolution/resolve'), {
        method: 'POST',
        headers: factoryRoleHeaders(),
        body: JSON.stringify({
          view_name: viewName,
          left_id: c.left.id,
          left_domain: c.left.domain,
          right_id: c.right.id,
          right_domain: c.right.domain,
          confidence: c.score,
          strategy: c.strategy || '',
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.reason || d.detail || '开票失败');
      setCandidates((prev) => prev.filter((x) => x !== c));
      toast?.success?.(
        d.ticket_id
          ? `已开仲裁票 ${d.ticket_id}（未写边）`
          : '已提交跨域仲裁',
      );
      reloadTickets();
    } catch (e: any) {
      toast?.error?.(e?.message || '关联失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDecide = async (ticketId: string, decision: string) => {
    setLoading(true);
    try {
      const r = await fetch(API(`/resolution/tickets/${ticketId}/decide`), {
        method: 'POST',
        headers: factoryRoleHeaders(),
        body: JSON.stringify({ decision, actor: 'factory-ui' }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.reason || d.detail || '裁决失败');
      toast?.success?.(decision === 'merge' ? `已批准合并 ${ticketId}` : `已${decision} ${ticketId}`);
      reloadTickets();
    } catch (e: any) {
      toast?.error?.(e?.message || '裁决失败');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyTicket = async (ticketId: string) => {
    setLoading(true);
    try {
      const r = await fetch(API(`/resolution/tickets/${ticketId}/apply`), {
        method: 'POST',
        headers: factoryRoleHeaders(),
        body: JSON.stringify({ actor: 'factory-ui' }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.reason || d.detail || '写边失败');
      toast?.success?.(d.edge_written || d.wrote_cross_domain_edge ? `已写跨域边 ${ticketId}` : `已处理 ${ticketId}`);
      reloadTickets();
    } catch (e: any) {
      toast?.error?.(e?.message || '写边失败');
    } finally {
      setLoading(false);
    }
  };

  const openTickets = tickets.filter(
    (t) => !t.applied && ['pending', 'approved', 'deferred', 'conflict'].includes(t.status),
  );

  return (
    <Card className="border-purple-500/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-purple-500/10 text-purple-400">
            <ArrowRightLeft className="w-5 h-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div>
              <span className="text-sm font-semibold text-gray-100">跨业务对齐</span>
              <span className="text-[11px] text-gray-500 ml-2">高级 · 可跳过</span>
            </div>
            <p className="text-[11px] text-gray-500 mt-0.5 leading-relaxed max-w-xl">
              判断两边是不是同一个对象。日常写说明书不用管这里。
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <select
              value={viewName}
              className="text-[10px] bg-gray-800 border border-gray-700 text-gray-400 rounded px-2 py-1"
              onChange={(e) => setViewName(e.target.value)}
            >
              {VIEWS.map((v) => (
                <option key={v.key} value={v.key}>{v.label}</option>
              ))}
            </select>
            <Button variant="ghost" size="sm" className="h-6 text-[10px] text-gray-400" onClick={reload}>
              <RefreshCw className="w-3 h-3" />
            </Button>
            {candidates.length > 0 && (
              <span className="text-[10px] bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">
                {candidates.length} 候选
              </span>
            )}
            {openTickets.length > 0 && (
              <span className="text-[10px] bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">
                {openTickets.length} 票
              </span>
            )}
            {loading && <span className="text-[10px] text-gray-500 animate-pulse ml-1">加载中...</span>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {candidates.length === 0 ? (
          <div className="text-xs text-gray-500 space-y-2 py-1">
            <div className="text-center text-gray-600">暂无跨域候选</div>
            {(meta.sources || []).length > 0 && (
              <div className="flex flex-wrap gap-2 justify-center text-[10px] text-gray-500">
                {(meta.sources || []).map((s: any, i: number) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-gray-800/80 border border-gray-700/50">
                    {s.domain}{s.class ? `/${s.class}` : ''} · {s.entity_count ?? 0} 实体
                  </span>
                ))}
              </div>
            )}
            <div className="text-[11px] text-amber-200/80 leading-relaxed px-1">
              {meta.hint ||
                '需要两侧 GraphIndex 有可对齐实例（同 customer_name / 近似名称）。请去 FDE⑦ 导入。'}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-[10px] text-gray-500">候选（点开票，不会立刻写边）</div>
            {candidates.slice(0, 10).map((c, i) => (
              <div key={i} className="p-2.5 rounded bg-gray-800/50 border border-gray-700/30">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs">
                    <span className="text-gray-200">{c.left.name}</span>
                    <span className="text-gray-600 mx-1.5">↔</span>
                    <span className="text-gray-200">{c.right.name}</span>
                  </div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
                    {(c.score * 100).toFixed(0)}% · {c.strategy || '—'}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mb-1.5">
                  {c.left.domain} ↔ {c.right.domain}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-purple-400 text-[10px] py-0 h-5"
                  loading={loading}
                  onClick={() => handleResolve(c)}
                >
                  开仲裁票
                </Button>
              </div>
            ))}
          </div>
        )}

        {openTickets.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-gray-700/40">
            <div className="text-[10px] text-gray-500">仲裁票（批准 merge 后再 apply 写边）</div>
            {openTickets.slice(0, 8).map((t) => (
              <div key={t.ticket_id} className="p-2.5 rounded bg-gray-800/50 border border-purple-700/30">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs text-gray-200 truncate">
                      {t.left_id} ↔ {t.right_id}
                    </div>
                    <div className="text-[10px] text-gray-500">
                      {t.left_domain} ↔ {t.right_domain} · {t.status}
                      <span className="font-mono ml-1 text-gray-600">{t.ticket_id}</span>
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {t.status === 'pending' && (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-green-400 text-[10px] py-0 h-6"
                          onClick={() => handleDecide(t.ticket_id, 'merge')}
                        >
                          批准合并
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-400 text-[10px] py-0 h-6"
                          onClick={() => handleDecide(t.ticket_id, 'reject')}
                        >
                          驳回
                        </Button>
                      </>
                    )}
                    {t.status === 'approved' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-blue-400 text-[10px] py-0 h-6"
                        onClick={() => handleApplyTicket(t.ticket_id)}
                      >
                        写边
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// ①b SuggestPanel — 代码 OR 表头/CSV → 提案草稿（禁自动 apply / 禁写图）
// ═══════════════════════════════════════════════════════════
const CodeSuggestionPanel: React.FC<{
  domainId: DomainId;
  onEnqueued?: (proposalId: string) => void;
}> = ({ domainId, onEnqueued }) => {
  const [mode, setMode] = useState<'code' | 'schema'>('schema');
  const [snippet, setSnippet] = useState(
    'class ServiceEndpoint:\n    pass\n# 表: AlertEvent\n实体 MiddlewarePool',
  );
  const [tableName, setTableName] = useState('alert_events');
  const [csvText, setCsvText] = useState(
    'id,service_name,severity,state\nA1,SVC-查询,critical,open\n',
  );
  const [loading, setLoading] = useState(false);
  const [last, setLast] = useState<any>(null);

  const runCodeSuggest = async (enqueue: boolean) => {
    setLoading(true);
    try {
      const r = await fetch(API('/ontology/code-suggestions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain_id: domainId || DEFAULT_DOMAIN,
          snippets: [snippet],
          enqueue,
          author: 'factory-ui',
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || '建议失败');
      setLast(d);
      const n = (d.suggestions || []).length;
      if (enqueue && d.proposal_id) {
        toast?.success?.(`已入队提案草稿 ${d.proposal_id}（禁自动 apply）`);
        onEnqueued?.(d.proposal_id);
      } else {
        toast?.success?.(`扫描到 ${n} 个类建议（未入队）`);
      }
    } catch (e: any) {
      toast?.error?.(e?.message || '代码建议失败');
    } finally {
      setLoading(false);
    }
  };

  const runSchemaSuggest = async (enqueue: boolean) => {
    setLoading(true);
    try {
      const r = await fetch(API('/ontology/schema-suggestions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain_id: domainId || DEFAULT_DOMAIN,
          table_name: tableName,
          csv_text: csvText,
          enqueue,
          author: 'factory-schema-ui',
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || '表头建议失败');
      setLast(d);
      const s0 = (d.suggestions || [])[0];
      if (enqueue && d.proposal_id) {
        toast?.success?.(
          `表头→提案 ${d.proposal_id} · 类 ${s0?.name || '—'}（禁自动 apply；≠写图）`,
        );
        onEnqueued?.(d.proposal_id);
      } else {
        toast?.success?.(
          `建议类 ${s0?.name || '—'} · 字段 ${(s0?.required_fields || []).join(',') || '—'}`,
        );
      }
    } catch (e: any) {
      toast?.error?.(e?.message || '表头建议失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card id="factory-code-suggest" className="border-cyan-500/20">
      <CardHeader>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="p-1.5 rounded bg-cyan-500/10 text-cyan-400">
            {mode === 'schema' ? <Table2 className="w-5 h-5" /> : <Code2 className="w-5 h-5" />}
          </div>
          <div className="flex-1 min-w-[200px]">
            <span className="text-sm font-semibold text-gray-100">①b 从表头生成（可选）</span>
            <span className="text-[11px] text-gray-500 ml-2">
              粘贴表头 → 生成类建议；写数据行请去 FDE
            </span>
          </div>
          <div className="flex gap-1 text-[10px]">
            <button
              type="button"
              className={`px-2 py-1 rounded border ${mode === 'schema' ? 'border-cyan-600 text-cyan-200 bg-cyan-950/40' : 'border-gray-700 text-gray-500'}`}
              onClick={() => setMode('schema')}
            >
              表头/CSV
            </button>
            <button
              type="button"
              className={`px-2 py-1 rounded border ${mode === 'code' ? 'border-cyan-600 text-cyan-200 bg-cyan-950/40' : 'border-gray-700 text-gray-500'}`}
              onClick={() => setMode('code')}
            >
              代码片段
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {mode === 'schema' ? (
          <>
            <input
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-[11px] text-gray-200"
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
              placeholder="表名 table_name"
            />
            <textarea
              className="w-full min-h-[100px] bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-[11px] font-mono text-gray-300"
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder="CSV：首行表头 + 可选样例行"
            />
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" size="sm" loading={loading} onClick={() => runSchemaSuggest(false)}>
                仅预览建议类
              </Button>
              <Button variant="default" size="sm" loading={loading} onClick={() => runSchemaSuggest(true)}>
                表头入队提案
              </Button>
              <Link
                to="/diagnostics/fde"
                className="text-[11px] text-gray-500 self-center hover:text-sky-400"
              >
                要写图？去 FDE⑦ 导入表/CSV →
              </Link>
            </div>
          </>
        ) : (
          <>
            <textarea
              className="w-full min-h-[100px] bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-[11px] font-mono text-gray-300"
              value={snippet}
              onChange={(e) => setSnippet(e.target.value)}
              placeholder="粘贴 Python/SQL/ER 片段，或写：表 Orders / class Foo"
            />
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" size="sm" loading={loading} onClick={() => runCodeSuggest(false)}>
                仅扫描建议
              </Button>
              <Button variant="default" size="sm" loading={loading} onClick={() => runCodeSuggest(true)}>
                入队提案草稿
              </Button>
            </div>
          </>
        )}
        {last && (
          <div className="text-[11px] text-gray-400 space-y-1 rounded border border-gray-700/50 p-2 bg-gray-900/40">
            <div>
              建议类={(last.suggestions || []).map((s: any) => s.name || s.label).join(', ') || '—'}
              {(last.suggestions || [])[0]?.required_fields
                ? ` · 字段=${((last.suggestions || [])[0].required_fields || []).join(',')}`
                : ''}
              {last.proposal_id ? ` · proposal=${last.proposal_id}` : ''}
            </div>
            <div className="text-[10px] text-gray-500">
              auto_apply={String(last.auto_apply ?? false)}
              {' · '}writes_graph={String(last.writes_graph ?? false)}
            </div>
            {(last.suggestions || [])[0]?.field_meanings && (
              <div className="text-[10px] text-violet-300/90">
                AI补齐(启发式): {Object.entries((last.suggestions || [])[0].field_meanings)
                  .slice(0, 6)
                  .map(([k, v]) => `${k}→${v}`)
                  .join(' · ')}
              </div>
            )}
            {last.authority_note && (
              <div className="text-[10px] text-amber-500/80">{last.authority_note}</div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ③ OntologyEvolutionPanel — 版本化本体治理
// ═══════════════════════════════════════════════════════════
type ProposalView = {
  title: string;
  subtitle: string;
  fields: string;
  source: string;
  risk: string;
  note: string;
};

const parseJsonish = (raw: any): any => {
  if (raw == null) return {};
  if (typeof raw === 'object') return raw;
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw || '{}');
    } catch {
      return {};
    }
  }
  return {};
};

const describeProposal = (p: any): ProposalView => {
  const ch = parseJsonish(p.changes);
  const impact = parseJsonish(p.impact_analysis);
  const cls = ch?.add?.class || {};
  const name = String(cls.name || cls.label || '未命名类');
  const sampleLabel = String(cls.label || '').trim();
  const fields = Array.isArray(cls.required_fields) ? cls.required_fields.filter(Boolean) : [];
  const fieldText = fields.length ? fields.slice(0, 6).join('、') : '名称';
  const promo = Array.isArray(impact.promotions) ? impact.promotions[0] : null;
  let note = '写入后，说明书里会多一个（或更新一个）业务类别。';
  if (promo?.class || (cls.name && promo)) {
    note = `说明书里已有「${promo?.class || name}」，这次是更新它的定义。`;
  } else if (cls.name) {
    note = `建议在说明书中增加「${name}」。`;
  }
  const author = String(p.author || '');
  let source = '未知来源';
  if (author.startsWith('extract:')) source = '来自上方文档确认';
  else if (author.includes('schema')) source = '来自表头/CSV';
  else if (author.includes('factory') || author.includes('code')) source = '来自代码建议';
  else if (author) source = `来源 ${author}`;

  const displayName =
    sampleLabel && sampleLabel !== name && !promo
      ? `${name}（例：${sampleLabel}）`
      : name;

  const title =
    p.status === 'applied'
      ? `已写入：${displayName}`
      : p.status === 'approved'
        ? `待写入：${displayName}`
        : `建议写入：${displayName}`;

  return {
    title,
    subtitle: fields.length ? `关注字段：${fieldText}` : '',
    fields: fieldText,
    source,
    risk: '',
    note,
  };
};

const OntologyEvolutionPanel: React.FC<{
  domainId: DomainId;
  highlightId?: string;
}> = ({ domainId, highlightId }) => {
  const [proposals, setProposals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastReceipt, setLastReceipt] = useState<any>(null);
  const [showHistory, setShowHistory] = useState(false);

  const reload = useCallback(() => {
    const did = encodeURIComponent(domainId || DEFAULT_DOMAIN);
    fetch(API(`/ontology/proposals?domain_id=${did}`))
      .then(r => r.json()).then(d => setProposals(d.proposals || []))
      .catch(() => {});
  }, [domainId]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const onEnq = () => reload();
    window.addEventListener('factory-proposal-enqueued', onEnq);
    return () => window.removeEventListener('factory-proposal-enqueued', onEnq);
  }, [reload]);

  useEffect(() => {
    if (!highlightId) return;
    const el = document.getElementById(`proposal-${highlightId}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [highlightId, proposals]);

  const handleApprove = async (id: string, label: string) => {
    setLoading(true);
    try {
      const r = await fetch(API(`/ontology/proposals/${id}/approve`), {
        method: 'POST',
        headers: factoryRoleHeaders(),
        body: JSON.stringify({}),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.reason || (typeof d.detail === 'string' ? d.detail : '') || '审批失败');
      setProposals(prev => prev.map(p => p.proposal_id === id ? { ...p, status: 'approved' } : p));
      toast?.success?.(`已批准「${label}」，下一步点「应用」才会写入说明书`);
    } catch (e: any) {
      toast?.error?.(e?.message || '审批失败');
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async (id: string, label: string) => {
    setLoading(true);
    try {
      const r = await fetch(API(`/ontology/proposals/${id}/apply`), { method: 'POST' });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.reason || (typeof d.detail === 'string' ? d.detail : '') || '应用失败');
      setProposals(prev => prev.map(p => p.proposal_id === id ? { ...p, status: 'applied' } : p));
      const added = (d.classes_added || []).join('、') || label;
      setLastReceipt({
        proposal_id: id,
        ok: d.ok !== false,
        version_from: d.version_from,
        version_to: d.version_to,
        classes_added: d.classes_added || [],
        live_path: d.live_path,
        rollback_snapshot: d.rollback_snapshot,
        at: new Date().toISOString(),
        label: added,
      });
      toast?.success?.(`已写入说明书：${added}`);
    } catch (e: any) {
      toast?.error?.(e?.message || '应用失败');
    } finally {
      setLoading(false);
    }
  };

  const statusLabel = (s: string) => {
    const m: Record<string, string> = {
      draft: '待同意', submitted: '已提交', approved: '待写入',
      applied: '已写入', rejected: '已忽略',
    };
    return m[s] || s;
  };

  const statusColorClass = (s: string) => {
    const m: Record<string, string> = {
      approved: 'bg-amber-500/20 text-amber-300',
      submitted: 'bg-yellow-500/20 text-yellow-400',
      applied: 'bg-emerald-500/20 text-emerald-400',
      draft: 'bg-sky-500/20 text-sky-300',
      rejected: 'bg-red-500/20 text-red-400',
    };
    return m[s] || 'bg-gray-500/20 text-gray-400';
  };

  // 待处理：同类只留一条（优先「待写入」，再留最新草稿），避免刷屏
  const rank = (s: string) => (s === 'approved' ? 3 : s === 'submitted' ? 2 : s === 'draft' ? 1 : 0);
  const dedupedActionable: any[] = [];
  const seenClass = new Set<string>();
  const sortedAct = [...proposals]
    .filter((p) => p.status === 'draft' || p.status === 'approved' || p.status === 'submitted')
    .sort((a, b) => rank(b.status) - rank(a.status) || String(b.proposal_id).localeCompare(String(a.proposal_id)));
  for (const p of sortedAct) {
    const ch = parseJsonish(p.changes);
    const key = String(ch?.add?.class?.name || ch?.add?.class?.label || p.proposal_id);
    if (seenClass.has(key)) continue;
    seenClass.add(key);
    dedupedActionable.push(p);
  }
  const hiddenDup = sortedAct.length - dedupedActionable.length;
  const actionable = dedupedActionable;
  const history = proposals.filter((p) => p.status === 'applied' || p.status === 'rejected');
  const visible = showHistory ? [...actionable, ...history] : actionable.length ? actionable : [];

  const renderCard = (p: any) => {
    const view = describeProposal(p);
    const label = view.title.replace(/^[^：:]+[：:]/, '') || '该类';
    return (
      <div
        key={p.proposal_id}
        id={`proposal-${p.proposal_id}`}
        className={`p-3 rounded-lg border ${
          highlightId && p.proposal_id === highlightId
            ? 'bg-sky-950/40 border-sky-600'
            : 'bg-gray-800/50 border-gray-700/30'
        }`}
      >
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <div className="min-w-0">
            <div className="text-sm text-gray-100 font-medium leading-snug">{view.title}</div>
            {view.subtitle ? (
              <div className="text-[11px] text-gray-400 mt-0.5">{view.subtitle}</div>
            ) : null}
            <div className="text-[11px] text-gray-500 mt-1 leading-relaxed">
              {view.note}
              {view.source ? ` · ${view.source}` : ''}
            </div>
          </div>
          <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${statusColorClass(p.status)}`}>
            {statusLabel(p.status)}
          </span>
        </div>
        <details className="mt-1 text-[10px] text-gray-600">
          <summary className="cursor-pointer select-none hover:text-gray-400">编号（可忽略）</summary>
          <div className="mt-1 font-mono break-all">{p.proposal_id}</div>
        </details>
        <div className="flex gap-2 mt-2">
          {p.status === 'draft' && (
            <Button
              variant="default"
              size="sm"
              className="text-[11px] h-7"
              loading={loading}
              onClick={() => handleApprove(p.proposal_id, label)}
            >
              同意
            </Button>
          )}
          {p.status === 'approved' && (
            <Button
              variant="default"
              size="sm"
              className="text-[11px] h-7"
              loading={loading}
              onClick={() => handleApply(p.proposal_id, label)}
            >
              写入说明书
            </Button>
          )}
        </div>
      </div>
    );
  };

  return (
    <Card id="factory-proposals" className="border-green-500/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-green-500/10 text-green-400">
            <GitBranch className="w-5 h-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div>
              <span className="text-sm font-semibold text-gray-100">② 写入说明书</span>
              <span className="text-[11px] text-gray-500 ml-2">{domainId}</span>
            </div>
            <p className="text-[11px] text-gray-500 mt-0.5 leading-relaxed max-w-xl">
              改的是<strong className="text-gray-400 font-medium">类定义（说明书）</strong>，
              不是知识图里的工单连线。日常可跳过；只有要增删类时才「同意 → 写入说明书」。
            </p>
          </div>
          {actionable.filter((p) => p.status === 'approved').length > 0 && (
            <span className="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded shrink-0">
              {actionable.filter((p) => p.status === 'approved').length} 条待写入
            </span>
          )}
          <Button variant="ghost" size="sm" onClick={reload} className="shrink-0">
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {lastReceipt && (
          <div className="mb-3 rounded border border-emerald-700/50 bg-emerald-950/30 p-2.5 text-[12px] text-emerald-100/90 space-y-0.5">
            <div className="font-medium text-emerald-300">刚才已写入说明书</div>
            <div>类：{(lastReceipt.classes_added || []).join('、') || lastReceipt.label || '—'}</div>
            <div className="text-[10px] text-emerald-200/60">
              说明书版本 v{lastReceipt.version_from ?? '?'} → v{lastReceipt.version_to ?? '?'}
            </div>
          </div>
        )}
        {hiddenDup > 0 && (
          <div className="mb-2 text-[11px] text-amber-200/80 leading-relaxed">
            已自动合并 {hiddenDup} 条同类重复草稿，只显示每类最新一条。
          </div>
        )}
        {proposals.length === 0 ? (
          <div className="text-xs text-gray-600 text-center py-4">
            暂无待写入项 — 请先在上方分析文档并点「确认」
          </div>
        ) : visible.length === 0 ? (
          <div className="text-xs text-gray-600 text-center py-4">
            没有待处理项
            {history.length > 0 && (
              <button
                type="button"
                className="ml-2 text-sky-400 hover:underline"
                onClick={() => setShowHistory(true)}
              >
                查看 {history.length} 条历史
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-2.5">
            {actionable.length > 0 && !showHistory && (
              <div className="text-[10px] text-gray-500">待你处理（{actionable.length}）</div>
            )}
            {visible.map(renderCard)}
            {history.length > 0 && (
              <button
                type="button"
                className="text-[11px] text-gray-500 hover:text-gray-300"
                onClick={() => setShowHistory((v) => !v)}
              >
                {showHistory ? '只看待处理' : `显示已写入（${history.length}）`}
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// KnowledgeFactoryPage — 主页面
// ═══════════════════════════════════════════════════════════
const KnowledgeFactoryPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const domainId = (params.get('domain') || DEFAULT_DOMAIN).trim() || DEFAULT_DOMAIN;
  const highlightId = (params.get('proposal') || '').trim();
  const focus = (params.get('focus') || '').trim();
  const [domainOptions, setDomainOptions] = useState<DomainOption[]>([]);
  const [domainFilter, setDomainFilter] = useState<DomainFilter>('preferred');

  const setDomain = (did: string) => {
    const next = new URLSearchParams(params);
    next.set('domain', did);
    next.delete('proposal');
    setParams(next, { replace: true });
  };

  useEffect(() => {
    fetch(WIKI_DOMAINS_API)
      .then((r) => r.json())
      .then((d) => {
        const rows: DomainOption[] = (d.domains || []).map((x: any) => ({
          id: String(x.id || ''),
          label: String(x.name || x.id || ''),
          classCount: typeof x.class_count === 'number' ? x.class_count : undefined,
          description: x.description ? String(x.description) : undefined,
        })).filter((x: DomainOption) => x.id);
        const rank = (id: string) => {
          const i = PREFERRED_DOMAIN_ORDER.indexOf(id);
          return i >= 0 ? i : PREFERRED_DOMAIN_ORDER.length + 1;
        };
        rows.sort((a, b) => rank(a.id) - rank(b.id) || a.label.localeCompare(b.label, 'zh'));
        setDomainOptions(rows);
      })
      .catch(() => setDomainOptions([]));
  }, []);

  useEffect(() => {
    if (focus === 'code' || focus === 'schema') {
      document.getElementById('factory-code-suggest')?.scrollIntoView({ behavior: 'smooth' });
    } else if (highlightId) {
      document.getElementById('factory-proposals')?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [focus, highlightId]);

  // 当前选中域若不在筛选组内，仍保留可见
  const filteredOptions = domainOptions.filter(
    (d) => domainFilter === 'all' || domainGroup(d.id) === domainFilter || d.id === domainId,
  );
  const selectOptions = filteredOptions.length
    ? filteredOptions
    : domainOptions.length
      ? domainOptions
      : [{ id: domainId, label: domainId }];

  const currentMeta = domainOptions.find((d) => d.id === domainId);

  const countIn = (id: DomainFilter) =>
    id === 'all'
      ? domainOptions.length
      : domainOptions.filter((d) => domainGroup(d.id) === id).length;

  return (
    <div className="p-6 space-y-5 max-w-4xl">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">从文档生成</h1>
          <p className="text-sm text-gray-400 mt-1 leading-relaxed">
            看下方橙色「你现在只需做这一步」。确认写知识图；写入说明书只改类定义。
          </p>
        </div>

      {/* 域选择：分组筛选 + 短列表 */}
      <div className="rounded-lg border border-gray-700/50 bg-gray-900/40 px-4 py-3 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="text-[12px] text-gray-300 font-medium">写到哪个业务域</div>
          <span className="text-[11px] text-gray-500">
            注册表共 {domainOptions.length || '…'} 个 · 当前筛选 {selectOptions.length} 个
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTER_CHIPS.map((f) => {
            const n = domainOptions.length ? countIn(f.id) : 0;
            const active = domainFilter === f.id;
            return (
              <button
                key={f.id}
                type="button"
                title={f.hint}
                onClick={() => setDomainFilter(f.id)}
                className={`px-2.5 py-1 rounded text-[11px] border transition-colors ${
                  active
                    ? 'bg-sky-600/30 border-sky-500/50 text-sky-100'
                    : 'bg-gray-900/60 border-gray-700/60 text-gray-400 hover:text-gray-200'
                }`}
              >
                {f.label}
                {domainOptions.length > 0 && (
                  <span className="ml-1 opacity-70">{n}</span>
                )}
              </button>
            );
          })}
        </div>
        <select
          className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200"
          value={selectOptions.some((d) => d.id === domainId) ? domainId : (selectOptions[0]?.id || domainId)}
          onChange={(e) => setDomain(e.target.value)}
          title="与「手动画类」同一注册表"
        >
          {selectOptions.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}（{d.id}）
              {typeof d.classCount === 'number' ? ` · ${d.classCount} 类` : ''}
            </option>
          ))}
        </select>
        <p className="text-[11px] text-gray-500 leading-relaxed">
          默认只看「常用交付」。Bell / 平台域是种子样例，日常交付不必翻。
          {currentMeta?.description ? (
            <> 当前域简介：{currentMeta.description.slice(0, 80)}{currentMeta.description.length > 80 ? '…' : ''}</>
          ) : null}
        </p>
      </div>

      <ExistingDomainBanner domainId={domainId} fallbackLabel={currentMeta?.label} />

      <BusinessOntologyGuide domainId={domainId} mode="factory" />

      <KnowledgeExtractionPanel domainId={domainId} />
      <OntologyEvolutionPanel domainId={domainId} highlightId={highlightId || undefined} />

      <details
        className="rounded-lg border border-gray-700/50 bg-gray-900/30"
        open={focus === 'code' || focus === 'schema'}
      >
        <summary className="cursor-pointer select-none px-4 py-3 text-sm text-gray-400 hover:text-gray-200">
          更多（一般不用）· 表头生成 / 跨域对齐 / 对照仪表
        </summary>
        <div className="px-3 pb-4 space-y-4 border-t border-gray-800/80 pt-3">
          <CodeSuggestionPanel
            domainId={domainId}
            onEnqueued={(pid) => {
              const next = new URLSearchParams(params);
              next.set('proposal', pid);
              next.delete('focus');
              setParams(next, { replace: true });
            }}
          />
          <CrossDomainResolutionPanel />
          <details className="rounded border border-gray-800/80">
            <summary className="cursor-pointer px-3 py-2 text-[12px] text-gray-500 hover:text-gray-300">
              对照材料仪表（可跳过）
            </summary>
            <div className="px-2 pb-3 space-y-3">
              <GovernanceLoopPanel />
              <OrgL5Panel />
            </div>
          </details>
        </div>
      </details>

      <div className="flex flex-wrap gap-3 text-[12px] text-gray-500 pt-1">
        <Link
          to={`/knowledge/business?tab=domains&domain=${encodeURIComponent(domainId)}`}
          className="hover:text-sky-400"
        >
          手动画类（查看 {domainId}）
        </Link>
        <span>·</span>
        <Link to="/diagnostics/fde" className="hover:text-sky-400">去 FDE 写实例数据</Link>
        <span>·</span>
        <Link to="/knowledge/library?tab=vault" className="hover:text-sky-400">知识库资料</Link>
      </div>
    </div>
  );
};

export default KnowledgeFactoryPage;
