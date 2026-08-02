import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Send, Loader2, Clock, CheckCircle, XCircle, ExternalLink, BarChart3, Trash2, Play, RefreshCw, FileText } from 'lucide-react';
import { projectApi, builderTeamApi, type ProjectItem, type ProjectRun } from '../../../services';
import { Card, CardContent, Button, Textarea, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';
import type { BuilderSession } from '../../../services';

// ── Simple inline chat (replaces crashing ChatWidget) ──
const InlineChat: React.FC<{
  projectId: string;
  initialMessage?: string;
  onPhaseChange?: (phase: string) => void;
}> = ({ projectId, initialMessage, onPhaseChange }) => {
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

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = () => { const m = input.trim(); if (m) { setInput(''); send(m); } };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[200px] max-h-[400px]">
        {messages.map((m, i) => (
          <div key={i} className={`p-2 rounded text-sm ${m.role === 'assistant' ? 'bg-primary/10 border border-primary/20 text-gray-200' : 'bg-dark-card border border-dark-border text-gray-300'}`}>
             <div className="text-[10px] text-gray-500 mb-1">{m.role === 'assistant' ? (agentMode ? agentName : 'AI PM') : '你'}</div>
            <div className="whitespace-pre-wrap break-words">{m.content}</div>
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
    title_field: "title", overview_field: "overview", scope_badge: "scope",
    tables: [{ key: "user_stories", title: "用户故事", columns: [
      { key: "id", label: "ID", width: "140px" }, { key: "description", label: "描述" },
      { key: "priority", label: "优先级", type: "badge" }, { key: "acceptance_criteria", label: "验收标准", type: "ac_list" },
    ]}],
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
};

const formatBadge = (v: string, type: string) => {
  if (type === 'risk' || type === 'badge') {
    const low = (v || '').toLowerCase();
    const color = low === 'high' ? 'bg-red-100 text-red-700' : low === 'medium' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600';
    return <span className={`px-1.5 py-0.5 rounded text-[10px] ${color}`}>{v}</span>;
  }
  if (type === 'method_badge') {
    const colors: Record<string,string>={GET:'bg-blue-100 text-blue-700',POST:'bg-green-100 text-green-700',PUT:'bg-amber-100 text-amber-700',DELETE:'bg-red-100 text-red-700'};
    return <span className={`px-1 rounded text-[10px] font-mono ${colors[v]||'bg-gray-100 text-gray-600'}`}>{v}</span>;
  }
  if (type === 'ac_list' && Array.isArray(v)) return <>{v.map((a:string,i:number)=><div key={i} className="text-[11px] text-gray-500">· {a}</div>)}</>;
  if (type === 'code') return <pre className="text-xs text-gray-600 font-mono whitespace-pre-wrap">{v}</pre>;
  return <>{v}</>;
};

// ── Generic DataDocument — schema-driven renderer ──
const DataDocument: React.FC<{ data: Record<string, unknown>; schema: DocSchema }> = ({ data, schema }) => {
  const title = (schema.title_field ? data[schema.title_field] : schema.title) as string || '';
  const overview = schema.overview_field ? (data[schema.overview_field] as string) : '';
  const scope = schema.scope_badge ? (data[schema.scope_badge] as string) : '';
  return (
    <div className="space-y-5 text-sm text-gray-800">
      {title && <div><h1 className="text-xl font-bold text-gray-900 mb-1">{title}</h1>{scope && <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">{scope}</span>}</div>}
      {overview && <p className="text-gray-600 leading-relaxed">{overview}</p>}
      {(schema.tables || []).map((t: TableDef) => {
        const rows = (data[t.key] || []) as any[];
        if (!rows.length) return null;
        return <div key={t.key}><h2 className="text-base font-semibold text-gray-900 mb-2 border-b pb-1">{t.title} ({rows.length})</h2>
          <table className="w-full text-xs border-collapse"><thead><tr className="bg-gray-50">{t.columns.map((c: ColDef) => (<th key={c.key} className="p-2 text-left border" style={{width:c.width}}>{c.label}</th>))}</tr></thead>
          <tbody>{rows.map((r: any, i: number) => (<tr key={i} className="border">{t.columns.map((c: ColDef) => (<td key={c.key} className="p-2 border">{c.type ? formatBadge(r[c.key], c.type) : <>{r[c.key]?.toString()||''}</>}</td>))}</tr>))}</tbody></table></div>;
      })}
      {(schema.lists || []).map((l: ListDef) => {
        const items = (data[l.key] || []) as string[];
        if (!items.length) return null;
        return <div key={l.key}><h2 className="text-base font-semibold text-gray-900 mb-2 border-b pb-1">{l.title}</h2><ul className="list-disc pl-5 space-y-0.5 text-gray-600 text-xs">{items.map((c:string,i:number)=><li key={i}>{c}</li>)}</ul></div>;
      })}
      {(schema.sections || []).map((s: SectionDef) => {
        const v = data[s.key];
        if (!v) return null;
        return <div key={s.key}><h2 className="text-base font-semibold text-gray-900 mb-2 border-b pb-1">{s.title}</h2>{s.type === 'code' ? <pre className="text-xs text-gray-600 font-mono whitespace-pre-wrap">{v as string}</pre> : <div className="text-gray-600 text-xs">{v as string}</div>}</div>;
      })}
    </div>
  );
};

// ── Fullscreen content viewer (schema-driven) ──
const FullscreenView: React.FC<{
  open: boolean; title: string; content: string; onClose: () => void
}> = ({ open, title, content, onClose }) => {
  if (!open) return null;
  let parsed: any = null; let schema: DocSchema | undefined;
  try { parsed = JSON.parse(content); } catch { /* raw */ }
  if (parsed) {
    if (parsed.user_stories) schema = SCHEMAS.prd;
    else if (parsed.components) schema = SCHEMAS.architecture;
    else if (parsed.test_cases) schema = SCHEMAS.test;
  }
  return (
    <div className="fixed inset-0 bg-black/80 z-[60] flex flex-col" onClick={onClose}>
      <div className="flex items-center justify-between p-3 border-b border-gray-200 bg-white flex-shrink-0" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-gray-800">{title}</h3>
        <button onClick={onClose} className="p-1.5 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-800 transition-colors text-lg">✕</button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 bg-white max-w-4xl mx-auto w-full" onClick={e => e.stopPropagation()}>
        {schema && parsed ? <DataDocument data={parsed} schema={schema} /> : <pre className="text-xs text-gray-700 font-mono whitespace-pre-wrap break-all">{content}</pre>}
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
  const [recommending, setRecommending] = useState(false);
  const [teamStages, setTeamStages] = useState<Array<{ agent_name?: string; agent_id?: string; phase?: string; id?: string }>>(project.team_stages || []);
  const [runHistory, setRunHistory] = useState<ProjectRun[]>(project.runs || []);
  const [deployUrl, setDeployUrl] = useState('');
  const [deploying, setDeploying] = useState(false);
  const [healthReport, setHealthReport] = useState<Record<string, any> | null>(null);
  const [agentMode, setAgentMode] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [stageOutputs, setStageOutputs] = useState<Record<string, any> | null>(null);
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);
  const [confirmedPrd, setConfirmedPrd] = useState<Record<string, unknown> | null>(
    (project as any).confirmed_prd || null);
  const [showPrdDetail, setShowPrdDetail] = useState(false);
  const [prdEditText, setPrdEditText] = useState('');
  const [savingPrd, setSavingPrd] = useState(false);
  const [fullscreenTitle, setFullscreenTitle] = useState('');
  const [fullscreenContent, setFullscreenContent] = useState('');

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

  // ── Poll pipeline state during execution ──
  useEffect(() => {
    if (phase !== 'executing' && !phase?.includes('approval')) {
      if (pollInterval) { clearInterval(pollInterval); setPollInterval(null); }
      return;
    }
    if (!project.project_id || pollInterval) return;
    const id = setInterval(async () => {
      try {
        const st = await projectApi.getState(project.project_id);
        const s = (st as any)?.state || {};
        const p = s.phase as string || phase;
        setPhase(p);
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
        if (Object.keys(outputs).length > 0) setStageOutputs(outputs);
        if (p === 'done' || p === 'failed') onRefresh();
      } catch { /* ignore */ }
    }, 3000);
    setPollInterval(id);
    return () => { clearInterval(id); };
  }, [phase, project.project_id]);

  // Load stage outputs whenever project opens (reads _final_state.json via API)
  useEffect(() => {
    if (!project.project_id) return;
    (async () => {
      try {
        const st = await projectApi.getState(project.project_id);
        const state = (st as any)?.state || {};
        const outputs: Record<string, any> = {};
        const orderedKeys = project.team_stages?.map(s => (s as any).output_artifact).filter(Boolean) || [];
        const keys = orderedKeys.length > 0 ? orderedKeys : ['architecture', 'code', 'test_report'];
        for (const k of keys) {
          if (state[k] && typeof state[k] === 'object' && state[k].raw_output) {
            outputs[k] = state[k];
          }
        }
        if (Object.keys(outputs).length > 0) setStageOutputs(outputs);
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
      setTeamStages(stages);
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

  const handleRecommend = async () => {
    if (!project.project_id) return;
    setRecommending(true);
    try {
      const result = await projectApi.recommendTeam(project.project_id);
      const stages = (result as any)?.plan_stages || [];
      setTeamStages(stages);
      toast.success('AI 已推荐团队');
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

  const handleApprove = async () => {
    if (!project.project_id) return;
    setStarting(true);
    try {
      await projectApi.approve(project.project_id);
      setPhase('executing');
      toast.success('已审批，继续执行');
    } catch (e: any) { toastGateError(e, '审批失败'); }
    finally { setStarting(false); }
  };

  const handleReject = async () => {
    if (!project.project_id) return;
    const feedback = window.prompt('驳回理由（可选）：');
    if (feedback === null) return; // cancelled
    setStarting(true);
    try {
      await projectApi.reject(project.project_id, feedback);
      toast.success('已驳回，将重新生成');
      onRefresh();
    } catch (e: any) { toastGateError(e, '驳回失败'); }
    finally { setStarting(false); }
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
            <div className="p-3 rounded bg-green-500/10 border border-green-500/30 text-sm text-green-300">
              ✅ 构建完成
              {!deployUrl && (
                <Button variant="primary" size="sm" className="ml-3" onClick={handleDeploy} loading={deploying}>部署到 App</Button>
              )}
              {deployUrl && (
                <a href={deployUrl} target="_blank" rel="noreferrer" className="ml-3 text-primary underline text-xs flex items-center gap-1 inline-flex">
                  <ExternalLink className="w-3 h-3" /> 打开应用
                </a>
              )}
            </div>
            {/* Health Report Card */}
            {!healthReport && (
              <button
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                onClick={async () => {
                  setLoadingHealth(true);
                  try {
                    const r = await projectApi.getHealthReport(project.project_id);
                    setHealthReport(r as any);
                  } catch { /* ignore */ }
                  setLoadingHealth(false);
                }}
              >
                {loadingHealth ? <Loader2 className="w-3 h-3 animate-spin" /> : <BarChart3 className="w-3 h-3" />}
                查看健康报告
              </button>
            )}
            {healthReport && (
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
            )}
          </div>
        ) : phase === 'executing' ? (
          <div className="p-3 rounded bg-blue-500/10 border border-blue-500/30 text-sm space-y-3">
            <div className="flex items-center gap-2 text-blue-300">
              <Loader2 className="w-4 h-4 animate-spin" /> Pipeline 执行中...
            </div>
            {/* Pipeline progress with stages */}
            {teamStages.length > 0 && (
              <div className="space-y-1.5">
                {teamStages.map((s, i) => {
                  const isRunning = i === teamStages.findLastIndex(st => runHistory?.some(r => r.phase === 'done' ? false : true));
                  const isDone = runHistory?.length > 0 && i < teamStages.length - 1;
                  const name = s.agent_name || s.agent_id || s.id || `Stage ${i + 1}`;
                  return (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      {isDone ? (
                        <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                      ) : i === 0 || (i > 0 && runHistory?.length > 0) ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400 flex-shrink-0" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-gray-600 flex-shrink-0" />
                      )}
                      <span className={isDone ? 'text-green-300' : isRunning ? 'text-blue-300 font-medium' : 'text-gray-500'}>
                        {name}
                      </span>
                      {isRunning && i > 0 && <span className="text-blue-400 ml-auto text-[10px]">进行中</span>}
                    </div>
                  );
                })}
                <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full transition-all duration-500" style={{ width: `${teamStages.length > 0 ? ((runHistory?.length || 0) / teamStages.length) * 100 : 50}%` }} />
                </div>
              </div>
            )}
            {teamStages.length === 0 && (
              <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: '60%' }} />
              </div>
            )}
          </div>
        ) : phase === 'paused' || phase?.includes('approval') ? (
          <div className="p-3 rounded bg-amber-500/10 border border-amber-500/30 text-sm space-y-2">
            <div className="text-amber-300 flex items-center gap-2">
              <Clock className="w-4 h-4" /> 等待审批 — 请审核当前阶段产出
            </div>
            <div className="flex gap-2">
              <Button variant="primary" size="sm" onClick={handleApprove} loading={starting}>✅ 审批通过</Button>
              <Button variant="secondary" size="sm" onClick={handleReject}>❌ 驳回重做</Button>
            </div>
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
            <p className="text-gray-400">{(confirmedPrd.user_stories as any[])?.length || 0} 个 User Stories · {confirmedPrd.scope as string || '-'}</p>
            <div className="flex gap-1.5">
              {!showPrdDetail ? (
                <>
                <button onClick={handleEditPrd} className="text-[10px] px-2 py-1 rounded bg-dark-hover text-gray-300 hover:text-white transition-colors">📋 查看 & 编辑</button>
                <button onClick={() => { setFullscreenTitle('PRD: ' + (confirmedPrd.title as string || '')); setFullscreenContent(JSON.stringify(confirmedPrd, null, 2)); }}
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

        {/* Stage Outputs — show architecture/code/test_report when available */}
        {stageOutputs && Object.keys(stageOutputs).length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-gray-400 uppercase">阶段产出</h3>
            {/* Test results summary card */}
             {stageOutputs.test_report && (stageOutputs.test_report as any)?.test_results && (() => {
              const tr = (stageOutputs.test_report as any).test_results;
              const p = tr.passed || 0, f = tr.failed || 0, e = tr.errors || 0;
              const total = p + f + e;
              const rate = total > 0 ? p / total : 0;
              const repairRounds = (stageOutputs.test_report as any)?.repair_rounds || 0;
              const repairLog = (stageOutputs.test_report as any)?.repair_log || '';
              const color = rate >= 0.8 ? 'text-green-400 bg-green-500/10 border-green-500/30' :
                            rate > 0 ? 'text-amber-400 bg-amber-500/10 border-amber-500/30' :
                            'text-red-400 bg-red-500/10 border-red-500/30';
              return (
                <div className={`rounded border p-2 text-xs ${color}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold">🧪 测试结果</span>
                    {repairRounds > 0 && <span className="text-[10px] px-1 rounded bg-blue-500/10 text-blue-400">🛠 自修复 ×{repairRounds}</span>}
                    <span className="ml-auto font-bold">{(rate * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex gap-3">
                    <span>✅ {p} 通过</span>
                    <span>❌ {f} 失败</span>
                    <span>⚠️ {e} 错误</span>
                  </div>
                </div>
              );
            })()}
            {Object.entries(stageOutputs).map(([key, val]) => {
              const rw = (val as any)?.raw_output || '';
              // Dynamic label: match output_artifact to team stage's agent_name
              const matchedStage = teamStages.find(s => (s as any).output_artifact === key);
              const agentLabel = (matchedStage as any)?.agent_name || (matchedStage as any)?.display_name || '';
              // Fallback to key-based label if teamStages not available
              const label = agentLabel || {
                architecture: '🏗️ 架构设计', code: '💻 代码生成', test_report: '🧪 测试报告',
                testReport: '🧪 测试报告', prd: '📋 PRD',
              }[key] || key.replace(/[_-]/g, ' ');
              let summary = '';

              // ── Structural detection (not key-name matching) ──
              // Test report: has pass_rate or test_cases
              if (rw && (val as any).pass_rate != null || /test_cases|test_suites/.test(rw.slice(0, 200))) {
                try {
                  const j = JSON.parse(rw);
                  const cases = j.test_cases || [];
                  if (cases.length > 0) summary = `${cases.length} 个测试用例`;
                } catch { /* raw text, skip */ }
              }
              // Architecture: has components/api_contracts/data_model
              if (rw && /components|api_contracts|data_model/.test(rw.slice(0, 200))) {
                try {
                  const j = JSON.parse(rw);
                  const comps = j.components?.length || 0;
                  const apis = j.api_contracts?.length || j.api_design?.length || 0;
                  const db = j.database_schema ? 1 : 0;
                  const hasSec = j.security ? '🔒' : ''; const hasPerf = j.performance ? '⚡' : ''; const hasDeploy = j.deployment ? '🚀' : '';
                  summary = `${comps} 组件 · ${apis} API · DB ${db} ${hasSec}${hasPerf}${hasDeploy}`;
                } catch { /* raw text, skip */ }
              }
              // Code: count ## FILE: blocks
              if (rw && rw.includes('## FILE:')) {
                const files = (rw.match(/## FILE:/g) || []).length;
                if (files > 0) summary = `${files} 个代码文件`;
              }

              const preview = rw ? (typeof rw === 'string' ? rw.slice(0, 2000) : JSON.stringify(rw).slice(0, 2000)) : '';
              return (
                <details key={key} className="text-xs rounded border border-dark-border bg-dark-hover/30">
                  <summary className="p-2 cursor-pointer text-gray-300 font-medium flex items-center justify-between">
                    <span>{label} ({typeof rw === 'string' ? rw.length : 0} 字符{summary ? ' · ' + summary : ''})</span>
                    {rw && (
                      <button onClick={e => { e.preventDefault(); setFullscreenTitle(label); setFullscreenContent(typeof rw === 'string' ? rw : JSON.stringify(rw, null, 2)); }}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-500 hover:text-gray-300 hover:bg-primary/20 transition-colors flex-shrink-0 ml-2">
                        🔍 全屏
                      </button>
                    )}
                  </summary>
                  <pre className="p-2 whitespace-pre-wrap break-all text-gray-400 max-h-40 overflow-y-auto border-t border-dark-border">{preview || '(空)'}</pre>
                </details>
              );
            })}
          </div>
        )}

        {/* Chat */}
        <Card>
          <CardContent className="p-0">
            <InlineChat
              projectId={project.project_id}
              initialMessage={!prdReady ? project.description : undefined}
              onPhaseChange={(p) => { if (p === 'prd_ready') setPrdReady(true); }}
            />
          </CardContent>
        </Card>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {!prdReady && phase === 'dialogue' && (
            <Button variant="secondary" size="sm" onClick={handleRecommend} loading={recommending}>AI 推荐团队</Button>
          )}
          {prdReady && phase === 'dialogue' && (
            <Button variant="primary" size="sm" onClick={handleConfirm} loading={starting}>确认需求</Button>
          )}
          {phase === 'team_ready' && (
            <Button variant="primary" size="sm" onClick={handleStart} loading={starting}>{runHistory.length > 0 ? '重新构建' : '启动构建'}</Button>
          )}
        </div>

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
    </motion.div>
  );
};

// ── Main Factory Page ──
const FactoryPage: React.FC = () => {
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [deployedApps, setDeployedApps] = useState<any[]>([]);
  const [desc, setDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedProject, setSelectedProject] = useState<ProjectItem | null>(null);
  const [selectedApp, setSelectedApp] = useState<string>('');

  const loadAll = useCallback(async () => {
    try {
      const p = await projectApi.list();
      setProjects(p.projects || []);
    } catch { /* ignore */ }
    try {
      const r = await fetch('/api/platform/apps');
      const d = await r.json();
      setDeployedApps(d.apps || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const create = async () => {
    if (!desc.trim()) return;
    setCreating(true);
    try {
      const project = await projectApi.create({ name: desc.trim().slice(0, 30) || '新项目', description: desc.trim() });
      setDesc('');
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
    const last = p.runs?.[p.runs.length - 1];
    if (!last) return { label: '待开始', color: 'text-gray-500', bg: 'bg-gray-500/10', phase: 'dialogue' };
    if (last.phase === 'done') return { label: '已完成', color: 'text-green-400', bg: 'bg-green-500/10', phase: 'done' };
    if (last.phase === 'failed') return { label: '失败', color: 'text-red-400', bg: 'bg-red-500/10', phase: 'failed' };
    return { label: '构建中', color: 'text-blue-400', bg: 'bg-blue-500/10', phase: 'executing' };
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* ── Create Section ── */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card border border-dark-border rounded-xl p-5">
        <h2 className="text-lg font-bold text-gray-100 mb-3">新建应用</h2>
        <p className="text-sm text-gray-400 mb-3">用自然语言描述你想要构建的应用，AI 将自动完成需求分析、架构设计和代码生成</p>
        <Textarea
          value={desc}
          onChange={e => setDesc(e.target.value)}
          placeholder="例如：构建一个视频解析平台，支持上传、转码、AI 摘要生成..."
          rows={3}
          className="mb-3"
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
            const passRate = lastRun?.pass_rate ?? 0;
            const hasPrd = !!(p as any).confirmed_prd;
            return (
              <motion.div
                key={p.project_id} layout
                whileHover={{ y: -1 }}
                className="rounded-lg border border-dark-border bg-dark-card p-4 cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => setSelectedProject(p)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h4 className="text-sm font-medium text-gray-100 truncate pr-6">{p.name}</h4>
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
                      <CheckCircle className="w-3 h-3" />通过率 {(passRate * 100).toFixed(0)}%
                    </span>
                    <div className="ml-auto flex gap-1">
                      <button onClick={async (e) => { e.stopPropagation();
                        try { const r = await projectApi.deployToApp(p.project_id); setSelectedApp((r as any)?.app_url || ''); } catch {} }}
                        className="text-[10px] px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors flex items-center gap-1">
                        <ExternalLink className="w-3 h-3" />预览
                      </button>
                      <button onClick={async (e) => { e.stopPropagation();
                        try { await projectApi.rebuild(p.project_id); toast.success('重新构建已触发'); loadAll(); } catch (er) { toastGateError(er, '重建失败'); } }}
                        className="text-[10px] px-2 py-1 rounded bg-dark-hover text-gray-400 hover:text-gray-300 transition-colors flex items-center gap-1">
                        <RefreshCw className="w-3 h-3" />重建
                      </button>
                    </div>
                  </div>
                )}
                {status.phase === 'failed' && (
                  <div className="flex items-center gap-2 pt-2 border-t border-dark-border">
                    <span className="text-[10px] text-red-400 flex items-center gap-1"><XCircle className="w-3 h-3" />{lastRun?.error?.slice(0, 30) || '执行失败'}</span>
                    <button onClick={async (e) => { e.stopPropagation();
                      try { await projectApi.rebuild(p.project_id); toast.success('重新构建已触发'); loadAll(); } catch (er) { toastGateError(er, '重建失败'); } }}
                      className="ml-auto text-[10px] px-2 py-1 rounded bg-primary/20 text-primary hover:bg-primary/30 transition-colors flex items-center gap-1">
                      <RefreshCw className="w-3 h-3" />重新构建
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
              onClick={() => setSelectedApp(a.app_url || `http://localhost:8004/${a.app_id}`)}
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

        {projects.length === 0 && deployedApps.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg mb-2">还没有应用</p>
            <p className="text-sm">在上方输入需求描述，开始构建你的第一个应用</p>
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
