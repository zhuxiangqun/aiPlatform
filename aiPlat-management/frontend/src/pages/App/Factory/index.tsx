import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Send, Loader2, Clock, CheckCircle, XCircle, ExternalLink, BarChart3, Trash2, Play, RefreshCw, FileText, Wrench } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { projectApi, builderTeamApi, workspaceAgentApi, type ProjectItem, type ProjectRun } from '../../../services';
import { reportPageData, clearPageData } from '../../../lib/pageDataBridge';
import { Card, CardContent, Button, Textarea, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';
import type { BuilderSession } from '../../../services';

// ── Simple inline chat (replaces crashing ChatWidget) ──
const InlineChat: React.FC<{
  projectId: string;
  initialMessage?: string;
  onPhaseChange?: (phase: string) => void;
  agentMode?: boolean;
  agentName?: string;
}> = ({ projectId, initialMessage, onPhaseChange, agentMode, agentName }) => {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [autoSent, setAutoSent] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  // Load existing messages from backend on mount
  useEffect(() => {
    (async () => {
      try {
        const resp = await projectApi.getMessages(projectId);
        const msgs = (resp as any)?.messages || [];
        if (msgs.length > 0) {
          setMessages(msgs);
          setAutoSent(true); // Prevent auto-send when history exists
        }
      } catch { /* ignore, will auto-send */ }
      setLoaded(true);
    })();
  }, [projectId]);

  const send = useCallback(async (msg: string) => {
    if (!msg.trim()) return;
    setSending(true);
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    try {
      const resp = await projectApi.chat(projectId, msg);
      setMessages(prev => [...prev, { role: 'assistant', content: resp.reply || '(no response)' }]);
      if (resp.prd_ready && onPhaseChange) onPhaseChange('prd_ready');
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '发送失败，请重试' }]);
    } finally { setSending(false); }
  }, [projectId, onPhaseChange]);

  // Auto-send initial message — only when no existing history
  useEffect(() => {
    if (loaded && initialMessage && !autoSent && messages.length === 0) {
      setAutoSent(true);
      send(initialMessage);
    }
  }, [loaded, initialMessage, autoSent, messages.length, send]);

  // Scroll chat to bottom on new messages — deferred to rAF + direct scrollTop
  // (smooth scrollIntoView right after commit forces a synchronous reflow).
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const prevMsgLenRef = useRef(messages.length);
  useEffect(() => {
    const prevLen = prevMsgLenRef.current;
    prevMsgLenRef.current = messages.length;
    if (messages.length <= prevLen) return;
    const raf = requestAnimationFrame(() => {
      const el = scrollContainerRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(raf);
  }, [messages.length]);

  const handleSend = () => { const m = input.trim(); if (m) { setInput(''); send(m); } };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[200px] max-h-[400px]">
        {messages.map((m, i) => (
          <div key={i} className={`p-2 rounded text-sm ${m.role === 'assistant' ? 'bg-primary/10 border border-primary/20 text-gray-200' : 'bg-dark-card border border-dark-border text-gray-300'}`}>
             <div className="text-[10px] text-gray-500 mb-1">{m.role === 'assistant' ? (agentMode ? agentName : 'AI PM') : '你'}</div>
            <div className="whitespace-pre-wrap break-words max-h-[200px] overflow-y-auto">{m.content}</div>
          </div>
        ))}
        {sending && <div className="flex items-center gap-2 text-xs text-gray-500"><Loader2 className="w-3 h-3 animate-spin" />思考中...</div>}
        <div ref={bottomRef} />
      </div>
      <div className="p-2 border-t border-dark-border flex gap-2">
        <Textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }} placeholder={agentMode ? `使用 ${agentName}...` : '输入需求...'} rows={2} className="flex-1 text-xs" />
        <Button variant="primary" onClick={handleSend} loading={sending} icon={<Send className="w-3 h-3" />} />
      </div>
    </div>
  );
};

// ── Document schemas (shared with backend YAML) ──
type ColDef = { key: string; label: string; width?: string; type?: string };
type TableDef = { key: string; title: string; columns: ColDef[] };
type SectionDef = { key: string; title: string; type?: string };
type ListDef = { key: string; title: string };
type StatDef = { key: string; label: string; color?: string; format?: string };
type DocSchema = {
  title_field?: string; overview_field?: string; scope_badge?: string; title?: string;
  tables?: TableDef[]; sections?: SectionDef[]; lists?: ListDef[]; stat_blocks?: StatDef[];
};

const SCHEMAS: Record<string, DocSchema> = {
  prd: {
    title_field: "title", overview_field: "description",
    tables: [
      { key: "functional_requirements", title: "功能需求", columns: [
        { key: "id", label: "ID", width: "100px" },
        { key: "name", label: "名称", width: "160px" },
        { key: "description", label: "描述" },
        { key: "priority", label: "优先级", type: "badge" },
        { key: "acceptance_criteria", label: "验收标准", type: "ac_list" },
      ]},
      { key: "user_stories", title: "用户故事", columns: [
        { key: "id", label: "ID", width: "100px" },
        { key: "story", label: "描述" },
        { key: "priority", label: "优先级", type: "badge" },
        { key: "related_fr", label: "关联FR" },
      ]},
    ],
    lists: [{ key: "constraints", title: "技术约束" }],
  },
  architecture: {
    title_field: "title", overview_field: "overview",
    tables: [
      { key: "components", title: "组件清单", columns: [
        { key: "name", label: "组件名" }, { key: "layer", label: "层级", type: "badge" },
        { key: "tech", label: "技术栈" }, { key: "responsibility", label: "职责", width: "300px" },
      ]},
      { key: "api_design", title: "API 设计", columns: [
        { key: "method", label: "方法", type: "method_badge" }, { key: "path", label: "路径" },
        { key: "description", label: "说明" },
      ]},
    ],
    sections: [
      { key: "database_schema", title: "数据库设计", type: "code" }, { key: "deployment", title: "部署方案" },
      { key: "security", title: "安全设计" }, { key: "performance", title: "性能优化" },
    ],
  },
  test: {
    title: "测试报告",
    tables: [{ key: "test_cases", title: "测试用例", columns: [
      { key: "id", label: "ID", width: "120px" }, { key: "user_story", label: "User Story" },
      { key: "description", label: "描述" }, { key: "risk_level", label: "风险", type: "risk" },
      { key: "test_type", label: "类型" },
    ]}],
    sections: [{ key: "test_log", title: "执行日志", type: "code" }],
  },
  qa: {
    title: "Agent 对话测试",
    tables: [{ key: "test_questions", title: "对话测试用例", columns: [
      { key: "id", label: "ID", width: "90px" },
      { key: "ac_ref", label: "验收标准", width: "110px" },
      { key: "category", label: "分类", type: "category" },
      { key: "question", label: "测试问题" },
      { key: "min_expectation", label: "最低期望" },
    ]}],
  },
  frontend: {
    title_field: "app_title", overview_field: "app_name",
    tables: [{ key: "stages", title: "页面阶段", columns: [
      { key: "id", label: "ID", width: "120px" },
      { key: "title", label: "标题" },
      { key: "skill", label: "Skill" },
      { key: "component", label: "组件", type: "badge" },
    ]}],
    lists: [
      { key: "auth_required_stages", title: "需认证的阶段" },
    ],
  },
  test_report: {
    title: "测试报告",
    title_field: "header.project",
    overview_field: "recommendation",
    scope_badge: "meta.pass_rate",
    tables: [
      { key: "test_results", title: "测试结果", columns: [
        { key: "id", label: "ID", width: "80px" },
        { key: "ac_ref", label: "FR", width: "70px" },
        { key: "category", label: "类型", type: "category" },
        { key: "question", label: "测试问题" },
        { key: "min_expectation", label: "预期", width: "180px" },
        { key: "result", label: "结果", type: "test_result_badge" },
        { key: "is_bug", label: "Bug?", type: "bug_badge" },
        { key: "score", label: "评分", width: "50px" },
        { key: "reason", label: "理由", width: "220px" },
      ]},
      { key: "bug_summary.bugs", title: "Bug 清单", columns: [
        { key: "id", label: "ID", width: "90px" },
        { key: "severity", label: "严重度", type: "badge" },
        { key: "title", label: "标题" },
        { key: "FR", label: "关联FR", width: "70px" },
        { key: "suggested_fix", label: "修复建议", width: "250px" },
      ]},
      { key: "quality_analysis.functional_coverage.by_fr", title: "功能覆盖率", columns: [
        { key: "fr", label: "FR", width: "80px" },
        { key: "ac_total", label: "AC总数", width: "60px" },
        { key: "ac_covered", label: "已覆盖", width: "60px" },
        { key: "coverage_pct", label: "覆盖率", width: "70px" },
      ]},
    ],
    sections: [
      { key: "quality_analysis.functional_coverage.overview", title: "覆盖总览", type: "text" },
      { key: "quality_analysis.case_quality.assessment", title: "用例质量评估", type: "text" },
    ],
    lists: [
      { key: "quality_analysis.risk_assessment.high_risk", title: "🔴 高风险" },
      { key: "quality_analysis.risk_assessment.medium_risk", title: "🟡 中风险" },
      { key: "quality_analysis.risk_assessment.low_risk", title: "🟢 低风险" },
      { key: "improvements", title: "改进建议" },
    ],
    stat_blocks: [
      { key: "meta.passed", label: "通过" },
      { key: "meta.failed", label: "失败" },
      { key: "meta.warnings", label: "警告" },
      { key: "bug_summary.total_bugs", label: "Bug" },
    ],
  },
};

const formatBadge = (v: string, type: string) => {
  if (type === 'risk' || type === 'badge' || type === 'priority') {
    const low = (v || '').toLowerCase();
    const color = low === 'high' ? 'bg-red-500/20 text-red-300' : low === 'medium' ? 'bg-amber-500/20 text-amber-300' : low === 'standard' ? 'bg-blue-500/20 text-blue-300' : 'bg-dark-hover text-gray-400';
    return <span className={`px-1.5 py-0.5 rounded text-[10px] ${color}`}>{v}</span>;
  }
  if (type === 'category') {
    const colors: Record<string,string> = { happy_path:'bg-green-500/20 text-green-300', exception:'bg-red-500/20 text-red-300', boundary:'bg-amber-500/20 text-amber-300' };
    const labels: Record<string,string> = { happy_path:'正常流程', exception:'异常流程', boundary:'边界测试' };
    return <span className={`px-1.5 py-0.5 rounded text-[10px] ${colors[v]||'bg-dark-hover text-gray-400'}`}>{labels[v]||v}</span>;
  }
  if (type === 'bug_badge') {
    return v ? <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-500/20 text-red-300">🐛 Bug</span>
             : <span className="px-1.5 py-0.5 rounded text-[10px] text-gray-500">—</span>;
  }
  if (type === 'test_result_badge') {
    const colors: Record<string,string> = { PASS:'bg-green-500/20 text-green-300', FAIL:'bg-red-500/20 text-red-300', WARNING:'bg-amber-500/20 text-amber-300' };
    return <span className={`px-1.5 py-0.5 rounded text-[10px] ${colors[v]||'bg-dark-hover text-gray-400'}`}>{v}</span>;
  }
  if (type === 'method_badge') {
    const colors: Record<string,string>={GET:'bg-blue-500/20 text-blue-300',POST:'bg-green-500/20 text-green-300',PUT:'bg-amber-500/20 text-amber-300',DELETE:'bg-red-500/20 text-red-300'};
    return <span className={`px-1 rounded text-[10px] font-mono ${colors[v]||'bg-dark-hover text-gray-400'}`}>{v}</span>;
  }
  if (type === 'ac_list' && Array.isArray(v)) return <>{v.map((a:string,i:number)=><div key={i} className="text-[11px] text-gray-400">· {a}</div>)}</>;
  if (type === 'code') return <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap">{v}</pre>;
  return <>{v}</>;
};

// ── Generic DataDocument — schema-driven renderer ──
const DataDocument: React.FC<{ data: Record<string, unknown>; schema: DocSchema }> = ({ data, schema }) => {
  const _get = (obj: any, path: string): any => {
    if (!path.includes('.')) return obj?.[path];
    return path.split('.').reduce((o, k) => (o != null ? o[k] : undefined), obj);
  };
  const title = (schema.title_field ? _get(data, schema.title_field) : schema.title) as string || '';
  const recLabels: Record<string, string> = { CONDITIONAL_APPROVAL: '有条件通过', APPROVED: '已通过', REJECTED: '已拒绝' };
  const overview = (() => {
    const raw = schema.overview_field ? (_get(data, schema.overview_field) as string) : '';
    if (schema.overview_field === 'recommendation') {
      return recLabels[raw] || raw;
    }
    return raw;
  })();
  const scope = schema.scope_badge ? (_get(data, schema.scope_badge) as any) : '';
  const scopeLabel = schema.scope_badge === 'meta.pass_rate' ? `通过率 ${scope}%` : (typeof scope === 'number' ? `${scope}%` : scope);
  return (
    <div className="space-y-5 text-sm text-gray-200">
      {title && <div><h1 className="text-xl font-bold text-gray-100 mb-1">{title}</h1>{scope != null && scope !== '' && <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-300">{scopeLabel}</span>}</div>}
      {overview && <p className="text-gray-400 leading-relaxed">{overview}</p>}
      {(schema.tables || []).map((t: TableDef) => {
        const rows = (_get(data, t.key) || []) as any[];
        if (!rows.length) return null;
        return <div key={t.key}><h2 className="text-base font-semibold text-gray-100 mb-2 border-b border-dark-border pb-1">{t.title} ({rows.length})</h2>
          <table className="w-full text-xs border-collapse"><thead><tr className="bg-dark-hover">{t.columns.map((c: ColDef) => (<th key={c.key} className="p-2 text-left border border-dark-border" style={{width:c.width}}>{c.label}</th>))}</tr></thead>
          <tbody>{rows.map((r: any, i: number) => (<tr key={i} className="border border-dark-border">{t.columns.map((c: ColDef) => (<td key={c.key} className="p-2 border border-dark-border">{c.type ? formatBadge(r[c.key], c.type) : <>{r[c.key]?.toString()||''}</>}</td>))}</tr>))}</tbody></table></div>;
      })}
      {(schema.lists || []).map((l: ListDef) => {
        const items = (_get(data, l.key) || []) as any[];
        if (!items.length) return null;
        const priorities: Record<string,string> = { MUST_FIX:'text-red-400', SHOULD_FIX:'text-amber-400', NICE_TO_HAVE:'text-blue-400' };
        return <div key={l.key}><h2 className="text-base font-semibold text-gray-100 mb-2 border-b border-dark-border pb-1">{l.title}</h2><ul className="list-disc pl-5 space-y-0.5 text-gray-400 text-xs">{items.map((c:any,i:number)=><li key={i}>{typeof c==='string' ? c : c.item ? <><span className={priorities[c.priority]||''}>[{c.priority}]</span> {c.item} {c.ref ? <span className="text-gray-600">({c.ref})</span> : ''}</> : String(c)}</li>)}</ul></div>;
      })}
      {(schema.sections || []).map((s: SectionDef) => {
        const v = _get(data, s.key);
        if (!v) return null;
        return <div key={s.key}><h2 className="text-base font-semibold text-gray-100 mb-2 border-b border-dark-border pb-1">{s.title}</h2>{s.type === 'code' ? <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap">{v as string}</pre> : <div className="text-gray-400 text-xs">{v as string}</div>}</div>;
      })}
      {(schema.stat_blocks || []).length > 0 && (
        <div className="flex gap-3 flex-wrap">
          {schema.stat_blocks.map((sb: any) => {
            const val = _get(data, sb.key);
            return val != null ? (
              <div key={sb.key} className="px-3 py-1.5 rounded bg-dark-hover text-xs">
                <span className="text-gray-500">{sb.label}: </span>
                <span className="text-gray-200 font-medium">{String(val)}</span>
              </div>
            ) : null;
          })}
        </div>
      )}
    </div>
  );
};

// ── Fullscreen content viewer (schema-driven) ──
const FullscreenView: React.FC<{
  open: boolean; title: string; content: string; onClose: () => void
}> = ({ open, title, content, onClose }) => {
  if (!open) return null;
  let parsed: any = null; let schema: DocSchema | undefined;
  try {
    parsed = JSON.parse(content);
  } catch {
    const jStart = content.indexOf('{');
    const jEnd = content.lastIndexOf('}');
    if (jStart >= 0 && jEnd > jStart) {
      try { parsed = JSON.parse(content.slice(jStart, jEnd + 1)); } catch {}
    }
  }
  if (parsed) {
    // Normalize simplified PRD format (string arrays → objects)
    if (parsed.functional_requirements?.length > 0 && typeof parsed.functional_requirements[0] === 'string') {
      parsed.functional_requirements = parsed.functional_requirements.map((s: string, i: number) => ({
        id: `FR-${String(i+1).padStart(3,'0')}`, name: s, description: '', priority: '', acceptance_criteria: [],
      }));
    }
    if (parsed.user_stories?.length > 0 && typeof parsed.user_stories[0] === 'string') {
      parsed.user_stories = parsed.user_stories.map((s: string, i: number) => ({
        id: `US-${String(i+1).padStart(3,'0')}`, story: s, priority: '', related_fr: '',
      }));
    }
    // Normalize QA test_questions (string arrays → objects)
    if (parsed.test_questions?.length > 0 && typeof parsed.test_questions[0] === 'string') {
      parsed.test_questions = parsed.test_questions.map((s: string, i: number) => ({
        id: `AQ-${String(i+1).padStart(3,'0')}`, ac_ref: '', category: '', question: s, min_expectation: '',
      }));
    }
    if (parsed.user_stories) schema = SCHEMAS.prd;
    else if (parsed.components) schema = SCHEMAS.architecture;
    else if (parsed.test_questions) schema = SCHEMAS.qa;
    else if (parsed.test_results || (parsed.header?.report_id)) schema = SCHEMAS.test_report;
    else if (parsed.test_cases) schema = SCHEMAS.test;
    else if (parsed.stages || parsed.app_name) schema = SCHEMAS.frontend;  // app_page.json format
  }
  return (
    <div className="fixed inset-0 bg-black/80 z-[60] flex flex-col" onClick={onClose}>
      <div className="flex items-center justify-between p-3 border-b border-dark-border bg-dark-card flex-shrink-0" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-gray-200">{title}</h3>
        <button onClick={onClose} className="p-1.5 rounded hover:bg-dark-hover text-gray-400 hover:text-gray-200 transition-colors text-lg">✕</button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 bg-dark-card max-w-4xl mx-auto w-full" onClick={e => e.stopPropagation()}>
        {schema && parsed ? <DataDocument data={parsed} schema={schema} /> :
         content.includes('## FILE:') ? (
          <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap break-all">{content}</pre>
        ) : parsed ? (
          <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap break-all">{JSON.stringify(parsed, null, 2)}</pre>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-invert max-w-none text-gray-200">
            {content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
};

// ── Project detail panel ──
const ProjectPanel: React.FC<{
  project: ProjectItem;
  onClose: () => void;
  onRefresh: () => void;
}> = ({ project, onClose, onRefresh }) => {
  const [phase, setPhase] = useState(
    ((project as any).confirmed_prd || (project.runs?.length > 0)) ? 'team_ready' : 'dialogue');
  const [prdReady, setPrdReady] = useState(
    !!(project as any).confirmed_prd || (project as any).runs?.length > 0);
  const [starting, setStarting] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [recommending, setRecommending] = useState(false);
  const [teamStages, setTeamStages] = useState<Array<{ agent_name?: string; agent_id?: string; phase?: string; id?: string }>>(project.team_stages || []);
  const [recommendedMode, setRecommendedMode] = useState<string>('');
  const [recommendedReason, setRecommendedReason] = useState<string>('');
  const [runHistory, setRunHistory] = useState<ProjectRun[]>(project.runs || []);
  const [deployUrl, setDeployUrl] = useState('');
  const [deploying, setDeploying] = useState(false);
  const [deployChecked, setDeployChecked] = useState(false);
  const [fixingBugs, setFixingBugs] = useState(false);
  const [hitlStageId, setHitlStageId] = useState<string | null>(null);
  const [hitlOutputArtifact, setHitlOutputArtifact] = useState<string | null>(null);
  const [healthReport, setHealthReport] = useState<Record<string, any> | null>(null);
  const [progressState, setProgressState] = useState<Record<string, any> | null>(null);
  const [executingSince, setExecutingSince] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [agentMode, setAgentMode] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [stageOutputs, setStageOutputs] = useState<Record<string, any> | null>(null);
  const [confirmedPrd, setConfirmedPrd] = useState<Record<string, unknown> | null>(
    (project as any).confirmed_prd || null);
  const [showPrdDetail, setShowPrdDetail] = useState(false);
  const [prdEditText, setPrdEditText] = useState('');
  const [savingPrd, setSavingPrd] = useState(false);
  const [fullscreenTitle, setFullscreenTitle] = useState('');
  const [fullscreenContent, setFullscreenContent] = useState('');
  const [editingStage, setEditingStage] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  // ── L2: import existing code (plan-app-factory-l2) ──
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [showManualModal, setShowManualModal] = useState(false);
  const [manualAgreed, setManualAgreed] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importZip, setImportZip] = useState<File | null>(null);
  const [importPath, setImportPath] = useState('');
  const [importedFiles, setImportedFiles] = useState<Array<{ path: string; size: number; lang: string }>>([]);
  const [importMeta, setImportMeta] = useState<{ has_tests: boolean; missing_deps: string[] } | null>(null);
  const [selectedIntents, setSelectedIntents] = useState<Record<string, string>>({});
  const [skipGate, setSkipGate] = useState(false);
  const [savingModify, setSavingModify] = useState(false);
  const [l2Stats, setL2Stats] = useState<any>(null);
  const [regeneratedWarnings, setRegeneratedWarnings] = useState<string[]>([]);

  // ── L3: incremental merge (plan-app-factory-l3) ──
  const [mergeStrategy, setMergeStrategy] = useState<'full_rewrite' | 'incremental_merge'>('full_rewrite');
  const [mergePreviews, setMergePreviews] = useState<any[]>([]);
  const [mergeImpact, setMergeImpact] = useState<any>(null);
  const [mergeDecisions, setMergeDecisions] = useState<Record<string, string>>({});
  const [showMergeReview, setShowMergeReview] = useState(false);
  const [buildingPreview, setBuildingPreview] = useState(false);
  const [applyingMerge, setApplyingMerge] = useState(false);
  // P1-04/05: formatting-fold + impact-analysis confirmation
  const [showFormatting, setShowFormatting] = useState(false);
  const [impactAnalysis, setImpactAnalysis] = useState<{
    auto_added: string[]; analysis: Record<string, string[]>;
  } | null>(null);

  // ── L4: multi-module (plan-app-factory-l4) ──
  const [modules, setModules] = useState<Array<{ module_id: string; description: string; root: string; imported: boolean; file_count: number }>>([]);
  const [selectedModule, setSelectedModule] = useState('default');
  const [showModulePanel, setShowModulePanel] = useState(false);
  const [moduleNamesInput, setModuleNamesInput] = useState('');
  const [creatingModules, setCreatingModules] = useState(false);
  const [moduleImporting, setModuleImporting] = useState(false);
  const [moduleFile, setModuleFile] = useState<File | null>(null);
  const [moduleImpact, setModuleImpact] = useState<any>(null);
  const [orchestrateResult, setOrchestrateResult] = useState<any>(null);
  const [orchestrating, setOrchestrating] = useState(false);
  // L4 v1.5: cross-module contract status on merge preview
  const [mergeCrossContracts, setMergeCrossContracts] = useState<any>(null);
  // ── L4.5: DB migration ──
  const [migrationPreview, setMigrationPreview] = useState<any>(null);
  const [migrationHistory, setMigrationHistory] = useState<any>({ migrations: [], pending: [] });
  const [generatingMigration, setGeneratingMigration] = useState(false);
  const [applyingMigration, setApplyingMigration] = useState(false);
  const [confirmDestructive, setConfirmDestructive] = useState(false);
  // ── L5: release ──
  const [releases, setReleases] = useState<any>({ releases: [], current: '' });
  const [creatingRelease, setCreatingRelease] = useState(false);
  const [transitioningRelease, setTransitioningRelease] = useState('');

  // Check for PRD on mount (may have been generated in a previous session)
  useEffect(() => {
    const raw = project as any;
    if (raw.confirmed_prd) setConfirmedPrd(raw.confirmed_prd);
    if (raw.confirmed_prd && (raw.runs?.length > 0)) setPrdReady(true);
  }, [project]);

  // Load full project data (list endpoint omits confirmed_prd)
  useEffect(() => {
    if (!project?.project_id) return;
    (async () => {
      try {
        const full = await projectApi.get(project.project_id) as any;
        if (full?.confirmed_prd) {
          setConfirmedPrd(full.confirmed_prd);
          setPrdReady(true);
        }
      } catch { /* ignore */ }
    })();
  }, [project.project_id]);

  // ── Check deploy status on mount ──
  useEffect(() => {
    if (!project?.project_id) return;
    (async () => {
      try {
        const r = await fetch('/api/platform/apps');
        const data = await r.json();
        const apps: any[] = data?.apps || [];
        const deployed = apps.find((a: any) =>
          (a.id || a.app_id || '').replace('factory_', '') === project.project_id
        );
        if (deployed) {
          // Extract app_url from description or build it
          const desc = deployed.description || '';
          const urlMatch = desc.match(/https?:\/\/[^\s]+/);
          setDeployUrl(urlMatch ? urlMatch[0] : `/app/sessions/${project.project_id}`);
        }
      } catch { /* ignore */ }
      setDeployChecked(true);
    })();
  }, [project.project_id]);

  // ── L2: surface regenerated warnings (Build-Log style, §3.9 条件 2) ──
  useEffect(() => {
    const runs = runHistory as any[];
    if (!runs?.length) return;
    const latest = runs[runs.length - 1];
    if (Array.isArray(latest?.regenerated_warnings) && latest.regenerated_warnings.length) {
      setRegeneratedWarnings(latest.regenerated_warnings);
    }
  }, [runHistory]);

  // ── L3-P1-05: impact analysis while selecting files (auto-added with reasons) ──
  useEffect(() => {
    if (!project?.project_id || !importedFiles.length) return;
    const checked = importedFiles
      .filter(f => (selectedIntents[f.path] || '').trim())
      .map(f => ({ path: f.path, intent: (selectedIntents[f.path] || '').trim() }));
    if (!checked.length) { setImpactAnalysis(null); return; }
    const t = setTimeout(async () => {
      try {
        const r = await projectApi.analyzeImpact(project.project_id, checked) as any;
        setImpactAnalysis(r?.impact || null);
      } catch { /* ignore */ }
    }, 300);
    return () => clearTimeout(t);
  }, [selectedIntents, importedFiles, project.project_id]);

  // ── Poll pipeline state during execution ──
  useEffect(() => {
    if (phase !== 'executing' && phase !== 'paused' && !phase?.includes('approval')) {
      return;
    }
    if (!project.project_id) return;
    const id = setInterval(async () => {
      try {
        const st = await projectApi.getState(project.project_id);
        const s = (st as any)?.state || {};
        const p = s.phase as string || phase;
        setPhase(p);
        setProgressState(s._progress || null);
        // v3.1: Track HITL stage from Core's _hitl_stage_id and _hitl_output_artifact
        if (p === 'paused') {
          const hitlId = s._hitl_stage_id as string;
          const hitlArtifact = s._hitl_output_artifact as string;
          if (hitlId) setHitlStageId(hitlId);
          if (hitlArtifact) setHitlOutputArtifact(hitlArtifact);
          if (!hitlId && !hitlArtifact && s._current_stage_idx != null) {
            // Fallback: Core hasn't written HITL fields yet (old pipeline)
            const idx = s._current_stage_idx as number;
            const stage = teamStages[idx];
            if (stage) {
              setHitlStageId((stage as any).id || (stage as any).agent_id || '');
              setHitlOutputArtifact((stage as any).output_artifact || null);
            }
          }
        } else if (p !== 'paused' && p !== 'executing') {
          setHitlStageId(null);
          setHitlOutputArtifact(null);
        }
        // Detect Agent mode: generated agent is deployed
        if (s._generated_agent && !agentMode) {
          setAgentName(s._generated_agent as string);
          setAgentMode(true);
        }
        const runs = (st as any)?.runs || [];
        if (runs.length > 0) setRunHistory(runs);
        // teamStages already set from project.team_stages (line 298);
        // don't overwrite with stripped _plan_stage_ids which lack output_artifact
        // Load outputs in team stage order (dynamic, not hardcoded)
        const outputs: Record<string, any> = {};
        const orderedKeys = teamStages.map(s => (s as any).output_artifact).filter(Boolean);
        const keys = orderedKeys.length > 0 ? orderedKeys : ['architecture', 'code', 'test_report'];
        for (const k of keys) {
          if (s[k] && typeof s[k] === 'object') outputs[k] = s[k];
        }
        if (Object.keys(outputs).length > 0) {
          if (p === 'paused' || p === 'executing') {
            // Race guard: when paused, ensure the HITL artifact is available before replacing.
            // Backend may write phase='paused' before persisting the artifact.
            const _hitlArtifact = s._hitl_output_artifact as string;
            if (p === 'paused' && _hitlArtifact && !outputs[_hitlArtifact] && outputs[Object.keys(outputs)[0]]) {
              // State incomplete — retry after brief delay to let backend finish persisting
              setTimeout(async () => {
                try {
                  const st2 = await projectApi.getState(project.project_id);
                  const s2 = (st2 as any)?.state || {};
                   const o2: Record<string, any> = {};
                   for (const k of keys) {
                     if (s2[k] && typeof s2[k] === 'object') o2[k] = s2[k];
                   }
                   if (o2[_hitlArtifact]) {
                     const filtered = _applyProgressiveOutputs(o2, s2._current_stage_idx || 0, keys);
                     if (Object.keys(filtered).length > 0) setStageOutputs(filtered);
                   }
                } catch { /* retry failed — next poll will fix */ }
              }, 400);
            } else {
              const filtered = _applyProgressiveOutputs(outputs, s._current_stage_idx || 0, orderedKeys);
              if (Object.keys(filtered).length > 0) setStageOutputs(filtered);
            }
          } else {
            setStageOutputs(prev => ({ ...prev, ...outputs }));
          }
        }
        if (p === 'done' || p === 'failed' || (p === 'paused' && phase !== 'paused')) onRefresh();
      } catch { /* ignore */ }
    }, 3000);
    return () => { clearInterval(id); };
  }, [phase, project.project_id]);

  // ── Independent execution timer — keeps ticking even when state endpoint times out ──
  useEffect(() => {
    if (phase === 'executing' && executingSince === null) {
      setExecutingSince(Date.now());
    } else if (phase !== 'executing') {
      setExecutingSince(null);
    }
  }, [phase, executingSince]);

  useEffect(() => {
    if (executingSince == null) return;
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - executingSince) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [executingSince]);

  // Load stage outputs whenever project opens (reads _final_state.json via API)
  useEffect(() => {
    if (!project.project_id) return;
    (async () => {
      try {
        const st = await projectApi.getState(project.project_id);
        const state = (st as any)?.state || {};
        const realPhase = state.phase as string;
        // Show all states immediately — no longer skip executing
        if (realPhase && realPhase !== 'idle' && realPhase !== 'pending') {
          setPhase(realPhase);
        }
        // Also load HITL fields on initial open (so button appears immediately)
        if (state._hitl_stage_id) setHitlStageId(state._hitl_stage_id as string);
        if (state._hitl_output_artifact) setHitlOutputArtifact(state._hitl_output_artifact as string);
        setProgressState(state._progress || null);
        const outputs: Record<string, any> = {};
        const orderedKeys = project.team_stages?.map(s => (s as any).output_artifact).filter(Boolean) || [];
        const keys = orderedKeys.length > 0 ? orderedKeys : ['architecture', 'code', 'test_report'];
        for (const k of keys) {
          if (state[k] && typeof state[k] === 'object' && state[k].raw_output) {
            outputs[k] = state[k];
          }
        }
        if (Object.keys(outputs).length > 0) setStageOutputs(prev => ({ ...prev, ...outputs }));
      } catch { /* ignore */ }
    })();
  }, [project.project_id]);

  useEffect(() => {
    setTeamStages(project.team_stages || []);
    setRunHistory(project.runs || []);
  }, [project]);

  const handleConfirm = async () => {
    if (!project.project_id) return;
    setStarting(true);
    try {
      await projectApi.confirm(project.project_id);
      const teamResult = await projectApi.recommendTeam(project.project_id);
      const stages = (teamResult as any)?.plan_stages || [];
      const rec = (teamResult as any)?.recommendation || {};
      setTeamStages(stages);
      setRecommendedMode((rec.mode as string) || '');
      setRecommendedReason((rec.reasoning as string) || '');
      setPhase('team_ready');
      toast.success('PRD 已确认，团队已推荐');
    } catch (e: any) { toastGateError(e, '确认失败'); }
    finally { setStarting(false); }
  };

  const handleStart = async () => {
    if (!project.project_id) return;
    setStarting(true);
    try {
      if (runHistory.length > 0 || (project as any).confirmed_prd) {
        // Rebuild: background thread, returns immediately, polling shows progress
        await projectApi.rebuild(project.project_id);
        setPhase('executing');
        toast.success('重建已触发');
      } else {
        const result = await projectApi.start(project.project_id);
        setPhase(result.phase || 'executing');
        toast.success('Pipeline 已启动');
      }
      onRefresh();
    } catch (e: any) { toastGateError(e, '启动失败'); }
    finally { setStarting(false); }
  };

  const handleFixBugs = async () => {
    if (!project.project_id) return;
    setFixingBugs(true);
    try {
      // Pre-fetch test_report to pass directly — avoids agent having to HTTP GET 68K state
      const st = await projectApi.getState(project.project_id);
      const testReportRaw = (st as any)?.state?.test_report?.raw_output || '';

      // ── Deterministic path: pytest report → fix programmer_agent directly (no LLM agent) ──
      let reportObj: any = null;
      try { reportObj = JSON.parse(testReportRaw); } catch {}
      const isPytest = reportObj && ((reportObj.test_mode === 'pytest' || reportObj.header?.test_mode === 'pytest') || (reportObj.bug_summary && Array.isArray(reportObj.bug_summary.failed_tests)));
      if (isPytest) {
        const totalBugs = reportObj?.bug_summary?.total_bugs ?? 0;
        const suggestedFix = reportObj?.bug_summary?.suggested_fix || '';
        if (!totalBugs || !suggestedFix) {
          toast.info('当前无 Bug 需要修复');
          setFixingBugs(false);
          return;
        }
        // pytest failures are code defects → regenerate the code-generating stage (dynamic, not hardcoded)
        const codeStage = teamStages.find((s: any) => s.output_artifact === 'code');
        const codeAgent = codeStage?.agent_id || 'programmer_agent';
        const gen = await projectApi.generateHypotheses(project.project_id, [codeAgent]);
        const fixPlan: string[] = (gen as any)?.fix_plan?.length ? (gen as any).fix_plan : [codeAgent];
        for (const stage of fixPlan) {
          await projectApi.regenerateStage(project.project_id, stage, suggestedFix);
        }
        toast.success(`修复已触发: ${fixPlan.length} 个阶段将重新生成，覆盖 ${totalBugs} 个 Bug`);
        setPhase('executing');
        onRefresh();
        setFixingBugs(false);
        return;
      }

      const result = await workspaceAgentApi.execute('test_report_orchestrator', {
        input: { project_id: project.project_id, test_report: testReportRaw },
      });
      const output = (result as any)?.output;
      if (output) {
        // ReAct agents wrap their trace in {text: "..."}. Extract the raw text first.
        const text = typeof output === 'string' ? output : (output?.text || output?.content || '');
        let summary: any = null;

        // 1. ReAct final answer: {"type":"done","answer":"{...json...}"} (line-separated)
        if (text) {
          const lines = text.split('\n');
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('{')) continue;
            try {
              const obj = JSON.parse(trimmed);
              if (obj && obj.type === 'done' && typeof obj.answer === 'string') {
                try { summary = JSON.parse(obj.answer); } catch { summary = obj.answer; }
                break;
              }
            } catch {}
          }
        }

        // 2. Fallback: search keywords in the raw text and extract enclosing JSON
        if (!summary) {
          const raw = text || JSON.stringify(output);
          for (const kw of ['"total_bugs"', '"fixed_stages"', '"status"']) {
            const idx = raw.lastIndexOf(kw);
            if (idx < 0) continue;
            const start = raw.lastIndexOf('{', idx);
            if (start < 0) continue;
            let depth = 0;
            let end = start;
            for (let j = start; j < raw.length; j++) {
              if (raw[j] === '{') depth++;
              if (raw[j] === '}') { depth--; if (depth === 0) { end = j + 1; break; } }
            }
            try { summary = JSON.parse(raw.slice(start, end)); break; } catch {}
          }
        }

        const status = typeof summary === 'string' ? '' : (summary?.status || '');
        if (status === 'no_bugs') {
          toast.info('当前无 Bug 需要修复');
        } else if (status === 'all_fixed') {
          toast.success(`修复完成: ${summary.before ?? '?'} 个 Bug 已全部清零`);
        } else if (status === 'regenerating') {
          const fixed = summary?.fixed_stages ?? 0;
          const total = summary?.total_bugs ?? 0;
          toast.success(`修复已触发: ${fixed} 个阶段将重新生成，覆盖 ${total} 个 Bug`);
        } else if (status === 'max_retries' || status === 'stuck' || status === 'timeout') {
          toast.warning(`修复未完全成功 (${status})，可再次点击「一键修复」`);
        } else if (summary && (summary?.fixed_stages != null || summary?.total_bugs != null || summary?.summary)) {
          const fixed = summary?.summary?.fixed_stages ?? summary?.fixed_stages ?? 0;
          const total = summary?.summary?.total_bugs ?? summary?.total_bugs ?? 0;
          toast.success(`修复编排完成: ${fixed} 个阶段已触发修复，覆盖 ${total} 个 Bug`);
        } else {
          toast.error('修复编排未返回结果，请重试');
        }
      } else {
        toast.error('修复编排未返回结果');
      }
      setPhase('executing');
      onRefresh();
    } catch (e: any) { toastGateError(e, '修复失败'); }
    finally { setFixingBugs(false); }
  };

  const handleRecommend = async () => {
    if (!project.project_id) return;
    setRecommending(true);
    try {
      const result = await projectApi.recommendTeam(project.project_id);
      const stages = (result as any)?.plan_stages || [];
      if (stages.length > 0) {
        setTeamStages(stages);
        toast.success(`AI 已推荐 ${stages.length} 个阶段`);
      } else {
        toast.warning('AI 推荐失败，请确保 PRD 已完成');
      }
    } catch (e: any) { toastGateError(e, '推荐失败'); }
    finally { setRecommending(false); }
  };

  const handleDeploy = async () => {
    if (!project.project_id) return;
    setDeploying(true);
    try {
      const result = await projectApi.deployToApp(project.project_id);
      setDeployUrl((result as any)?.app_url || '');
      toast.success('部署成功');
    } catch (e: any) { toastGateError(e, '部署失败'); }
    finally { setDeploying(false); }
  };

  const handleRollbackPrd = async () => {
    if (!project.project_id) return;
    if (!confirm('将回到需求编辑模式，当前 PRD 仍保留。确定？')) return;
    try {
      await projectApi.rollbackPrd(project.project_id);
      setPrdReady(false);
      setPhase('dialogue');
      setStageOutputs(null);
      toast.success('已进入需求编辑模式，可在下方对话中修改需求');
    } catch (e: any) { toastGateError(e, '操作失败'); }
  };

  // ── L2: import existing code handlers ──
  const loadImportStats = async () => {
    try {
      const r = await projectApi.getImportStats() as any;
      setL2Stats(r);
    } catch { /* ignore */ }
  };

  const handleOpenImport = async () => {
    if (!project.project_id) return;
    setShowManualModal(true);          // 《预期管理手册》弹窗 — 首次必读
    setShowImportPanel(true);
    loadImportStats();
    try {
      const r = await projectApi.listImportedFiles(project.project_id) as any;
      if (r?.files?.length) {
        setImportedFiles(r.files);
        setImportMeta({ has_tests: !!r.has_tests, missing_deps: r.missing_deps || [] });
      }
    } catch { /* no import yet */ }
  };

  const handleImportSubmit = async () => {
    if (!project.project_id) return;
    if (!importZip && !importPath.trim()) { toast('请选择 zip 文件或填写路径'); return; }
    setImporting(true);
    try {
      const fd = new FormData();
      if (importZip) fd.append('file', importZip);
      if (importPath.trim()) fd.append('existing_path', importPath.trim());
      const r = await projectApi.importRepo(project.project_id, fd) as any;
      if (r?.status === 'ok') {
        toast.success(`已导入 ${r.imported_files} 个文件`);
        const list = await projectApi.listImportedFiles(project.project_id) as any;
        setImportedFiles(list?.files || []);
        setImportMeta({ has_tests: !!list?.has_tests, missing_deps: list?.missing_deps || [] });
        setImportZip(null); setImportPath('');
      } else {
        toast.error(r?.detail || '导入失败');
      }
    } catch (e: any) { toastGateError(e, '导入失败'); }
    setImporting(false);
  };

  const handleApplyModify = async () => {
    if (!project.project_id) return;
    const modifyFiles = importedFiles
      .filter(f => (selectedIntents[f.path] || '').trim())
      .map(f => ({ path: f.path, intent: (selectedIntents[f.path] || '').trim() }));
    if (!modifyFiles.length) { toast.error('请至少勾选一个文件并填写修改意图'); return; }
    // security 类变更二次确认（§3.8）
    const scopeText = modifyFiles.map(m => m.path + ' ' + m.intent).join(' ');
    if (skipGate && /login|auth|password|pay|token|session|admin|verification/i.test(scopeText)) {
      if (!confirm('⚠️ 涉及认证/支付/权限类变更，跳过测试门禁风险较高。确定继续？')) return;
    }
    setSavingModify(true);
    try {
      const prd = {
        ...(confirmedPrd || {}),
        modify_files: modifyFiles,
        skip_pytest_gate: skipGate,
        merge_strategy: mergeStrategy,
      };
      await projectApi.updatePrd(project.project_id, prd as any);
      toast.success(mergeStrategy === 'incremental_merge'
        ? '修改意图已保存，开始增量构建（完成后可生成合并预览）'
        : '修改意图已保存，开始重建（被改文件将整体重写）');
      setShowImportPanel(false);
      setShowManualModal(false);
      await projectApi.rebuild(project.project_id);
      // 刷新状态进入构建中
      try {
        const st = await projectApi.getState(project.project_id) as any;
        await _refreshFromState((st as any)?.state);
      } catch { window.location.reload(); }
    } catch (e: any) { toastGateError(e, '保存失败'); }
    setSavingModify(false);
  };

  // ── L3: merge review handlers ──
  const handleGenerateMergePreview = async () => {
    if (!project.project_id) return;
    setBuildingPreview(true);
    try {
      const r = await projectApi.mergePreview(project.project_id, selectedModule) as any;
      if (r?.status === 'ok') {
        setMergePreviews(r.previews || []);
        setMergeImpact(r.impact || null);
        setMergeCrossContracts(r.cross_contracts || null);
        setMergeDecisions({});
        setShowMergeReview(true);
        if (r.cross_contracts?.broken?.length) {
          toast.error(`⚠️ 跨模块契约断裂 ${r.cross_contracts.broken.length} 处，合并将被阻断`);
        } else {
          toast.success(`已生成 ${r.previews?.length || 0} 个文件的合并预览`);
        }
      } else {
        toast.error(r?.detail || '生成合并预览失败');
      }
    } catch (e: any) { toastGateError(e, '生成合并预览失败'); }
    setBuildingPreview(false);
  };

  const handleToggleMergeDecision = (path: string, verdict: string) => {
    setMergeDecisions(prev => {
      const next = { ...prev };
      if (verdict === 'approved') next[path] = 'approved';
      else if (verdict === 'rejected') next[path] = 'rejected';
      else delete next[path];
      return next;
    });
  };

  const handleApplyMerge = async () => {
    if (!project.project_id) return;
    const allApproved = mergePreviews.length > 0 &&
      mergePreviews.every(p => mergeDecisions[p.path] === 'approved');
    if (!allApproved) {
      // P0-01: atomic approval — rejected → regenerate, never partial apply
      toast.error('必须审批全部文件（原子化）。请驳回并重新生成，或修改为通过后再应用。');
      return;
    }
    setApplyingMerge(true);
    try {
      const r = await projectApi.mergeApply(project.project_id, mergeDecisions) as any;
      if (r?.status === 'ok') {
        toast.success(`已应用 ${r.applied?.length || 0} 个文件`);
        if (r.warnings?.length) setRegeneratedWarnings(r.warnings);
        setShowMergeReview(false);
        setMergePreviews([]);
      } else {
        toast.error(r?.detail || '应用合并失败');
      }
    } catch (e: any) { toastGateError(e, '应用合并失败'); }
    setApplyingMerge(false);
  };

  // P0-01: rejected → regenerate whole affected set (rule is explicit in UI)
  const handleRegenerateAfterReject = async () => {
    if (!project.project_id) return;
    if (!confirm('将基于全部受影响文件重新生成（被驳回的文件不会再应用）。确定？')) return;
    try {
      setShowMergeReview(false);
      await projectApi.rebuild(project.project_id);
      try {
        const st = await projectApi.getState(project.project_id) as any;
        await _refreshFromState((st as any)?.state);
      } catch { window.location.reload(); }
    } catch (e: any) { toastGateError(e, '重新生成失败'); }
  };

  // ── L4: multi-module handlers ──
  const loadModules = async () => {
    if (!project?.project_id) return;
    try {
      const r = await projectApi.listModules(project.project_id) as any;
      setModules(r?.modules || []);
    } catch { /* ignore */ }
  };

  const handleCreateModules = async () => {
    if (!project?.project_id) return;
    const names = moduleNamesInput.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
    if (!names.length) { toast.error('请输入模块名（逗号分隔）'); return; }
    setCreatingModules(true);
    try {
      const r = await projectApi.createModules(project.project_id,
        names.map(n => ({ module_id: n, description: n }))) as any;
      if (r?.status === 'ok') {
        toast.success(`已声明 ${r.total} 个模块`);
        setModuleNamesInput('');
        await loadModules();
      } else { toast.error(r?.detail || '声明模块失败'); }
    } catch (e: any) { toastGateError(e, '声明模块失败'); }
    setCreatingModules(false);
  };

  const handleModuleImport = async () => {
    if (!project?.project_id || !moduleFile) return;
    setModuleImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', moduleFile);
      const r = await projectApi.importModuleRepo(project.project_id, selectedModule, fd) as any;
      if (r?.status === 'ok') {
        toast.success(`模块 ${r.module_id} 已导入 ${r.imported_files} 个文件`);
        setModuleFile(null);
        await loadModules();
      } else { toast.error(r?.detail || '导入失败'); }
    } catch (e: any) { toastGateError(e, '导入失败'); }
    setModuleImporting(false);
  };

  const handleCrossModuleImpact = async (moduleId: string) => {
    if (!project?.project_id) return;
    try {
      const r = await projectApi.crossModuleImpact(project.project_id, moduleId) as any;
      if (r?.status === 'ok') {
        setModuleImpact({ ...r, for_module: moduleId });
        toast.success(`影响闭包：${r.closure?.join(' → ') || moduleId}`);
      } else { toast.error(r?.detail || '影响分析失败'); }
    } catch (e: any) { toastGateError(e, '影响分析失败'); }
  };

  const handleOrchestrate = async (moduleId: string) => {
    if (!project?.project_id) return;
    if (!confirm(`按依赖顺序编排受影响模块（变更 ${moduleId} 的影响闭包）？`)) return;
    setOrchestrating(true);
    try {
      const r = await projectApi.moduleOrchestrate(project.project_id, [moduleId]) as any;
      if (r?.status === 'ok') {
        setOrchestrateResult(r);
        toast.success(`编排完成：${r.order?.join(' → ') || ''}`);
      } else { toast.error(r?.detail || '编排失败'); }
    } catch (e: any) { toastGateError(e, '编排失败'); }
    setOrchestrating(false);
  };

  // ── L4.5: migration handlers ──
  const loadMigrationHistory = async () => {
    if (!project?.project_id) return;
    try {
      const r = await projectApi.listMigrations(project.project_id) as any;
      setMigrationHistory(r || { migrations: [], pending: [] });
    } catch { /* ignore */ }
  };

  const handleMigrationPreview = async () => {
    if (!project?.project_id) return;
    setGeneratingMigration(true);
    try {
      const r = await projectApi.migrationPreview(project.project_id, selectedModule) as any;
      if (r?.status === 'ok') {
        setMigrationPreview(r);
        if (!r.has_changes) toast.success('无模型变更，不需要迁移');
        else if (r.destructive) toast.warning('⚠️ 存在破坏性变更，需显式确认');
        else toast.success('迁移预览已生成');
        await loadMigrationHistory();
      } else { toast.error(r?.detail || '生成迁移预览失败'); }
    } catch (e: any) { toastGateError(e, '生成迁移预览失败'); }
    setGeneratingMigration(false);
  };

  const handleApplyMigration = async () => {
    if (!project?.project_id || !migrationPreview?.migration) return;
    const mig = migrationPreview.migration;
    if (mig.destructive && !confirmDestructive) {
      toast.error('破坏性迁移需勾选"我了解数据影响"后确认应用');
      return;
    }
    setApplyingMigration(true);
    try {
      const r = await projectApi.applyMigrations(project.project_id, [mig.id], confirmDestructive) as any;
      if (r?.status === 'ok') {
        toast.success(`迁移已应用：${r.applied?.join(', ') || ''}`);
        setMigrationPreview(null);
        setConfirmDestructive(false);
        await loadMigrationHistory();
      } else { toast.error(r?.detail || '应用迁移失败'); }
    } catch (e: any) { toastGateError(e, '应用迁移失败'); }
    setApplyingMigration(false);
  };

  const handleRollbackMigration = async (id: string) => {
    if (!project?.project_id) return;
    if (!confirm(`应用 down 脚本回滚迁移 ${id}？`)) return;
    try {
      const r = await projectApi.rollbackMigration(project.project_id, id) as any;
      if (r?.status === 'ok') toast.success(`已回滚：${id}`);
      else toast.error(r?.detail || '回滚失败');
      await loadMigrationHistory();
    } catch (e: any) { toastGateError(e, '回滚失败'); }
  };

  // ── L5: release handlers ──
  const loadReleases = async () => {
    if (!project?.project_id) return;
    try {
      const r = await projectApi.listReleases(project.project_id) as any;
      setReleases(r || { releases: [], current: '' });
    } catch { /* ignore */ }
  };

  const handleCreateRelease = async () => {
    if (!project?.project_id) return;
    setCreatingRelease(true);
    try {
      const r = await projectApi.createRelease(project.project_id, selectedModule) as any;
      if (r?.status === 'ok') {
        toast.success(`发布 ${r.release?.version} 已创建（${r.release?.status}）`);
        if (r.estimated_hint) toast.warning('⚠️ 通过率为估算值，建议先跑真实测试再全量');
        await loadReleases();
      } else { toast.error(r?.detail || '创建发布失败'); }
    } catch (e: any) { toastGateError(e, '创建发布失败'); }
    setCreatingRelease(false);
  };

  const handleReleaseTransition = async (version: string, action: 'canary' | 'full' | 'rollback', canaryWeight?: number) => {
    if (!project?.project_id) return;
    if (action === 'rollback' && !confirm(`回滚发布 ${version}（切换 current 到历史版本）？`)) return;
    setTransitioningRelease(version);
    try {
      const r = await projectApi.releaseTransition(project.project_id, version, action, '', canaryWeight) as any;
      if (r?.status === 'ok') {
        toast.success(`发布 ${version} → ${action}`);
        await loadReleases();
      } else { toast.error(r?.detail || '状态切换失败'); }
    } catch (e: any) { toastGateError(e, '状态切换失败'); }
    setTransitioningRelease('');
  };

  const handleEditStage = (stageKey: string, currentRaw: any) => {
    const content = typeof currentRaw === 'string' ? currentRaw : JSON.stringify(currentRaw, null, 2);
    setEditingStage(stageKey);
    setEditContent(content);
  };

  const handleSaveStageEdit = async () => {
    if (!editingStage || !project.project_id) return;
    setSavingEdit(true);
    try {
      await projectApi.updateStageArtifact(project.project_id, editingStage, editContent);
      toast.success('已保存，可点击「从此阶段重建」');
      setEditingStage(null);
    } catch (e: any) { toastGateError(e, '保存失败'); }
    finally { setSavingEdit(false); }
  };

  const handleEditPrd = () => {
    setPrdEditText(JSON.stringify(confirmedPrd, null, 2));
    setShowPrdDetail(true);
  };

  const handleSavePrd = async () => {
    if (!project.project_id) return;
    try {
      const parsed = JSON.parse(prdEditText);
      setSavingPrd(true);
      await projectApi.updatePrd(project.project_id, parsed);
      setConfirmedPrd(parsed);
      setShowPrdDetail(false);
      toast.success('PRD 已保存，可点"重建"重新生成代码');
    } catch { toast('JSON 格式错误，请检查'); }
    finally { setSavingPrd(false); }
  };

  // ── P1: Progressive output clearing — keeps upstream stages, clears only downstream ──
  const _applyProgressiveOutputs = (
    outputs: Record<string, any>,
    currentStageIdx: number,
    allStageKeys: string[],
  ): Record<string, any> => {
    const keepIdx = Math.min(currentStageIdx + 1, allStageKeys.length);
    const filtered: Record<string, any> = {};
    for (const k of allStageKeys.slice(0, keepIdx)) {
      if (outputs[k] !== undefined) filtered[k] = outputs[k];
    }
    return filtered;
  };

  // ── Shared: refresh UI from a pipeline state snapshot (used by poll, approve, reject) ──
  const _refreshFromState = async (stateObj: any) => {
    const s = stateObj || {};
    const p = s.phase as string || 'executing';
    setPhase(p);
    setProgressState(s._progress || null);

    if (p === 'paused') {
      const hitlId = s._hitl_stage_id as string;
      const hitlArtifact = s._hitl_output_artifact as string;
      if (hitlId) setHitlStageId(hitlId);
      if (hitlArtifact) setHitlOutputArtifact(hitlArtifact);
    }
    // Don't clear HITL during executing — let it naturally transition via poll

    const orderedKeys = teamStages.map((ts: any) => ts.output_artifact).filter(Boolean);
    const keys = orderedKeys.length > 0 ? orderedKeys : ['architecture', 'code', 'test_report'];
    const outputs: Record<string, any> = {};
    for (const k of keys) {
      if (s[k] && typeof s[k] === 'object') outputs[k] = s[k];
    }
    if (Object.keys(outputs).length > 0) {
      if (p === 'paused' || p === 'executing') {
        const _hitlArtifact = s._hitl_output_artifact as string;
        if (p === 'paused' && _hitlArtifact && !outputs[_hitlArtifact] && outputs[Object.keys(outputs)[0]]) {
          setTimeout(async () => {
            try {
              const st2 = await projectApi.getState(project.project_id);
              const s2 = (st2 as any)?.state || {};
              const o2: Record<string, any> = {};
              for (const k of keys) {
                if (s2[k] && typeof s2[k] === 'object') o2[k] = s2[k];
              }
              if (o2[_hitlArtifact]) {
                const filtered = _applyProgressiveOutputs(o2, s2._current_stage_idx || 0, keys);
                if (Object.keys(filtered).length > 0) setStageOutputs(filtered);
              }
            } catch {}
          }, 400);
        } else {
          const filtered = _applyProgressiveOutputs(outputs, s._current_stage_idx || 0, keys);
          if (Object.keys(filtered).length > 0) setStageOutputs(filtered);
        }
      } else {
        setStageOutputs(prev => ({ ...prev, ...outputs }));
      }
    }
  };

  // ── Transition to executing mode — optimistic, then correct via real state ──
  const _enterExecutingMode = async () => {
    setPhase('executing');
    setHitlStageId(null);
    setHitlOutputArtifact(null);

    try {
      const st = await projectApi.getState(project.project_id);
      const s = (st as any)?.state || {};
      setProgressState(s._progress || null);

      const orderedKeys = teamStages.map((ts: any) => ts.output_artifact).filter(Boolean);
      const keys = orderedKeys.length > 0 ? orderedKeys : ['architecture', 'code', 'test_report'];
      const outputs: Record<string, any> = {};
      for (const k of keys) {
        if (s[k] && typeof s[k] === 'object') outputs[k] = s[k];
      }
      if (Object.keys(outputs).length > 0) {
        const filtered = _applyProgressiveOutputs(outputs, s._current_stage_idx || 0, keys);
        if (Object.keys(filtered).length > 0) setStageOutputs(filtered);
      }

      const backendPhase = s.phase as string;
      if (backendPhase === 'paused') {
        setPhase('paused');
        if (s._hitl_stage_id) setHitlStageId(s._hitl_stage_id as string);
        if (s._hitl_output_artifact) setHitlOutputArtifact(s._hitl_output_artifact as string);
      } else if (backendPhase === 'done' || backendPhase === 'failed') {
        setPhase(backendPhase);
        onRefresh();
      }
    } catch { /* keep 'executing' — poll will fix */ }
  };

  const handleApprove = async () => {
    if (!project.project_id) return;
    // Optimistic: progress bar appears immediately
    setPhase('executing');
    setHitlStageId(null);
    setHitlOutputArtifact(null);
    setStarting(true);
    try {
      await projectApi.approve(project.project_id);
      toast.success('已审批，正在继续执行');
      // Fetch state AFTER API — backend has processed the approval
      const st = await projectApi.getState(project.project_id);
      await _refreshFromState((st as any)?.state);
    } catch (e: any) {
      toastGateError(e, '审批失败');
      const st = await projectApi.getState(project.project_id);
      await _refreshFromState((st as any)?.state);
    }
    finally { setStarting(false); }
  };

  const handleReject = async () => {
    if (!project.project_id) return;
    const feedback = window.prompt('驳回理由（可选）：');
    if (feedback === null) return;
    // Clear only rejected stage + downstream
    const _rejectedArtifact = hitlOutputArtifact;
    const _keys = teamStages.map((ts: any) => ts.output_artifact).filter(Boolean);
    const _rejIdx = _rejectedArtifact ? _keys.indexOf(_rejectedArtifact) : -1;
    if (_rejIdx >= 0) {
      setStageOutputs(prev => {
        if (!prev) return null;
        const next: Record<string, any> = {};
        for (const k of _keys.slice(0, _rejIdx)) {
          if (prev[k]) next[k] = prev[k];
        }
        return next;
      });
    } else {
      setStageOutputs(null);
    }
    // Optimistic: progress bar appears immediately
    setPhase('executing');
    setHitlStageId(null);
    setHitlOutputArtifact(null);
    setRejecting(true);
    try {
      await projectApi.reject(project.project_id, feedback);
      toast.success('已驳回，将重新生成');
      const st = await projectApi.getState(project.project_id);
      await _refreshFromState((st as any)?.state);
    } catch (e: any) {
      toastGateError(e, '驳回失败');
      const st = await projectApi.getState(project.project_id);
      await _refreshFromState((st as any)?.state);
    }
    finally { setRejecting(false); }
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} className="fixed inset-y-0 right-0 w-full max-w-2xl bg-dark-card border-l border-dark-border shadow-2xl z-50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-border">
        <div>
          <h2 className="text-lg font-bold text-gray-100">{project.name}</h2>
          <p className="text-xs text-gray-500">{project.description}</p>
        </div>
        <Button variant="ghost" onClick={onClose}>✕</Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Progress */}
        {phase === 'done' ? (
          <div className="space-y-2">
            {/* L2: regenerated warnings — no diff view in L2, must surface for manual review (§3.9) */}
            {regeneratedWarnings.length > 0 && (
              <div className="p-3 rounded bg-amber-500/10 border border-amber-500/40 text-xs space-y-1">
                <div className="text-amber-300 font-semibold">⚠️ 以下文件已被整体重写（非合并）— 请人工 Review Diff</div>
                {regeneratedWarnings.map((w, i) => (
                  <div key={i} className="text-amber-200/90 font-mono text-[10px]">{w}</div>
                ))}
              </div>
            )}
            <div className="p-3 rounded bg-green-500/10 border border-green-500/30 text-sm text-green-300">
              ✅ 构建完成
              {mergeStrategy === 'incremental_merge' && (
                <Button variant="secondary" size="sm" className="ml-3"
                  onClick={handleGenerateMergePreview} loading={buildingPreview}>
                  🔀 生成合并预览（L3 增量审批）
                </Button>
              )}
              {agentMode && (
                <a href={`/app/apps/${project.project_id}`} target="_blank" rel="noreferrer" className="ml-3 text-primary underline text-xs flex items-center gap-1 inline-flex">
                  <ExternalLink className="w-3 h-3" /> 使用应用
                </a>
              )}
              {!agentMode && !deployUrl && (
                <Button variant="primary" size="sm" className="ml-3" onClick={handleDeploy} loading={deploying}>部署到 App</Button>
              )}
              {deployUrl && (
                <a href={deployUrl} target="_blank" rel="noreferrer" className="ml-3 text-primary underline text-xs flex items-center gap-1 inline-flex">
                  <ExternalLink className="w-3 h-3" /> 打开应用
                </a>
              )}
              {!agentMode && (
                <Button variant="ghost" size="sm" className="ml-2" onClick={handleRollbackPrd}>
                  重新编辑需求
                </Button>
              )}
            </div>
            {/* Health Report Card — auto-loads when pipeline done */}
            {healthReport ? (
              <div className="p-3 rounded bg-blue-500/5 border border-blue-500/30 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-blue-300 font-medium">Pipeline 健康报告</span>
                  <span className="text-lg font-bold text-blue-200">{healthReport.overall_score || '?'}/100</span>
                </div>
                {healthReport.dimensions?.map((d: any) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <span className="w-24 text-gray-400 truncate">{d.display_name || d.name}</span>
                    <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(100, d.score / d.max_score * 100)}%` }} />
                    </div>
                    <span className="w-8 text-right text-gray-300">{d.score}</span>
                  </div>
                ))}
              </div>
            ) : (
              <button
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                onClick={async () => {
                  setLoadingHealth(true);
                  try {
                    const r = await projectApi.getHealthReport(project.project_id);
                    setHealthReport(r as any);
                  } catch (e) {
                    toastGateError(e, '健康报告加载失败');
                  }
                  setLoadingHealth(false);
                }}
              >
                {loadingHealth ? <Loader2 className="w-3 h-3 animate-spin" /> : <BarChart3 className="w-3 h-3" />}
                查看健康报告
              </button>
            )}
          </div>
        ) : phase === 'executing' ? (
          <div className="p-3 rounded bg-blue-500/10 border border-blue-500/30 text-sm space-y-3">
            <div className="flex items-center gap-2 text-blue-300">
              <Loader2 className="w-4 h-4 animate-spin" /> Pipeline 执行中...
            </div>
            {/* Pipeline progress with stages */}
            {teamStages.length > 0 && (() => {
              // ── Config-driven stage detection ──
              // Use _progress.stage (=output_artifact) for exact running-stage match.
              // Fallback to _current_stage_idx for done/completed detection.
              const runningKey = progressState?.status === 'running' ? progressState.stage : null;
              const doneKey = progressState?.status === 'completed' ? progressState.stage : null;
              const cumDone = progressState ? (() => {
                // If we have a running/done key, count stages up to and including it
                let count = 0;
                for (const s of teamStages) {
                  if ((s as any).output_artifact === runningKey || (s as any).output_artifact === doneKey) {
                    count++;
                    break;
                  }
                  count++;
                }
                return count;
              })() : (stageOutputs ? Object.keys(stageOutputs).length : 0);

              const progressPct = teamStages.length > 0
                ? Math.round((cumDone / teamStages.length) * 100)
                : 0;

              return (<>
                <div className="space-y-1.5">
                  {teamStages.map((s, i) => {
                    const key = (s as any).output_artifact || '';
                    const isRunning = runningKey === key;
                    // Stage is done if its output_artifact has produced data
                    const hasOutput = stageOutputs ? stageOutputs[key] != null : false;
                    const isDone = hasOutput && !isRunning;
                    const name = s.agent_name || s.agent_id || s.id || `Stage ${i + 1}`;
                    return (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        {isDone ? (
                          <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                        ) : isRunning ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400 flex-shrink-0" />
                        ) : (
                          <Clock className="w-3.5 h-3.5 text-gray-600 flex-shrink-0" />
                        )}
                        <span className={isDone ? 'text-green-300' : isRunning ? 'text-blue-300 font-medium' : 'text-gray-500'}>
                          {name}
                        </span>
                        {isRunning && <span className="text-blue-400 ml-auto text-[10px]">进行中</span>}
                      </div>
                    );
                  })}
                  <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }} />
                  </div>
                </div>
              </>);
            })()}
            {teamStages.length === 0 && (
              <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: '60%' }} />
              </div>
            )}
            {/* Sub-step progress indicator */}
            {progressState?.status === 'running' && (
              <div className="text-[10px] text-blue-400 mt-1 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                {progressState.stage === 'test_executor' ? (
                  <>执行对话测试中{progressState.current_step > 0 ? ` (Step ${progressState.current_step})` : ''}... {elapsed}s</>
                ) : progressState.backend === 'agent' ? (
                  <>{progressState.stage} 执行中{progressState.current_step > 0 ? ` (Step ${progressState.current_step})` : ''}... {elapsed}s</>
                ) : (
                  <>运行中... {elapsed}s</>
                )}
              </div>
            )}
            {progressState?.status === 'timeout' && (
              <div className="text-[10px] text-amber-400 mt-1 flex items-center gap-1">
                ⚠️ 测试执行超时（{progressState.elapsed_sec}s）— 流水线将继续
              </div>
            )}
            {progressState?.status === 'error' && (
              <div className="text-[10px] text-red-400 mt-1 flex items-center gap-1">
                ❌ 执行失败: {(progressState.error || '').slice(0, 60)}
              </div>
            )}
            {progressState?.status === 'completed' && (
              <div className="text-[10px] text-green-400 mt-1 flex items-center gap-1">
                ✅ 完成 ({progressState.elapsed_sec}s)
              </div>
            )}
          </div>
        ) : phase === 'paused' || phase?.includes('approval') ? (
          <div className="text-[11px] text-amber-400 flex items-center gap-1.5 p-2 rounded bg-amber-500/5">
            <Clock className="w-3 h-3" /> 等待审批 — 请在下方「阶段产出」中审核并操作
          </div>
        ) : null}

        {/* PRD summary — always show if confirmed */}
        {confirmedPrd && (
          <div className="p-3 rounded border border-green-500/30 bg-green-500/5 text-xs space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-green-400" />
              <span className="text-green-300 font-semibold">PRD 已确认</span>
              <span className="ml-auto text-gray-500 text-[10px]">{new Date().toLocaleDateString()}</span>
            </div>
            <p className="text-gray-200 font-medium">{confirmedPrd.title as string || 'Untitled'}</p>
            <p className="text-gray-400">{(confirmedPrd.user_stories as any[])?.length || 0} 个 User Stories</p>
            <div className="flex gap-1.5">
              {!showPrdDetail ? (
                <>
                <button onClick={handleEditPrd} className="text-[10px] px-2 py-1 rounded bg-dark-hover text-gray-300 hover:text-white transition-colors">📋 查看 & 编辑</button>
                <button onClick={() => {
                  const pmKey = teamStages[0]?.output_artifact;
                  const pmRaw = pmKey && stageOutputs ? stageOutputs[pmKey]?.raw_output : null;
                  setFullscreenTitle('PRD: ' + (confirmedPrd?.title as string || ''));
                  setFullscreenContent(pmRaw || JSON.stringify(confirmedPrd || {}, null, 2));
                }}
                  className="text-[10px] px-2 py-1 rounded bg-dark-hover text-gray-300 hover:text-white transition-colors">🔍 全屏</button>
                </>
              ) : (
                <>
                  <button onClick={() => setShowPrdDetail(false)} className="text-[10px] px-2 py-1 rounded bg-dark-hover text-gray-400 hover:text-gray-300 transition-colors">收起</button>
                </>
              )}
            </div>
            {/* PRD detail / edit section */}
            {showPrdDetail && (
              <div className="space-y-2 pt-2 border-t border-dark-border">
                <textarea
                  value={prdEditText}
                  onChange={e => setPrdEditText(e.target.value)}
                  className="w-full min-h-[300px] bg-dark-hover border border-dark-border rounded p-2 text-xs text-gray-200 font-mono resize-y focus:outline-none focus:border-primary"
                />
                <div className="flex gap-2">
                  <Button variant="primary" size="sm" onClick={handleSavePrd} loading={savingPrd}>保存 PRD</Button>
                  <Button variant="ghost" size="sm" onClick={() => setShowPrdDetail(false)}>取消</Button>
                  <span className="ml-auto text-[10px] text-gray-500">保存后点"重建"重新生成代码</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Team stages */}
        {teamStages.length > 0 && (
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-gray-400 uppercase">团队配置</h3>
            {recommendedMode && (
              <div className="flex items-center gap-1.5 text-[10px]">
                <span className={`px-1.5 py-0.5 rounded ${recommendedMode === 'agent' ? 'bg-purple-500/20 text-purple-300' : 'bg-blue-500/20 text-blue-300'}`}>
                  {recommendedMode === 'agent' ? '🤖 Agent 应用模式' : '💻 代码应用模式'}
                </span>
                {recommendedReason && <span className="text-gray-500 truncate max-w-[300px]">{recommendedReason.slice(0, 80)}</span>}
              </div>
            )}
            <div className="flex items-center gap-1 text-xs">
              {teamStages.map((s, i) => (
                <React.Fragment key={s.id || i}>
                  <span className="px-2 py-1 rounded bg-dark-hover text-gray-300">{s.agent_name || s.agent_id}</span>
                  {i < teamStages.length - 1 && <span className="text-gray-600">→</span>}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}

        {/* L4: 多模块编排（plan-app-factory-l4 §4） */}
        <div className="p-3 rounded border border-teal-500/30 bg-teal-500/5 text-xs space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-teal-300 font-semibold">🧩 多模块编排（L4）</span>
            <Button variant="ghost" size="sm" className="ml-auto"
              onClick={() => { setShowModulePanel(v => !v); if (!showModulePanel) loadModules(); }}>
              {showModulePanel ? '收起' : '模块管理'}
            </Button>
          </div>
          {showModulePanel && (
            <div className="space-y-2 pt-2 border-t border-dark-border">
              {/* 声明模块 */}
              <div className="flex gap-1.5">
                <input value={moduleNamesInput} onChange={e => setModuleNamesInput(e.target.value)}
                  placeholder="声明模块（逗号分隔，如 auth,billing,order）"
                  className="flex-1 bg-dark-hover border border-dark-border rounded px-2 py-1 text-[10px] text-gray-200" />
                <Button variant="secondary" size="sm" onClick={handleCreateModules} loading={creatingModules}>声明</Button>
              </div>
              {/* 模块列表 */}
              {modules.length === 0 && (
                <div className="text-[10px] text-gray-500">未声明模块（默认单模块模式，L2/L3 不受影响）</div>
              )}
              <div className="space-y-1.5">
                {modules.map(m => {
                  const active = selectedModule === m.module_id;
                  return (
                    <div key={m.module_id} className={`rounded border p-1.5 flex items-center gap-2 flex-wrap ${active ? 'border-teal-500/50 bg-teal-500/10' : 'border-dark-border'}`}>
                      <label className="flex items-center gap-1.5 text-[11px] cursor-pointer">
                        <input type="radio" name="module" checked={active}
                          onChange={() => setSelectedModule(m.module_id)} />
                        <span className="font-mono text-teal-200">{m.module_id}</span>
                        <span className="text-gray-500">({m.file_count} 文件{m.imported ? ' ✓已导入' : ''})</span>
                      </label>
                      <div className="ml-auto flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => handleCrossModuleImpact(m.module_id)}>影响分析</Button>
                        <Button variant="secondary" size="sm" onClick={() => handleOrchestrate(m.module_id)} loading={orchestrating}>编排</Button>
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* 选中模块导入 */}
              {modules.length > 0 && (
                <div className="flex gap-1.5 items-center">
                  <label className="text-[10px] text-gray-400">导入到 [{selectedModule}]：</label>
                  <input type="file" accept=".zip" onChange={e => setModuleFile(e.target.files?.[0] || null)}
                    className="text-[10px] text-gray-300 flex-1" />
                  <Button variant="secondary" size="sm" onClick={handleModuleImport} loading={moduleImporting}
                    disabled={!moduleFile}>导入</Button>
                </div>
              )}
              {/* 跨模块影响展示 */}
              {moduleImpact && (
                <div className="p-2 rounded bg-teal-500/10 border border-teal-500/30 text-[10px] space-y-1">
                  <div className="text-teal-200 font-medium">影响分析 [{moduleImpact.for_module}]</div>
                  <div className="text-gray-300">影响闭包：{moduleImpact.closure?.join(' → ') || moduleImpact.for_module}</div>
                  {Object.entries(moduleImpact.graph || {}).map(([mid, g]: [string, any]) => (
                    <div key={mid} className="text-gray-400">
                      <span className="font-mono text-teal-300/90">{mid}</span>
                      {g.depends_on?.length > 0 && <span> → 依赖 {g.depends_on.join(', ')}</span>}
                      {g.depended_by?.length > 0 && <span> ← 被 {g.depended_by.join(', ')} 依赖</span>}
                      {g.evidence && Object.keys(g.evidence).length > 0 && (
                        <div className="pl-3 text-gray-500">
                          {Object.entries(g.evidence).map(([t, ev]: [string, any]) => (
                            <div key={t}>· {t}: {(ev as any[]).map((e: any) => e.line_file || e.route || e.topic || '').filter(Boolean).join(', ')}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {/* 编排结果 */}
              {orchestrateResult && (
                <div className="p-2 rounded bg-blue-500/10 border border-blue-500/30 text-[10px] space-y-0.5">
                  <div className="text-blue-200 font-medium">编排结果</div>
                  <div className="text-gray-300">顺序：{orchestrateResult.order?.join(' → ')}</div>
                  {(orchestrateResult.results || []).map((r: any, i: number) => (
                    <div key={i} className="text-gray-400">
                      {r.module_id}: {r.triggered ? '✓ 已触发' : r.skipped ? `跳过（${r.reason}）` : `✗ ${r.error || ''}`}
                    </div>
                  ))}
                </div>
              )}
              {/* L4.5: 数据库迁移 */}
              <div className="pt-1 border-t border-dark-border space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-teal-300 font-medium">🗄️ 数据库迁移（L4.5）— 模型变更自动生成 up/down DDL</span>
                  <Button variant="ghost" size="sm" className="ml-auto" onClick={loadMigrationHistory}>历史</Button>
                  <Button variant="secondary" size="sm" onClick={handleMigrationPreview} loading={generatingMigration}>
                    生成迁移预览
                  </Button>
                </div>
                {/* 迁移预览 */}
                {migrationPreview?.has_changes && migrationPreview.migration && (
                  <div className="p-2 rounded bg-amber-500/10 border border-amber-500/40 space-y-1">
                    <div className="text-[10px] text-amber-200 font-medium">
                      迁移 {migrationPreview.migration.id}
                      {migrationPreview.destructive && <span className="text-red-300 ml-2">⛔ 破坏性变更</span>}
                    </div>
                    {/* destructive 红横幅 + 确认勾选 */}
                    {migrationPreview.destructive && (
                      <div className="p-1.5 rounded bg-red-500/10 border border-red-500/40 text-[10px] text-red-300">
                        破坏性变更（{[
                          ...Object.keys(migrationPreview.migration.summary?.removed_columns || {}).map(t =>
                            `删列 ${t}.${migrationPreview.migration.summary.removed_columns[t].join(',')}`),
                          ...Object.keys(migrationPreview.migration.summary?.type_changed || {}).map(t =>
                            `类型变更 ${t}.${Object.keys(migrationPreview.migration.summary.type_changed[t]).join(',')}`),
                          ...(migrationPreview.migration.summary?.removed_tables || []).map(t => `删表 ${t}`),
                        ].join('；')}）
                        <label className="flex items-center gap-1 mt-1 cursor-pointer">
                          <input type="checkbox" checked={confirmDestructive} onChange={e => setConfirmDestructive(e.target.checked)} />
                          我了解数据影响，确认应用
                        </label>
                      </div>
                    )}
                    {/* 跨模块字段引用 */}
                    {migrationPreview.cross_refs?.length > 0 && (
                      <div className="text-[10px] text-red-300/90">
                        ⚠️ 跨模块字段引用：{migrationPreview.cross_refs.map((c: any) => `${c.module}(${c.file} 引用 ${c.field})`).join('、')}
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-1.5">
                      <div>
                        <div className="text-[10px] text-gray-400">UP</div>
                        <pre className="bg-black/40 rounded p-1.5 text-[9px] font-mono text-green-300 whitespace-pre-wrap max-h-24 overflow-auto">{migrationPreview.migration.up_sql}</pre>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-400">DOWN</div>
                        <pre className="bg-black/40 rounded p-1.5 text-[9px] font-mono text-amber-300 whitespace-pre-wrap max-h-24 overflow-auto">{migrationPreview.migration.down_sql}</pre>
                      </div>
                    </div>
                    <div className="flex gap-1.5">
                      <Button variant="primary" size="sm" onClick={handleApplyMigration} loading={applyingMigration}>应用迁移</Button>
                      <Button variant="ghost" size="sm" onClick={() => setMigrationPreview(null)}>收起</Button>
                      <span className="ml-auto text-[10px] text-gray-500">默认仅记录状态；AIPLAT_DB_EXECUTE=true 才执行真实 SQL</span>
                    </div>
                  </div>
                )}
                {/* 迁移历史 */}
                {(migrationHistory.migrations?.length > 0 || migrationHistory.pending?.length > 0) && (
                  <div className="text-[10px] text-gray-400 space-y-0.5">
                    {migrationHistory.pending?.map((m: any) => (
                      <div key={m.id} className="text-amber-300">⏳ {m.id}（待应用{m.destructive ? '·破坏性' : ''}）[{m.module_id}]</div>
                    ))}
                    {migrationHistory.migrations?.map((m: any) => (
                      <div key={m.id} className="flex items-center gap-2">
                        <span className={m.status === 'rolled_back' ? 'text-gray-500' : 'text-green-300'}>
                          {m.status === 'applied' ? '✅' : '↩️'} {m.id}（{m.status}）[{m.module_id}]
                        </span>
                        {m.status === 'applied' && (
                          <button className="text-red-300 underline" onClick={() => handleRollbackMigration(m.id)}>回滚</button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {/* L5: 发布流水线 */}
                <div className="pt-1 border-t border-dark-border space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-blue-300 font-medium">🚀 发布流水线（L5）— 版本化 + 金丝雀灰度</span>
                    <Button variant="ghost" size="sm" className="ml-auto" onClick={loadReleases}>版本</Button>
                    <Button variant="secondary" size="sm" onClick={handleCreateRelease} loading={creatingRelease}>
                      创建发布
                    </Button>
                  </div>
                  {releases.releases?.length > 0 && (
                    <div className="text-[10px] space-y-0.5">
                      <div className="text-gray-500">当前指针：{releases.current?.includes('releases') ? releases.current.split('releases/')[1]?.split('/')[0] : '（未设置）'}</div>
                      {releases.releases.map((r: any) => {
                        const st = r.status;
                        const color = st === 'full' ? 'text-green-300' : st === 'canary' ? 'text-amber-300' : st === 'rolled_back' ? 'text-gray-500' : st === 'ready' ? 'text-blue-300' : 'text-gray-400';
                        return (
                          <div key={r.version} className="flex items-center gap-2 flex-wrap">
                            <span className={`font-mono ${color}`}>[{st}] {r.version}</span>
                            <span className="text-gray-600">[{r.module_id}] pass_rate={r.pass_rate_source}</span>
                            <span className="ml-auto flex gap-1">
                              {st === 'ready' && (
                                <button className="text-blue-300 underline" onClick={() => handleReleaseTransition(r.version, 'canary', 10)}>开始金丝雀</button>
                              )}
                              {st === 'canary' && (
                                <>
                                  <span className="text-gray-500">权重 {r.canary_weight || 10}%</span>
                                  {[10, 50, 100].map(w => (
                                    <button key={w} className="text-gray-400 underline"
                                      onClick={() => handleReleaseTransition(r.version, 'canary', w)}>{w}%</button>
                                  ))}
                                  <button className="text-green-300 underline" onClick={() => handleReleaseTransition(r.version, 'full')}>提升全量</button>
                                  <button className="text-red-300 underline" onClick={() => handleReleaseTransition(r.version, 'rollback')}>回滚</button>
                                </>
                              )}
                              {st === 'full' && (
                                <button className="text-red-300 underline" onClick={() => handleReleaseTransition(r.version, 'rollback')}>回滚</button>
                              )}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  <div className="text-[10px] text-gray-500">
                    状态机：ready → canary（金丝雀验证）→ full（全量）→ rolled_back（回滚）；版本历史 append-only，可回退任意版本
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* L2: 导入既有代码（plan-app-factory-l2-import-repo.md §3.4/§3.8/§3.9） */}
        <div className="p-3 rounded border border-purple-500/30 bg-purple-500/5 text-xs space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-purple-300 font-semibold">📥 导入既有代码（L2）</span>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={handleOpenImport}>导入 / 管理</Button>
          </div>
          {l2Stats?.l3_priority_alert && (
            <div className="text-amber-300 text-[10px]">
              📊 全系统跳过测试门禁率 {Math.round((l2Stats.skip_ratio || 0) * 100)}% &gt; 40% — 逃生舱被当常规路径，建议优先规划 L3 增量合并引擎
            </div>
          )}
          {showImportPanel && (
            <div className="space-y-2 pt-2 border-t border-dark-border">
              {/* 红字重写警告（§3.4 三层强制之一） */}
              <div className="p-2 rounded bg-red-500/10 border border-red-500/40 text-red-300 text-[10px] leading-relaxed">
                ⚠️ 当前版本将根据旧代码<strong>【重写】</strong>勾选的文件，而非合并改动。
                请确认已备份，且你接受"该文件整体重生成"的结果。
              </div>
              {/* L3: 修改模式（plan-app-factory-l3 §3.2/§4） */}
              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-gray-400">修改模式：</label>
                <div className="flex gap-2 text-[10px]">
                  <label className={`flex-1 p-1.5 rounded border cursor-pointer ${mergeStrategy === 'full_rewrite' ? 'border-blue-500/60 bg-blue-500/10 text-blue-200' : 'border-dark-border bg-dark-hover text-gray-300'}`}>
                    <input type="radio" name="merge_strategy" className="mr-1"
                      checked={mergeStrategy === 'full_rewrite'}
                      onChange={() => setMergeStrategy('full_rewrite')} />
                    整文件重写（L2，默认）
                  </label>
                  <label className={`flex-1 p-1.5 rounded border cursor-pointer ${mergeStrategy === 'incremental_merge' ? 'border-green-500/60 bg-green-500/10 text-green-200' : 'border-dark-border bg-dark-hover text-gray-300'}`}>
                    <input type="radio" name="merge_strategy" className="mr-1"
                      checked={mergeStrategy === 'incremental_merge'}
                      onChange={() => setMergeStrategy('incremental_merge')} />
                    增量合并（L3）— 改动逐文件审批
                  </label>
                </div>
                {mergeStrategy === 'incremental_merge' && (
                  <div className="text-[10px] text-green-300/80">
                    L3 只重生成受影响文件；构建完成后将生成 diff 预览，需逐文件审批后才应用。
                  </div>
                )}
              </div>
              {/* 上传 zip / 路径 */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-gray-400">上传 zip：</label>
                <input type="file" accept=".zip" onChange={e => setImportZip(e.target.files?.[0] || null)}
                  className="text-[10px] text-gray-300" />
                <label className="text-[10px] text-gray-400">或 AIPLAT_HOME 内路径：</label>
                <input value={importPath} onChange={e => setImportPath(e.target.value)}
                  placeholder="如 ~/.aiplat/legacy_app（仅限 AIPLAT_HOME 内目录）"
                  className="w-full bg-dark-hover border border-dark-border rounded px-2 py-1 text-[10px] font-mono text-gray-200" />
                <Button variant="secondary" size="sm" onClick={handleImportSubmit} loading={importing}>导入</Button>
              </div>
              {/* 文件列表：勾选 + 意图绑定（§3.2/§4） */}
              {importedFiles.length > 0 && (
                <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                  <div className="text-[10px] text-gray-400">
                    共 {importedFiles.length} 个文件 — 勾选并填写"修改意图"（改这个文件干什么），空意图不能提交
                  </div>
                  {!importMeta?.has_tests && (
                    <div className="text-[10px] text-amber-300">⚠️ 未检测到 tests/ 目录，pytest 门禁无法运行。</div>
                  )}
                  {importMeta?.missing_deps?.length ? (
                    <div className="text-[10px] text-amber-300/90">
                      依赖预检：{importMeta.missing_deps.slice(0, 5).join('、')}
                      {importMeta.missing_deps.length > 5 ? ' …' : ''}
                    </div>
                  ) : null}
                  {importedFiles.map(f => (
                    <div key={f.path} className="flex items-start gap-2">
                      <input type="checkbox"
                        checked={!!(selectedIntents[f.path] || '').trim()}
                        onChange={e => setSelectedIntents(prev => ({
                          ...prev, [f.path]: e.target.checked ? (prev[f.path] || '') : '' }))}
                        className="mt-1" />
                      <div className="flex-1 space-y-0.5">
                        <div className="text-[10px] font-mono text-gray-300">
                          {f.path} <span className="text-gray-600">({f.size}B)</span>
                        </div>
                        <input value={selectedIntents[f.path] || ''}
                          onChange={e => setSelectedIntents(prev => ({ ...prev, [f.path]: e.target.value }))}
                          placeholder="修改意图，如：登录增加验证码校验"
                          className="w-full bg-dark-hover border border-dark-border rounded px-2 py-0.5 text-[10px] text-gray-200" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* L3-P1-05: 影响面分析（自动加入文件 + 原因 + 取消二次确认） */}
              {impactAnalysis?.auto_added?.length > 0 && (
                <div className="p-2 rounded bg-purple-500/10 border border-purple-500/30 space-y-1">
                  <div className="text-[10px] text-purple-200">
                    影响面分析：{impactAnalysis.auto_added.length} 个文件被自动加入
                  </div>
                  {impactAnalysis.auto_added.map(f => {
                    const reason = (() => {
                      for (const [main, rels] of Object.entries(impactAnalysis.analysis || {})) {
                        if ((rels as string[]).includes(f)) return `被 ${main} 引用`;
                      }
                      return 'import 关联';
                    })();
                    return (
                      <div key={f} className="flex items-center gap-1.5 text-[10px]">
                        <span className="font-mono text-purple-200/90">{f}</span>
                        <span className="text-gray-500">（{reason}）</span>
                        {!selectedIntents[f]?.trim() && (
                          <button
                            className="ml-auto text-red-300 hover:text-red-200 underline"
                            onClick={() => {
                              if (window.confirm(`取消修改 ${f} 可能导致新代码调用失败（${reason}）。确认取消？`)) {
                                setSelectedIntents(prev => ({ ...prev, [f]: '' }));
                              }
                            }}>
                            取消加入
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {/* 测试门禁逃生（§3.8）：无 tests/ 时才展示 */}
              {importMeta && !importMeta.has_tests && importedFiles.length > 0 && (
                <label className="flex items-center gap-1.5 text-[10px] text-gray-300 cursor-pointer">
                  <input type="checkbox" checked={skipGate} onChange={e => setSkipGate(e.target.checked)} />
                  跳过测试门禁（代码即使跑不通测试也能部署，通过率为估算值）
                </label>
              )}
              {importedFiles.length > 0 && (
                <Button variant="primary" size="sm" onClick={handleApplyModify} loading={savingModify}>
                  保存修改意图并重建
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Actions — show for team_ready / done / failed so user can always rebuild */}
        <div className="flex flex-wrap gap-2">
          {!prdReady && phase === 'dialogue' && teamStages.length === 0 && (
            <Button variant="secondary" size="sm" onClick={handleRecommend} loading={recommending}>AI 推荐团队</Button>
          )}
          {prdReady && phase === 'dialogue' && (
            <Button variant="primary" size="sm" onClick={handleConfirm} loading={starting}>确认需求</Button>
          )}
          {(phase === 'team_ready' || phase === 'done' || phase === 'failed' || phase === 'paused') && (
            <Button variant="primary" size="sm" onClick={handleStart} loading={starting}>{runHistory.length > 0 ? '重新构建' : '启动构建'}</Button>
          )}
        </div>

        {/* Stage Outputs — show architecture/code/test_report when available */}
        {stageOutputs && Object.keys(stageOutputs).length > 0 && (
          <div className="space-y-2">
            {/* ── Stage Artifact Editor ── */}
            {editingStage && (
              <div className="p-3 rounded border border-amber-500/30 bg-amber-500/5 space-y-2">
                <div className="text-xs text-amber-300 flex items-center gap-2">
                  ✏️ 编辑中：{editingStage}
                </div>
                <textarea value={editContent} onChange={e => setEditContent(e.target.value)}
                  className="w-full h-40 text-xs bg-dark-bg border border-dark-border rounded p-2 text-gray-200 font-mono" />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleSaveStageEdit} loading={savingEdit}>保存</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditingStage(null)}>取消</Button>
                  {phase !== 'paused' && (
                    <Button size="sm" variant="secondary" onClick={async () => {
                      await handleSaveStageEdit();
                      if (!project.project_id) return;
                      try {
                        await projectApi.regenerateStage(project.project_id, editingStage, '用户手动编辑后重建');
                        toast.success('已从此阶段重建，下游将自动重跑');
                        setPhase('executing');
                        onRefresh();
                      } catch (e: any) { toastGateError(e, '重建失败'); }
                    }}>保存并从此阶段重建</Button>
                  )}
                </div>
              </div>
            )}
            <h3 className="text-xs font-semibold text-gray-400 uppercase">阶段产出</h3>
            {Object.entries(stageOutputs).map(([key, val]) => {
              const rw = (val as any)?.raw_output || '';
              const elapsed = (val as any)?.elapsed_sec != null ? ((val as any).elapsed_sec as number).toFixed(1) : '';
              // Dynamic label: match output_artifact to team stage's agent_name
              const matchedStage = teamStages.find(s => (s as any).output_artifact === key);
              const agentLabel = (matchedStage as any)?.agent_name || (matchedStage as any)?.display_name || '';
              // Fallback to key-based label if teamStages not available
              const label = agentLabel || {
                architecture: '🏗️ 架构设计', code: '💻 代码生成', test_report: '🧪 测试报告',
                testReport: '🧪 测试报告', prd: '📋 PRD',
              }[key] || key.replace(/[_-]/g, ' ');
              const isHITL = hitlOutputArtifact && key === hitlOutputArtifact;
              let summary = '';

              // ── Structural detection (not key-name matching) ──
              // Helper: extract JSON from mixed text (Markdown + JSON)
              const tryParseJSON = (text: string, marker: string) => {
                const idx = text.indexOf(marker);
                if (idx < 0) return null;
                const jsonStart = Math.max(0, text.lastIndexOf('{', idx) - 500, text.indexOf('{'));
                if (jsonStart < 0) return null;
                const jsonEnd = text.lastIndexOf('}');
                if (jsonEnd <= jsonStart) return null;
                try { return JSON.parse(text.slice(jsonStart, jsonEnd + 1)); }
                catch { return null; }
              };
              // Test report: has pass_rate or test_cases
              if (rw && (val as any).pass_rate != null || /test_cases|test_suites/.test(rw.slice(0, 200))) {
                try {
                  const j = JSON.parse(rw);
                  const cases = j.test_cases || [];
                  if (cases.length > 0) summary = `${cases.length} 个测试用例`;
                } catch { /* raw text, skip */ }
              }
              // Architecture: has components + (api_contracts or api_design)
              if (rw && rw.includes('"components"') && (rw.includes('"api_contracts"') || rw.includes('"api_design"'))) {
                const j = tryParseJSON(rw, '"components"');
                if (j) {
                  const comps = j.components?.length || 0;
                  const apis = j.api_contracts?.length || j.api_design?.length || 0;
                  const db = j.database_schema ? 1 : 0;
                  const hasSec = j.security ? '🔒' : ''; const hasPerf = j.performance ? '⚡' : ''; const hasDeploy = j.deployment ? '🚀' : '';
                  summary = `${comps} 组件 · ${apis} API · DB ${db} ${hasSec}${hasPerf}${hasDeploy}`;
                }
              }
              // PRD: structured JSON with functional_requirements
              if (rw && rw.includes('"functional_requirements"')) {
                const j = tryParseJSON(rw, '"functional_requirements"');
                if (j) {
                  const frs = j.functional_requirements || [];
                  const acs = frs.reduce((sum: number, fr: any) => sum + (fr.acceptance_criteria?.length || 0), 0);
                  const title = (j.title || '').slice(0, 30);
                  const uss = j.user_stories?.length || 0;
                  if (frs.length > 0) summary = `${title} · ${frs.length} FR · ${acs} 验收标准 · ${uss} US`;
                }
              }
              // QA Agent mode: has test_questions (with or without agent_conversation)
              if (rw && rw.includes('"test_questions"')) {
                const j = tryParseJSON(rw, '"test_questions"');
                if (j) {
                  const qs = j.test_questions || [];
                  if (qs.length > 0) {
                    // Only count FRs when test_questions are objects with ac_ref
                    if (typeof qs[0] === 'object') {
                      const coveredFRs = new Set(qs.map((q: any) => {
                        const parts = (q.ac_ref || '').split('-');
                        return parts.length >= 2 ? parts.slice(0, 2).join('-') : q.ac_ref || '';
                      })).size;
                      summary = `${qs.length} 条对话测试 · 覆盖 ${coveredFRs} 个FR`;
                    } else {
                      summary = `${qs.length} 条对话测试`;
                    }
                  }
                }
              }
              // Code: count ## FILE: blocks
              if (rw && rw.includes('## FILE:')) {
                const files = (rw.match(/## FILE:/g) || []).length;
                if (files > 0) summary = `${files} 个代码文件`;
              }

              const preview = rw ? (typeof rw === 'string' ? rw.slice(0, 2000) : JSON.stringify(rw).slice(0, 2000)) : '';
              const qaParsed = (rw && rw.includes('"test_questions"')) ? tryParseJSON(rw, '"test_questions"') : null;
              const testReportParsed = (() => {
                if (!rw || !(rw.includes('"test_results"') || rw.includes('"bug_summary"'))) return null;
                try { return JSON.parse(rw); } catch {}
                // Fallback: extract JSON from markdown-wrapped text
                const jStart = rw.indexOf('{');
                const jEnd = rw.lastIndexOf('}');
                if (jStart >= 0 && jEnd > jStart) {
                  try { return JSON.parse(rw.slice(jStart, jEnd + 1)); } catch {}
                }
                return null;
              })();
              const bugCount = testReportParsed?.bug_summary?.total_bugs || testReportParsed?.bug_summary?.bugs?.length || 0;

              return (
                <React.Fragment key={key}>
                  <details className="text-xs rounded border border-dark-border bg-dark-hover/30">
                  <summary className="p-2 cursor-pointer text-gray-300 font-medium flex items-center justify-between">
                    <span>{label} ({typeof rw === 'string' ? rw.length : 0} 字符{elapsed ? ` · ⏱ ${elapsed}s` : ''}{summary ? ' · ' + summary : ''})</span>
                    <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                      {bugCount > 0 && (
                        <button onClick={e => { e.preventDefault(); handleFixBugs(); }}
                          disabled={fixingBugs}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 hover:text-blue-200 transition-colors">
                          {fixingBugs ? <Loader2 className="w-3 h-3 animate-spin inline mr-0.5" /> : <Wrench className="w-3 h-3 inline mr-0.5" />}
                          一键修复 ({bugCount} Bug)
                        </button>
                      )}
                      {rw && (
                        <button onClick={e => { e.preventDefault(); setFullscreenTitle(label); setFullscreenContent(typeof rw === 'string' ? rw : JSON.stringify(rw, null, 2)); }}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-500 hover:text-gray-300 hover:bg-primary/20 transition-colors">
                          🔍 全屏
                        </button>
                      )}
                      {(phase === 'done' || phase === 'paused') && rw && (
                        <button onClick={e => { e.preventDefault(); handleEditStage(key, rw); }}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-500 hover:text-yellow-400 transition-colors">
                          ✏️ 编辑
                        </button>
                      )}
                      {isHITL && (phase === 'paused' || phase?.includes('approval')) && (
                        <>
                          <button onClick={e => { e.preventDefault(); handleApprove(); }}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-300 hover:bg-green-500/30 hover:text-green-200 transition-colors">
                            ✅ 审批通过
                          </button>
                          <button onClick={e => { e.preventDefault(); handleReject(); }}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 hover:bg-red-500/30 hover:text-red-200 transition-colors">
                            ❌ 驳回重做
                          </button>
                        </>
                      )}
                    </div>
                  </summary>
                  <div className="p-2 max-h-72 overflow-y-auto border-t border-dark-border text-gray-300 text-xs max-w-none">
                    {qaParsed ? (
                      <table className="w-full text-[10px] border-collapse">
                        <thead><tr className="text-gray-400 text-left"><th className="p-1">ID</th><th className="p-1 w-[52px]">分类</th><th className="p-1">问题</th><th className="p-1 hidden sm:table-cell">期望</th></tr></thead>
                        <tbody>
                          {(qaParsed.test_questions || []).slice(0, 10).map((q: any) => (
                            <tr key={q.id} className="border-t border-gray-700/50 hover:bg-gray-800/30">
                              <td className="p-1 text-gray-500">{q.id}</td>
                              <td className="p-1"><span className={`px-1 rounded text-[9px] ${q.category==='happy_path'?'bg-green-900/50 text-green-400':q.category==='exception'?'bg-red-900/50 text-red-400':'bg-amber-900/50 text-amber-400'}`}>{q.category==='happy_path'?'正常':q.category==='exception'?'异常':'边界'}</span></td>
                              <td className="p-1 max-w-[200px] truncate">{q.question}</td>
                              <td className="p-1 max-w-[180px] truncate text-gray-500 hidden sm:table-cell">{q.min_expectation}</td>
                            </tr>
                          ))}
                        </tbody>
                        {qaParsed.test_questions?.length > 10 && <tfoot><tr><td colSpan={4} className="p-1 text-[10px] text-gray-500 text-center">... 共 {qaParsed.test_questions.length} 条 · 点 🔍 全屏 查看完整表格</td></tr></tfoot>}
                      </table>
                    ) : preview ? (
                      rw.includes('## FILE:') ? (
                        <div className="border border-gray-700 rounded overflow-hidden">
                          <div className="flex items-center gap-1.5 px-2 py-1 bg-gray-800 text-[10px] text-gray-300">
                            <FileText className="w-3 h-3" /> {(rw.match(/## FILE:/g) || []).length} 个文件
                          </div>
                          <pre className="p-2 text-xs text-gray-100 bg-gray-900 font-mono whitespace-pre-wrap break-all max-h-72 overflow-y-auto">{preview}</pre>
                        </div>
                      ) : rw.trimStart().startsWith('{') ? (
                        (() => {
                          let parsedInline: any = null;
                          try { parsedInline = JSON.parse(rw); } catch { parsedInline = tryParseJSON(rw, '"components"'); }
                          // test_report: structured JSON with test_results and bug_summary
                          if (parsedInline?.test_results && parsedInline?.header) {
                            const tr = parsedInline;
                            const passed = tr.meta?.passed || 0;
                            const failed = tr.meta?.failed || 0;
                            const bugs = tr.bug_summary?.total_bugs ?? tr.bug_summary?.bugs?.length ?? 0;
                            const rate = tr.meta?.pass_rate ?? 0;
                            const rec = tr.recommendation || '';
                            const recLabel: Record<string,string> = { CONDITIONAL_APPROVAL: '有条件通过', APPROVED: '已通过', REJECTED: '已拒绝' };
                            return (
                              <div className="space-y-2">
                                <div className="flex items-center gap-3 text-[10px]">
                                  <span className="text-green-400">✅ {passed} 通过</span>
                                  {failed > 0 && <span className="text-red-400">❌ {failed} 失败</span>}
                                  {bugs > 0 && <span className="text-amber-400">🐛 {bugs} 个 Bug</span>}
                                  <span className="text-blue-400">通过率 {rate}%</span>
                                  <span className="text-gray-500">|</span>
                                  <span className="text-gray-400">{recLabel[rec] || rec}</span>
                                </div>
                                {Array.isArray(tr.test_results) && tr.test_results.find((r: any) => r.is_bug) && (
                                  <div className="text-[10px] text-red-400">
                                    发现 Bug: {tr.test_results.filter((r: any) => r.is_bug).map((r: any, i: number) => (
                                      <span key={i} className="inline-block mr-1.5">{r.id}: {r.reason?.slice(0, 50)}</span>
                                    ))?.slice?.(0, 3)}
                                  </div>
                                )}
                              </div>
                            );
                          }
                          return parsedInline?.components ? (
                            <table className="w-full text-[10px] border-collapse">
                              <thead><tr className="text-gray-400 text-left">
                                <th className="p-1">组件</th><th className="p-1 w-[50px]">层级</th><th className="p-1 w-[70px]">技术栈</th>
                              </tr></thead>
                              <tbody>
                                {(parsedInline.components || []).slice(0, 5).map((c: any, i: number) => (
                                  <tr key={i} className="border-t border-gray-700/50">
                                    <td className="p-1 font-medium">{c.name}</td>
                                    <td className="p-1"><span className="px-1 rounded text-[9px] bg-gray-700 text-gray-300">{c.layer}</span></td>
                                    <td className="p-1 text-gray-500 max-w-[100px] truncate">{c.tech}</td>
                                  </tr>
                                ))}
                              </tbody>
                              {parsedInline.components.length > 5 && (
                                <tfoot><tr><td colSpan={3} className="p-1 text-[10px] text-gray-500 text-center">
                                  共 {parsedInline.components.length} 个组件 · {parsedInline.api_design?.length || 0} 个 API · 点 🔍 全屏查看完整设计
                                </td></tr></tfoot>
                              )}
                            </table>
                          ) : (
                            <div className="text-[10px] text-gray-400 p-1">
                              {summary || 'JSON 格式有误'} · 点 🔍 全屏 查看原始内容
                            </div>
                          );
                        })()
                      ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-invert prose-xs max-w-none">{preview}</ReactMarkdown>
                      )
                    ) : '(空)'}
                  </div>
                </details>
                </React.Fragment>
              );
            })}
            {/* Aggregate test results — shown at end, not inline per-stage */}
            {(() => {
              for (const [key, val] of Object.entries(stageOutputs)) {
                const tr = (val as any)?.test_results;
                if (tr && (tr.passed != null || tr.failed != null || tr.errors != null)) {
                  const p = tr.passed || 0; const f = tr.failed || 0; const e = tr.errors || 0;
                  const total = p + f + e; const rate = total > 0 ? p / total : 0;
                  const testColor = rate >= 0.8 ? 'text-green-400 bg-green-500/10 border-green-500/30' : rate > 0 ? 'text-amber-400 bg-amber-500/10 border-amber-500/30' : 'text-red-400 bg-red-500/10 border-red-500/30';
                  return (
                    <div key="test-results" className={`rounded border p-2 text-xs ${testColor}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold">🧪 测试结果</span>
                        <span className="ml-auto font-bold">{(rate * 100).toFixed(0)}%</span>
                      </div>
                      <div className="flex gap-3">
                        <span>✅ {p} 通过</span>
                        <span>❌ {f} 失败</span>
                        <span>⚠️ {e} 错误</span>
                      </div>
                    </div>
                  );
                }
              }
              return null;
            })()}
          </div>
        )}

        {/* Chat */}
        <Card>
          <CardContent className="p-0">
            <InlineChat
              projectId={project.project_id}
              initialMessage={!prdReady ? project.description : undefined}
              onPhaseChange={(p) => { if (p === 'prd_ready') setPrdReady(true); }}
              agentMode={agentMode}
              agentName={agentName}
            />
          </CardContent>
        </Card>

        {/* Run history */}
        {runHistory.length > 0 && (
          <details className="text-xs">
            <summary className="text-gray-500 cursor-pointer">运行历史 ({runHistory.length})</summary>
            <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
              {runHistory.slice(-5).reverse().map((r, i) => (
                <div key={i} className="flex justify-between p-1.5 rounded bg-dark-hover/30">
                  <span className="text-gray-400">{r.started_at?.slice(0, 16)}</span>
                  <span className={r.pass_rate >= 0.8 ? 'text-green-400' : 'text-yellow-400'}>通过率 {(r.pass_rate * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
      <FullscreenView
        open={!!fullscreenContent}
        title={fullscreenTitle}
        content={fullscreenContent}
        onClose={() => { setFullscreenContent(''); setFullscreenTitle(''); }}
      />

      {/* L2: 《预期管理手册》弹窗（§3.9 条件 1 — 首次导入必读，同意才能继续） */}
      {showManualModal && (
        <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4"
          onClick={() => { setManualAgreed(false); setShowManualModal(false); setShowImportPanel(false); }}>
          <div className="bg-dark-card border border-dark-border rounded-lg max-w-2xl max-h-[80vh] overflow-y-auto p-5 text-xs space-y-3"
            onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-bold text-gray-100">📘 应用工厂 L2 代码导入模式 — 用户预期管理手册（必读）</h3>
            <div className="text-gray-300 space-y-2 text-[11px] leading-relaxed">
              <p><b className="text-red-300">一句话核心认知：</b>L2 不是"找茬修改器"，而是"整体重铸机"。
                你的旧代码是<b>原料</b>不是<b>地基</b>——AI 会把整块铁熔了按新需求重铸一把新剑，而不是在旧剑上焊个新把手。</p>
              <p>⚠️ <b>重写 ≠ 合并</b>：勾选的文件会被<b>整体重写</b>（不是"在第 100 行插 5 行"）。
                对外接口（函数名/类名/API 路由路径）会被强制保留，但内部特殊边界处理、性能 Hack、隐式全局变量可能被标准写法替换。</p>
              <p>⚠️ <b>"保持风格"是玄学</b>：最终代码看起来会像"AI 写的，但套了你原来的函数名"。生僻写法（元类/装饰器嵌套/猴子补丁）大概率被重写。</p>
              <p>⚠️ <b>无测试门禁可能失效</b>：老项目无 tests/ 时可跳过测试门禁——代码即使跑不通测试也能部署（通过率为估算值，非实测）。
                <b className="text-amber-300">登录/支付/权限类变更强烈建议不要跳过，自行手动测一遍。</b></p>
              <p>✅ <b>后悔药只有一颗</b>：不满意 → 「回滚 PRD」→ 从 imported/ 备份目录找回原件 → 重新勾选重写。
                试错成本 = 一次生成的时间，不要在生成结果上打补丁。</p>
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="primary" size="sm" onClick={() => { setManualAgreed(true); setShowManualModal(false); }}>
                同意以上规则，点击继续
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setManualAgreed(false); setShowManualModal(false); setShowImportPanel(false); }}>
                退出此功能
              </Button>
            </div>
          </div>
        </div>
      )}
      {/* L3: 合并审批界面（plan-app-factory-l3 §3.5/§4） */}
      {showMergeReview && (
        <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4"
          onClick={() => setShowMergeReview(false)}>
          <div className="bg-dark-card border border-dark-border rounded-lg max-w-3xl max-h-[85vh] overflow-y-auto p-5 text-xs space-y-3 w-full"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-100">🔀 合并审批（L3 增量模式）</h3>
              <Button variant="ghost" size="sm" onClick={() => setShowMergeReview(false)}>✕</Button>
            </div>
            {/* 影响面分析（§3.3） */}
            {mergeImpact?.auto_added?.length > 0 && (
              <div className="p-2 rounded bg-purple-500/10 border border-purple-500/30 text-[10px] text-purple-200">
                影响面分析：自动加入 {mergeImpact.auto_added.length} 个文件
                （{mergeImpact.auto_added.join('、')}）— 仅供参考，可在下方逐文件驳回
              </div>
            )}
            {/* L4 v1.5: 跨模块契约状态 */}
            {mergeCrossContracts && (
              mergeCrossContracts.broken?.length > 0 ? (
                <div className="p-2 rounded bg-red-500/10 border border-red-500/50 text-[10px] text-red-300 space-y-0.5">
                  <div className="font-semibold">⛔ 跨模块契约断裂 — 合并将被阻断（L4 v1.5 门禁）</div>
                  {mergeCrossContracts.broken.map((b: any, i: number) => (
                    <div key={i}>· {b.detail}</div>
                  ))}
                  <div className="text-red-300/70">请修复变更模块的对外接口后重新生成。</div>
                </div>
              ) : (
                <div className="p-2 rounded bg-green-500/10 border border-green-500/30 text-[10px] text-green-300">
                  ✓ 跨模块契约通过（依赖方引用的 {mergeCrossContracts.checked?.length || 0} 处端点/实体在新版本中存活）
                </div>
              )
            )}
            {/* 逐文件 diff 审批 */}
            {mergePreviews.length === 0 && (
              <div className="text-gray-400 text-[11px] py-4 text-center">无合并预览（流水线未产出新版本）</div>
            )}
            <div className="space-y-3">
              {mergePreviews.map(pv => {
                const approved = mergeDecisions[pv.path] === 'approved';
                const rejected = mergeDecisions[pv.path] === 'rejected';
                const syntaxOk = pv.syntax?.ok !== false;
                const interfaceOk = pv.interface?.ok !== false;
                const blocked = !syntaxOk || !interfaceOk;
                return (
                  <div key={pv.path} className={`rounded border p-2 ${blocked ? 'border-red-500/50 bg-red-500/5' : approved ? 'border-green-500/40 bg-green-500/5' : rejected ? 'border-gray-600 bg-dark-hover' : 'border-dark-border'}`}>
                    {/* P0-03: 确定性门禁阻断横幅 */}
                    {blocked && (
                      <div className="mb-1.5 p-1.5 rounded bg-red-500/15 border border-red-500/50 text-[10px] text-red-300">
                        ⛔ 确定性门禁阻断：{!syntaxOk ? `语法错误（${pv.syntax?.error}）` : ''}
                        {!interfaceOk ? `对外接口缺失（${(pv.interface?.missing || []).join(', ')}）` : ''}
                        — 该文件禁止通过，只能驳回
                      </div>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-[11px] text-gray-200">{pv.path}</span>
                      <span className="text-[10px] text-gray-500">
                        +{pv.changed_lines}/-{pv.unchanged_lines} 行
                      </span>
                      {!syntaxOk && <span className="text-[10px] text-red-400">❌ 语法: {pv.syntax?.error}</span>}
                      {!interfaceOk && (
                        <span className="text-[10px] text-red-400">
                          ❌ 接口缺失: {(pv.interface?.missing || []).join(', ')}
                        </span>
                      )}
                      <div className="ml-auto flex gap-1">
                        <Button variant="ghost" size="sm"
                          className={rejected ? '!bg-gray-600/40' : ''}
                          onClick={() => handleToggleMergeDecision(pv.path, 'rejected')}>驳回</Button>
                        <Button variant="primary" size="sm"
                          disabled={blocked}
                          className={approved ? '!bg-green-600/50' : ''}
                          onClick={() => handleToggleMergeDecision(pv.path, 'approved')}>
                          {approved ? '已通过 ✓' : '通过'}
                        </Button>
                      </div>
                    </div>
                    {/* diff 内容 — P1-04: formatting hunks folded by default */}
                    <pre className="mt-1.5 max-h-44 overflow-auto bg-black/40 rounded p-2 text-[10px] font-mono leading-tight">
                      {(pv.hunks || []).filter((h: any) => showFormatting || h.category !== 'formatting').map((h: any, i: number) => (
                        <div key={i}>
                          <div className={`${h.category === 'formatting' ? 'text-gray-500 italic' : 'text-blue-400'}`}>
                            {h.header}{h.category === 'formatting' ? '（格式噪音）' : ''}
                          </div>
                          {h.lines.map((l: string, j: number) => (
                            <div key={j} className={l.startsWith('+') ? 'text-green-400' : l.startsWith('-') ? 'text-red-400' : 'text-gray-500'}>{l}</div>
                          ))}
                        </div>
                      ))}
                      {!pv.hunks?.length && <div className="text-gray-600">（无 diff 内容）</div>}
                      {pv.logic_changes === 0 && pv.changed_lines > 0 && (
                        <div className="text-gray-600 mt-1">仅格式变动（空格/缩进/空行）</div>
                      )}
                    </pre>
                  </div>
                );
              })}
            </div>
            {mergePreviews.length > 0 && (
              <div className="flex gap-2 pt-2 border-t border-dark-border items-center">
                <label className="flex items-center gap-1 text-[10px] text-gray-400 cursor-pointer">
                  <input type="checkbox" checked={showFormatting} onChange={e => setShowFormatting(e.target.checked)} />
                  显示格式噪音
                </label>
                {mergePreviews.some(p => mergeDecisions[p.path] === 'rejected') ? (
                  <Button variant="secondary" size="sm" onClick={handleRegenerateAfterReject}>
                    ♻️ 驳回文件需重新生成（全部文件）
                  </Button>
                ) : (
                  <Button variant="primary" size="sm" onClick={handleApplyMerge} loading={applyingMerge}
                    disabled={!mergePreviews.every(p => mergeDecisions[p.path] === 'approved')}>
                    应用合并（{mergePreviews.filter(p => mergeDecisions[p.path] === 'approved').length}/{mergePreviews.length} 已通过）
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => { setMergeDecisions({}); setShowMergeReview(false); }}>取消</Button>
                <span className="ml-auto text-[10px] text-gray-500">原子化：全部通过才应用；驳回 → 重新生成</span>
              </div>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
};

// ── Main Factory Page ──
const FactoryPage: React.FC = () => {
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [deployedApps, setDeployedApps] = useState<any[]>([]);
	const [loadingApps, setLoadingApps] = useState(true);
	const [projectStates, setProjectStates] = useState<Record<string, string>>({});
	const [projectPassRates, setProjectPassRates] = useState<Record<string, number>>({});
	const [desc, setDesc] = useState('');
	const [appName, setAppName] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedProject, setSelectedProject] = useState<ProjectItem | null>(null);
  const [selectedApp, setSelectedApp] = useState<string>('');

  const loadAll = useCallback(async () => {
    setLoadingApps(true);
    try {
      const p = await projectApi.list();
	      if (p?.projects) {
	        setProjects(p.projects);
	        // ── v3.1: fetch real-time pipeline phase from Core ──
	        const states: Record<string, string> = {};
	        const rates: Record<string, number> = {};
	        await Promise.all(p.projects.map(async (prj: ProjectItem) => {
	          try {
	            const st = await projectApi.getState(prj.project_id);
            const phase = (st as any)?.state?.phase || (st as any)?.phase || '';
            states[prj.project_id] = phase; // always set, even if empty (frontend handles 'loading')
	            const tr = (st as any)?.state?.test_report;
	            if (tr?.raw_output) {
	              try {
	                const trj = JSON.parse(tr.raw_output);
	                if (trj.meta?.pass_rate != null) rates[prj.project_id] = trj.meta.pass_rate;
	              } catch {}
	            }
	          } catch { /* skip */ }
	        }));
	        setProjectStates(states);
	        if (Object.keys(rates).length > 0) setProjectPassRates(rates);
	      }
    } catch { /* keep existing state, retry on next loadAll */ }
    try {
      const r = await fetch('/api/platform/apps');
      const d = await r.json();
      if (d?.apps) setDeployedApps(d.apps);
    } catch { /* keep existing state */ }
    setLoadingApps(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  // P2-4: 向数字人上报应用工厂实时状态（项目数/阶段/通过率/选中项目）
  useEffect(() => {
    const stageCount: Record<string, number> = {};
    Object.values(projectStates).forEach((ph: string) => {
      const key = ph || 'unknown';
      stageCount[key] = (stageCount[key] || 0) + 1;
    });
    const runningCount = Object.values(projectStates).filter(ph => ['executing', 'running', 'pending'].includes(ph)).length;
    const doneCount = Object.values(projectStates).filter(ph => ['done', 'completed'].includes(ph)).length;
    const avgPassRate = Object.values(projectPassRates).length
      ? Math.round(Object.values(projectPassRates).reduce((a, b) => a + (b || 0), 0) / Object.values(projectPassRates).length * 100) / 100
      : undefined;
    reportPageData('/app/factory', {
      projectCount: projects.length,
      deployedAppCount: deployedApps.length,
      stageCount,
      running: runningCount,
      done: doneCount,
      avgPassRate,
      selectedProject: selectedProject?.name || undefined,
      selectedProjectPhase: selectedProject ? (projectStates[selectedProject.project_id] || undefined) : undefined,
    });
    return () => clearPageData('/app/factory');
  }, [projects, deployedApps, projectStates, projectPassRates, selectedProject]);

  const create = async () => {
    if (!desc.trim()) { toast.warning('请输入应用描述'); return; }
    setCreating(true);
    try {
      const project = await projectApi.create({ name: desc.trim().slice(0, 30) || '新项目', description: desc.trim(), app_name: appName.trim() || undefined });
      setDesc('');
      setAppName('');
      toast.success('项目已创建');
      setSelectedProject(project);
      loadAll();
    } catch (e) { toastGateError(e, '创建失败'); }
    finally { setCreating(false); }
  };

  const handleDelete = async (e: React.MouseEvent, project: ProjectItem) => {
    e.stopPropagation();
    if (!confirm(`确定要删除「${project.name}」吗？此操作不可撤销。`)) return;
    try {
      await projectApi.delete(project.project_id);
      toast.success('项目已删除');
      if (selectedProject?.project_id === project.project_id) setSelectedProject(null);
      loadAll();
    } catch (err) { toastGateError(err, '删除失败'); }
  };

  const getStatus = (p: ProjectItem) => {
    const realPhase = projectStates[p.project_id];
    const phase = realPhase; // No fallback to old runs[].phase — state endpoint is authoritative
    if (!phase) return { label: '获取中...', color: 'text-gray-500', bg: 'bg-gray-500/10', phase: 'loading' };
    if (phase === 'done') return { label: '已完成', color: 'text-green-400', bg: 'bg-green-500/10', phase: 'done' };
    if (phase === 'expired') return { label: '已过期', color: 'text-gray-400', bg: 'bg-gray-500/10', phase: 'expired' };
    if (phase === 'failed') return { label: '失败', color: 'text-red-400', bg: 'bg-red-500/10', phase: 'failed' };
    if (phase === 'paused') return { label: '等待审批', color: 'text-amber-400', bg: 'bg-amber-500/10', phase: 'paused' };
    if (phase === 'pending') return { label: '已中断', color: 'text-amber-400', bg: 'bg-amber-500/10', phase: 'failed' };
    return { label: '构建中', color: 'text-blue-400', bg: 'bg-blue-500/10', phase: 'executing' };
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* ── Create Section ── */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card border border-dark-border rounded-xl p-5">
        <h2 className="text-lg font-bold text-gray-100 mb-3">新建应用
          <a href="/docs?path=design/ai-app-factory.md" target="_blank" className="ml-2 text-xs text-gray-500 hover:text-primary font-normal underline underline-offset-2">
            📖 设计文档
          </a>
        </h2>
        <p className="text-sm text-gray-400 mb-3">用自然语言描述你想要构建的应用，AI 将自动完成需求分析、架构设计和代码生成</p>
        <Textarea
          value={desc}
          onChange={e => setDesc(e.target.value)}
          placeholder="例如：构建一个视频解析平台，支持上传、转码、AI 摘要生成..."
          rows={3}
          className="mb-3"
        />
        <input
          value={appName}
          onChange={e => setAppName(e.target.value)}
          placeholder="应用英文名（可选，如 video_parser）"
          className="mb-3 w-full bg-dark-bg border border-dark-border rounded-lg px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500/50"
        />
        <Button variant="primary" onClick={create} loading={creating} icon={<Plus className="w-4 h-4" />}>
          开始构建
        </Button>
      </motion.div>

      {/* ── Projects + Apps Grid ── */}
      <div>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
          我的应用 ({projects.length + deployedApps.length})
          {projects.length > 0 && (
            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (!confirm(`确定要删除全部 ${projects.length} 个项目吗？此操作不可撤销。`)) return;
                try {
                  await projectApi.batchDelete({ project_ids: projects.map(p => p.project_id) });
                  toast.success(`已删除 ${projects.length} 个项目`);
                  setSelectedProject(null);
                  loadAll();
                } catch (err) { toastGateError(err, '批量删除失败'); }
              }}
              className="ml-2 text-[10px] text-red-400 hover:text-red-300 hover:underline transition-colors"
            >
              全部清空
            </button>
          )}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {/* Projects */}
          {projects.map(p => {
            const status = getStatus(p);
            const lastRun = p.runs?.[p.runs.length - 1];
            const passRate = projectPassRates[p.project_id] ?? lastRun?.pass_rate ?? 0;
            const hasPrd = !!(p as any).confirmed_prd;
            return (
              <motion.div
                key={p.project_id} layout
                whileHover={{ y: -1 }}
                className="rounded-lg border border-dark-border bg-dark-card p-4 cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => setSelectedProject(p)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h4 className="text-sm font-medium text-gray-100 truncate max-w-[200px]">{p.name}</h4>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={e => handleDelete(e, p)}
                      className="p-1 rounded hover:bg-red-500/20 text-gray-600 hover:text-red-400 transition-colors"
                      title="删除项目"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${status.bg} ${status.color}`}>{status.label}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-500 line-clamp-2 mb-2">{p.description}</p>
                <div className="flex items-center gap-2 text-[10px] text-gray-600 mb-2">
                  <Clock className="w-3 h-3" />
                  <span>{p.created_at?.slice(0, 10)}</span>
                  {p.runs?.length ? <span>· {p.runs.length} 次运行</span> : null}
                </div>

                {/* ── Phase-dependent footer ── */}
                {status.phase === 'dialogue' && (
                  <div className="flex items-center gap-2 pt-2 border-t border-dark-border">
                    {hasPrd ? (
                      <>
                        <span className="text-[10px] text-green-400 flex items-center gap-1"><CheckCircle className="w-3 h-3" />PRD 就绪</span>
                        <button onClick={async (e) => { e.stopPropagation(); setSelectedProject(p); }} className="ml-auto text-[10px] px-2 py-1 rounded bg-primary/20 text-primary hover:bg-primary/30 transition-colors">查看详情</button>
                      </>
                    ) : (
                      <span className="text-[10px] text-gray-500 flex items-center gap-1"><Clock className="w-3 h-3" />需要完成PM对话</span>
                    )}
                  </div>
                )}
                {status.phase === 'executing' && (
                  <div className="pt-2 border-t border-dark-border space-y-1">
                    <div className="h-1 bg-gray-700 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: '45%' }} />
                    </div>
                    <span className="text-[10px] text-blue-400">构建中...</span>
                  </div>
                )}
                {status.phase === 'done' && (
                  <div className="flex items-center gap-2 pt-2 border-t border-dark-border">
                    <span className="text-[10px] text-green-400 flex items-center gap-1">
                       <CheckCircle className="w-3 h-3" />通过率 {passRate.toFixed(0)}%
                    </span>
                    <button onClick={async (e) => { e.stopPropagation();
                      try { const r = await projectApi.deployToApp(p.project_id); setSelectedApp((r as any)?.app_url || ''); } catch {} }}
                      className="ml-auto text-[10px] px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors flex items-center gap-1">
                      <ExternalLink className="w-3 h-3" />预览
                    </button>
                  </div>
                )}
                {status.phase === 'failed' && (
                  <div className="flex items-center gap-2 pt-2 border-t border-dark-border">
                    <span className="text-[10px] text-red-400 flex items-center gap-1"><XCircle className="w-3 h-3" />{lastRun?.error?.slice(0, 30) || '执行失败'}</span>
                  </div>
                )}
                {status.phase === 'paused' && (
                  <div className="flex items-center gap-2 pt-2 border-t border-dark-border">
                    <span className="text-[10px] text-amber-400 flex items-center gap-1"><Clock className="w-3 h-3" />等待审批</span>
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await projectApi.rebuild(p.project_id);
                          toast.success('重建已触发');
                          loadAll();
                        } catch (err) { toastGateError(err, '重建失败'); }
                      }}
                      className="ml-auto text-[10px] px-2 py-1 rounded bg-primary/20 text-primary hover:bg-primary/30 transition-colors"
                    >
                      🔄 重新构建
                    </button>
                  </div>
                )}
              </motion.div>
            );
          })}

          {/* Deployed Apps */}
          {deployedApps.map((a: any) => (
            <motion.div
              key={a.id || a.app_id}
              layout
              whileHover={{ y: -1 }}
              className="rounded-lg border border-green-500/30 bg-green-500/5 p-4 cursor-pointer hover:border-green-400/50 transition-colors"
              onClick={() => {
                const pid = (a.id || a.app_id || '').replace('factory_', '');
                setSelectedApp(a.app_url || `/app/sessions/${pid}`);
              }}
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="text-sm font-medium text-gray-100 truncate">{a.name || a.app_id}</h4>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-400">✅ 已部署</span>
              </div>
              <p className="text-xs text-gray-500 line-clamp-2 mb-2">{a.description || a.mode || '已部署应用'}</p>
              <div className="flex items-center gap-1 text-[10px] text-green-400">
                <ExternalLink className="w-3 h-3" /> 打开预览
              </div>
            </motion.div>
          ))}
        </div>

        {projects.length === 0 && deployedApps.length === 0 && !loadingApps && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg mb-2">还没有应用</p>
            <p className="text-sm">在上方输入需求描述，开始构建你的第一个应用</p>
          </div>
        )}
        {loadingApps && projects.length === 0 && deployedApps.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <Loader2 className="w-6 h-6 animate-spin mx-auto mb-3" />
            <p className="text-sm">加载中...</p>
          </div>
        )}
        </div>

      {/* ── Project Detail Panel ── */}
      {selectedProject && (
        <ProjectPanel
          project={selectedProject}
          onClose={() => setSelectedProject(null)}
          onRefresh={loadAll}
        />
      )}

      {/* ── Deployed App Preview ── */}
      {selectedApp && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setSelectedApp('')}>
          <div className="bg-dark-card border border-dark-border rounded-xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-3 border-b border-dark-border">
              <span className="text-sm text-gray-300">应用预览</span>
              <div className="flex gap-2">
                <a href={selectedApp} target="_blank" rel="noreferrer" className="text-xs text-primary flex items-center gap-1"><ExternalLink className="w-3 h-3" />新窗口打开</a>
                <Button variant="ghost" size="sm" onClick={() => setSelectedApp('')}>✕</Button>
              </div>
            </div>
            <iframe src={selectedApp} className="flex-1 border-0" title="应用预览" />
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default FactoryPage;
