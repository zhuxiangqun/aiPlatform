import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle, XCircle, Loader2, Clock, Download, Code, FileText, Bug, Eye, EyeOff } from 'lucide-react';
import type { BuilderSession, PipelineStageConfig } from '../../services';
import InteractivePipelineDAG from './InteractivePipelineDAG';

interface PipelineProps {
  session: BuilderSession;
  teamStages?: PipelineStageConfig[];
  onRegenerate?: (stageKey: string) => void;
  onApprove?: () => void;
  onReject?: (stageKey: string) => void;
  onRollback?: (stageKey: string) => void;
  loading?: boolean;
}

// --- dynamic stage list built from team config (NOT hardcoded) ---

interface VisibleStage {
  key: string;
  label: string;
  desc: string;
  isTestStage: boolean;
}

function buildStages(teamStages?: PipelineStageConfig[], session?: BuilderSession): VisibleStage[] {
  const raw = session as Record<string, unknown> | undefined;
  const stages: VisibleStage[] = (teamStages || []).map((s) => ({
    key: s.output_artifact,
    label: s.agent_name,
    desc: (s as unknown as Record<string, unknown>).phase_description as string || s.phase || s.output_artifact,
    isTestStage: !!(s as unknown as Record<string, unknown>).generate_test_plan,
  }));
  // Insert test_plan stage if any artifact has test_script (structural detection)
  const testPlanEntry = Object.entries(raw || {}).find(([, v]) => isTestPlanArtifact(v));
  if (testPlanEntry) {
    const testingIdx = stages.findIndex((s) => {
      const val = raw?.[s.key];
      return isTestReportArtifact(val);
    });
    if (testingIdx >= 0 && !stages.some((s) => isTestPlanArtifact(raw?.[s.key]))) {
      const hasReport = Object.values(raw || {}).some((v) => isTestReportArtifact(v));
      stages.splice(testingIdx, 0, {
        key: testPlanEntry[0],
        label: '测试用例',
        desc: hasReport ? '已确认，测试已执行' :
              raw?.phase === 'paused' || (typeof raw?.phase === 'string' && (raw.phase as string).includes('approval')) ? '待确认' : '已生成',
        isTestStage: true,
      });
    }
  }
  return stages;
}

const ElapsedTimer: React.FC = () => {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return (
    <div className="text-[10px] text-gray-500 text-center">
      {mins > 0 ? `已运行 ${mins}分${secs}秒` : `已运行 ${secs}秒`}
    </div>
  );
};

// --- helpers ---

const getStageStatus = (key: string, session: BuilderSession, visible: VisibleStage[]) => {
  if (session.phase === 'failed') return 'failed';
  const raw = session as Record<string, unknown>;
  const currentIdx = raw['_current_stage_idx'] as number | undefined;
  const val = raw[key];
  const isCurrent = currentIdx != null && currentIdx >= 0 && visible[currentIdx]?.key === key;

  // HITL check first: current stage awaiting approval
  if (isCurrent && (session.phase?.includes('approval') || session.phase === 'paused'))
    return 'awaiting';

  // Passed: has artifact
  if (val != null) {
    if (typeof val === 'object' && 'recommendation' in val) {
      const tr = val as { recommendation?: string };
      if (tr.recommendation === 'APPROVED') return 'passed';
    }
    if (typeof val === 'object' || typeof val === 'string') {
      const obj = val as Record<string, unknown>;
      if (Object.keys(obj).length > 0) return 'passed';
    }
  }

  // Running
  if (isCurrent && session.phase === 'executing') return 'running';

  return 'waiting';
};

// Structural artifact type detection — uses artifact shape, not key name
const isTestReportArtifact = (val: unknown): val is { pass_rate?: number; test_cases?: unknown[]; recommendation?: string; issues?: unknown[] } =>
  typeof val === 'object' && val != null && 'pass_rate' in val;

const isCodeArtifact = (val: unknown): val is { files?: unknown[] } =>
  typeof val === 'object' && val != null && ('files' in val || 'component_files' in val);

const isPRDArtifact = (val: unknown): boolean =>
  typeof val === 'object' && val != null && ('sections' in val || 'acceptance_criteria' in val || 'features' in val);

const isTestPlanArtifact = (val: unknown): val is { test_script?: string; test_cases_count?: number } =>
  typeof val === 'object' && val != null && 'test_script' in val;

const isFlatFileDict = (val: unknown): boolean =>
  typeof val === 'object' && val != null && !Array.isArray(val) &&
  Object.keys(val as object).length > 0 &&
  Object.values(val as object).every(v => typeof v === 'string' && v.length > 20);

const hasArtifact = (key: string, session: BuilderSession): boolean => {
  const raw = session as Record<string, unknown>;
  return raw[key] != null;
};

const statusIcon = (status: string) => {
  if (status === 'passed') return <CheckCircle className="w-5 h-5 text-green-400" />;
  if (status === 'failed') return <XCircle className="w-5 h-5 text-red-400" />;
  if (status === 'running') return <Loader2 className="w-5 h-5 text-primary animate-spin" />;
  if (status === 'partial') return <Clock className="w-5 h-5 text-yellow-400" />;
  if (status === 'awaiting') return <Clock className="w-5 h-5 text-amber-400" />;
  return <Clock className="w-5 h-5 text-gray-600" />;
};

const statusLabel = (status: string) => {
  if (status === 'passed') return '已完成';
  if (status === 'failed') return '失败';
  if (status === 'running') return '执行中';
  if (status === 'partial') return '未通过';
  if (status === 'awaiting') return '待确认';
  return '等待中';
};

const statusColor = (status: string) => {
  if (status === 'passed') return 'bg-green-500/10 text-green-300';
  if (status === 'failed') return 'bg-red-500/10 text-red-300';
  if (status === 'running') return 'bg-primary/10 text-primary';
  if (status === 'partial') return 'bg-yellow-500/10 text-yellow-300';
  if (status === 'awaiting') return 'bg-amber-500/10 text-amber-300';
  return 'bg-gray-500/10 text-gray-400';
};

// --- structured output viewer ---

const StructuredViewer: React.FC<{ stageKey: string; data: unknown }> = ({ data }) => {
  const val = data as Record<string, unknown> | null;
  if (!val) return null;

  const stories = (val.user_stories as Array<Record<string, unknown>>) || [];
  const constraints = (val.constraints as string[]) || [];
  const components = (val.components as Array<Record<string, unknown>>) || [];
  const dataModel = (val.data_model as Record<string, Record<string, string>>) || {};
  const apiContracts = (val.api_contracts as Array<Record<string, unknown>>) || [];
  const testCases = (val.test_cases as Array<Record<string, unknown>>) || [];
  const techStack = (val.tech_stack as Record<string, string>) || {};
  const files = (val.files as Array<Record<string, unknown>>) || [];
  const rawOutput = typeof val.raw_output === 'string' ? val.raw_output : null;

  const isPRD = stories.length > 0;
  const isArch = components.length > 0 || Object.keys(dataModel).length > 0 || apiContracts.length > 0;
  const isTestPlan = testCases.length > 0;
  const isCode = files.length > 0;
  const hasContent = isPRD || isArch || isTestPlan || isCode || Boolean(rawOutput);
  if (!hasContent) return null;

  return (
    <details className="mt-2 group">
      <summary className="text-[10px] text-gray-500 cursor-pointer hover:text-gray-300">查看产出详情</summary>
      <div className="mt-1 p-2 rounded bg-dark-hover text-[10px] text-gray-400 max-h-40 overflow-y-auto space-y-2">
        {isPRD && (
          <>
            <div className="text-gray-300 font-medium mb-1">PRD · {stories.length} 个 User Stories</div>
            {stories.map((us: Record<string, unknown>, i: number) => (
              <details key={i} className="ml-1">
                <summary className="cursor-pointer text-gray-200">
                  <span className="text-primary">{us.id as string}</span> {(us.description as string || '').slice(0, 70)}
                </summary>
                <div className="ml-3 mt-1 text-gray-500">
                  {(us.acceptance_criteria as string[] || []).map((ac: string, j: number) => (
                    <div key={j}>AC{j+1}: {ac}</div>
                  ))}
                </div>
              </details>
            ))}
            {constraints.length > 0 && (
              <div className="ml-1 mt-1">
                <span className="text-gray-300">约束：</span>
                {constraints.map((c: string, i: number) => (
                  <div key={i} className="ml-2 text-gray-500">{c}</div>
                ))}
              </div>
            )}
          </>
        )}
        {isTestPlan && (
          <div>
            <div className="text-gray-300 font-medium mb-1">测试用例 ({testCases.length})</div>
            {testCases.map((tc: Record<string, unknown>, i: number) => (
              <div key={i} className="ml-1 mb-1">
                <span className="text-primary">{tc.id as string}</span>
                <span className="text-gray-200 ml-1">{(tc.description as string || '').slice(0, 60)}</span>
                <span className="text-gray-500 ml-1">— {(tc.expected as string || '').slice(0, 40)}</span>
              </div>
            ))}
          </div>
        )}
        {isArch && (
          <>
            {components.length > 0 && (
              <div>
                <div className="text-gray-300 font-medium mb-1">组件 ({components.length})</div>
                {components.map((c: Record<string, unknown>, i: number) => (
                  <div key={i} className="ml-2 mb-1">
                    <span className="text-gray-100">{c.name as string}</span>
                    <span className="text-gray-500 ml-1">— {(c.responsibility as string || '').slice(0, 60)}</span>
                    {(c.dependencies as string[])?.length > 0 && (
                      <span className="text-[9px] text-blue-400 ml-1">[{(c.dependencies as string[]).join(', ')}]</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {Object.keys(dataModel).length > 0 && (
              <div>
                <div className="text-gray-300 font-medium mb-1">数据模型</div>
                {Object.entries(dataModel).map(([entity, fields]) => (
                  <div key={entity} className="ml-2 mb-1">
                    <span className="text-gray-100">{entity}</span>
                    <span className="text-gray-500 ml-1">{Object.entries(fields || {}).map(([k, v]) => `${k}: ${v}`).join(', ')}</span>
                  </div>
                ))}
              </div>
            )}
            {apiContracts.length > 0 && (
              <div>
                <div className="text-gray-300 font-medium mb-1">API 契约 ({apiContracts.length})</div>
                {apiContracts.map((api: Record<string, unknown>, i: number) => (
                  <div key={i} className="ml-2 mb-1">
                    <span className={`font-mono ${api.method === 'GET' ? 'text-green-400' : 'text-yellow-400'}`}>
                      {(api.method as string || 'GET').padEnd(6)}
                    </span>
                    <span className="text-gray-200 ml-1">{api.path as string}</span>
                  </div>
                ))}
              </div>
            )}
            {Object.keys(techStack).length > 0 && (
              <div><span className="text-gray-300">技术栈：</span>{Object.entries(techStack).map(([k, v]) => `${k}: ${v}`).join(', ')}</div>
            )}
          </>
        )}
        {isCode && (
          <div>
            <div className="text-gray-300 font-medium mb-1">文件 ({files.length})</div>
            {files.map((f: Record<string, unknown>, i: number) => (
              <div key={i} className="ml-2">
                <span className="font-mono">{f.path as string}</span>
                <span className="ml-1">({((f.content as string) || '').length} 字符)</span>
              </div>
            ))}
          </div>
        )}
        {rawOutput && !isPRD && !isArch && !isTestPlan && !isCode && (
          <pre className="whitespace-pre-wrap break-all text-[9px]">{(rawOutput || '').slice(0, 1500)}</pre>
        )}
      </div>
    </details>
  );
};

// ── Code file viewer with tabs ──

const CodeFileViewer: React.FC<{ open: boolean; files: Record<string, string> | null; title: string; onClose: () => void }> = ({ open, files, title, onClose }) => {
  const entries = Object.entries(files || {});
  const [activeFile, setActiveFile] = useState(entries[0]?.[0] || '');

  useEffect(() => {
    if (entries.length > 0 && !entries.some(([k]) => k === activeFile)) {
      setActiveFile(entries[0][0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  if (!open || entries.length === 0) return null;

  const activeContent = (files?.[activeFile] || '')
    .replace(/^## FILE:\s*\S+\s*\n?/, '')
    .replace(/^```\w*\n/, '')
    .replace(/\n```\s*$/, '');

  const detectLang = (filename: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const map: Record<string, string> = { py: 'python', ts: 'typescript', tsx: 'typescript', js: 'javascript',
      jsx: 'javascript', css: 'css', html: 'html', json: 'json', yaml: 'yaml', yml: 'yaml',
      md: 'markdown', sql: 'sql', sh: 'bash', txt: 'text', dockerfile: 'dockerfile' };
    return map[ext] || map[filename.toLowerCase()] || '';
  };

  const totalLines = activeContent.split('\n').length;
  const totalChars = activeContent.length;

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={onClose}>
      <motion.div
        initial={{ scale: 0.95 }} animate={{ scale: 1 }}
        className="bg-dark-card border border-dark-border rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-dark-border">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-bold text-gray-100">{title}</h2>
            <span className="text-[11px] text-gray-500">{entries.length} 个文件</span>
          </div>
          <button className="text-gray-500 hover:text-gray-300 text-lg leading-none" onClick={onClose}>✕</button>
        </div>

        <div className="flex gap-0 px-4 pt-2 overflow-x-auto border-b border-dark-border bg-dark-hover/50 shrink-0">
          {entries.map(([name, content]) => (
            <button
              key={name}
              onClick={() => setActiveFile(name)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs whitespace-nowrap rounded-t transition-colors ${
                name === activeFile
                  ? 'bg-dark-card text-gray-100 border-t border-l border-r border-dark-border -mb-[1px]'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <FileText className="w-3 h-3" />
              {name}
              <span className="text-[10px] text-gray-600">({(content as string).length}字符)</span>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto">
          <div className="flex items-center justify-between px-4 py-1.5 text-[10px] text-gray-600 border-b border-dark-border/50 bg-dark-hover/30">
            <span>{detectLang(activeFile) || 'text'} · {totalLines} 行 · {totalChars.toLocaleString()} 字符</span>
            <button
              className="text-primary hover:text-primary/80"
              onClick={() => {
                const blob = new Blob([activeContent], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = activeFile; a.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download className="w-3 h-3 inline mr-1" />下载此文件
            </button>
          </div>
          <pre className="p-4 text-xs text-gray-300 font-mono leading-relaxed whitespace-pre overflow-auto max-h-[calc(90vh-160px)]">
            {activeContent}
          </pre>
        </div>
      </motion.div>
    </div>
  );
};

// --- main component ---

function getTestReport(session: Record<string, unknown>): Record<string, unknown> | undefined {
  for (const key of Object.keys(session)) {
    const val = session[key];
    if (val && typeof val === 'object' && isTestReportArtifact(val as Record<string, unknown>)) {
      return val as Record<string, unknown>;
    }
  }
  return undefined;
}

// --- stage trace panel (orchestration visibility) ---

interface StageTrace {
  stage_id?: string;
  agent_id?: string;
  phase?: string;
  skill_name?: string;
  model_name?: string;
  model_purpose?: string;
  model_tier?: string;
  complexity_range?: number[];
  output_size?: number;
  elapsed_sec?: number;
  tokens_used?: number;
  retry_count?: number;
  failure_strategy?: string;
  strategy?: string;
}

const StageTracePanel: React.FC<{ trace: StageTrace; stageKey: string }> = ({ trace, stageKey }) => {
  const [open, setOpen] = useState(false);
  if (!trace || !trace.model_name) return null;

  return (
    <div className="mt-2 border-t border-dark-border pt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors w-full text-left"
      >
        {open ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
        思维链 · {trace.model_name}{trace.model_tier ? ` · ${trace.model_tier}` : ''}
        {trace.elapsed_sec != null ? ` · ${trace.elapsed_sec.toFixed(0)}s` : ''}
      </button>
      {open && (
        <div className="mt-2 text-[10px] text-gray-400 space-y-1 pl-4 border-l border-dark-border">
          {trace.model_name && (
            <div>
              模型: <span className="text-gray-300">{trace.model_name}</span>
              {trace.model_tier && (
                <span className="ml-1 px-1 bg-dark-border rounded text-[9px]">{trace.model_tier}</span>
              )}
            </div>
          )}
          {trace.model_purpose && <div>用途: {trace.model_purpose}</div>}
          {trace.model_tier && trace.complexity_range && (
            <div>复杂度: {trace.complexity_range[0]}-{trace.complexity_range[1]}</div>
          )}
          {trace.skill_name && <div>技能: {trace.skill_name}</div>}
          {trace.strategy && <div>策略: {trace.strategy === 'skill_dispatch' ? '技能执行' : 'ReAct 推理'}</div>}
          {trace.output_size != null && <div>产出: {(trace.output_size / 1024).toFixed(1)} KB</div>}
          {trace.tokens_used != null && trace.tokens_used > 0 && <div>Token: {trace.tokens_used.toLocaleString()}</div>}
          {trace.retry_count != null && trace.retry_count > 0 && <div className="text-yellow-400">重试: {trace.retry_count} 次</div>}
          {trace.failure_strategy && <div>失败策略: {trace.failure_strategy}</div>}
          {trace.agent_id && <div>Agent: {trace.agent_id}</div>}
        </div>
      )}
    </div>
  );
};


export const BuilderPipeline: React.FC<PipelineProps> = ({ session, teamStages, onRegenerate, onApprove, onReject: _onReject, onRollback, loading }) => {
  const raw = session as Record<string, unknown>;
  const testReport = getTestReport(raw);
  const passRate = (testReport?.pass_rate as number) ?? 0;
  const rec = testReport?.recommendation as string | undefined;
  const visible = buildStages(teamStages, session);
  const [previewStage, setPreviewStage] = useState<VisibleStage | null>(null);
  const [previewData, setPreviewData] = useState<Record<string, unknown> | null>(null);

  const cols = visible.length <= 2 ? 'lg:grid-cols-2' : visible.length <= 3 ? 'lg:grid-cols-3' : 'lg:grid-cols-4';
  return (
    <div className="space-y-4">
      {/* Interactive Pipeline DAG */}
      <InteractivePipelineDAG
        session={session}
        teamStages={teamStages}
        onStageClick={(key) => {
          const el = document.getElementById(`stage-${key}`);
          el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }}
      />

      <div className={`grid grid-cols-1 ${cols} gap-3`}>
        {visible.map((stage, idx) => {
          const status = getStageStatus(stage.key, session, visible);
          const hasContent = hasArtifact(stage.key, session);
          const artifact = (session as Record<string, unknown>)[stage.key];

          return (
            <motion.div
              key={stage.key}
              id={`stage-${stage.key}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="rounded-lg border border-dark-border bg-dark-card p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="text-sm font-semibold text-gray-100">{stage.label}</div>
                  <div className="text-xs text-gray-500">{stage.desc}</div>
                </div>
                <div className="flex items-center gap-2">
                  {statusIcon(status)}
                  <span className={`text-xs px-2 py-0.5 rounded ${statusColor(status)}`}>
                    {statusLabel(status)}
                  </span>
                </div>
              </div>

              <div className="rounded-lg bg-dark-border overflow-hidden mb-3" style={{ height: 10 }}>
                <div
                  className={`h-full rounded-lg transition-all duration-1000 ${
                    status === 'passed' ? 'bg-green-500' :
                    status === 'running' ? 'bg-cyan-500' :
                    status === 'awaiting' ? 'bg-yellow-500' :
                    'bg-transparent'
                  }`}
                  style={{ width: status === 'running' ? '66%' : status === 'passed' ? '100%' : status === 'awaiting' ? '100%' : '0%' }}
                />
              </div>

              {status === 'running' && (
                <div className="flex items-center justify-between mb-3">
                  <ElapsedTimer />
                  <span className="text-[10px] text-cyan-400 font-medium">LLM 推理中…</span>
                </div>
              )}

              {/* trace panel: model info + reasoning chain */}
              {(hasContent || status === 'passed' || status === 'running') && (() => {
                const traceKey = `_trace_${stage.key}`;
                const trace = (session as Record<string, unknown>)[traceKey] as StageTrace | undefined;
                if (!trace && !hasContent) return null;
                // Also check for trace on agent_id
                const sid = (stage as unknown as Record<string, unknown>).id as string | undefined;
                const altTraceKey = sid ? `_trace_${sid}` : null;
                const altTrace = altTraceKey ? (session as Record<string, unknown>)[altTraceKey] as StageTrace | undefined : undefined;
                const finalTrace = trace || altTrace;
                if (!finalTrace) return null;
                return <StageTracePanel trace={finalTrace} stageKey={stage.key} />;
              })()}

              {hasContent && (
                <div className="text-xs text-gray-400 space-y-1">
                  {(() => {
                    const val = (session as Record<string, unknown>)[stage.key] as Record<string, unknown> | null;
                    if (!val) return null;
                    if (isTestReportArtifact(val) && testReport) {
                      return <>
                        <div>测试用例: {(testReport?.test_cases as Array<unknown> | undefined)?.length || 0}</div>
                        <div className="flex items-center gap-1">通过率:<span className={passRate >= 0.8 ? 'text-green-400' : 'text-red-400'}>{(passRate * 100).toFixed(0)}%</span></div>
                      </>;
                    }
                    const comps = (val as Record<string, unknown>).components as Array<Record<string, unknown>> || [];
                    const dm = (val as Record<string, unknown>).data_model as Record<string, unknown> || {};
                    const apis = (val as Record<string, unknown>).api_contracts as Array<Record<string, unknown>> || [];
                    const f = (val as Record<string, unknown>).files as Array<Record<string, unknown>> || [];
                    const tc = (val as Record<string, unknown>).test_cases as Array<Record<string, unknown>> || [];
                    const rawOutput = typeof (val as Record<string, unknown>).raw_output === 'string' ? (val as Record<string, unknown>).raw_output : null;
                    return <>
                      {comps.length > 0 && <div>组件: {comps.length} 个</div>}
                      {Object.keys(dm).length > 0 && <div>数据模型: {Object.keys(dm).length} 个实体</div>}
                      {apis.length > 0 && <div>API 契约: {apis.length} 个</div>}
                      {tc.length > 0 && <div>测试用例: {tc.length} 条</div>}
                      {f.length > 0 && <div>文件: {f.length} 个</div>}
                      {rawOutput && <div className="text-gray-500 italic">LLM 原始输出</div>}
                    </>;
                  })()}
                </div>
              )}

              {hasContent && !isCodeArtifact(artifact) && (
                <StructuredViewer stageKey={stage.key} data={artifact} />
              )}
              {hasContent && isCodeArtifact(artifact) && (
                <div className="text-[10px] text-gray-500 mt-2 space-y-1">
                  <div>代码已生成，保存至 ~/.aiplat/output/{session.session_id}/ 目录</div>
                  {(() => {
                    const val = (session as Record<string, unknown>)[stage.key] as Record<string, unknown> | null;
                    if (isFlatFileDict(val)) {
                      const keys = Object.keys(val as object);
                      return (
                        <div className="text-gray-400">
                          {keys.slice(0, 5).map(k => <span key={k} className="mr-2 font-mono">{k}</span>)}
                          {keys.length > 5 && <span className="text-gray-600">+{keys.length - 5} 个文件</span>}
                        </div>
                      );
                    }
                    return null;
                  })()}
                  <button
                    className="flex items-center gap-1 text-blue-400 hover:text-blue-300 cursor-pointer"
                    onClick={() => {
                      const artifact = (session as Record<string, unknown>)[stage.key] as Record<string, unknown>;
                      if (isFlatFileDict(artifact)) {
                        setPreviewStage(stage);
                        setPreviewData(artifact);
                      }
                    }}
                  >
                    <Code className="w-3 h-3" /> 预览代码
                  </button>
                </div>
              )}

              {hasContent && status !== 'running' && !isCodeArtifact(artifact) && (
                <>
                  <button
                    className="mt-2 flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 cursor-pointer"
                    onClick={() => {
                      const artifact = (session as Record<string, unknown>)[stage.key];
                      const json = JSON.stringify(artifact, null, 2);
                      const blob = new Blob([json], { type: 'application/json' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${stage.key}_${session.session_id}.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <Download className="w-3 h-3" /> 下载
                  </button>
                  <button
                    className="mt-1 flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 cursor-pointer"
                    onClick={() => {
                      setPreviewStage(stage);
                      setPreviewData((session as Record<string, unknown>)[stage.key] as Record<string, unknown>);
                    }}
                  >
                    🔍 预览
                  </button>
                </>
              )}

              {hasContent && status !== 'running' && !isPRDArtifact(artifact) && (
                <button
                  className="mt-1 flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 cursor-pointer"
                  onClick={() => onRegenerate?.(stage.key)}
                  title="将清空本阶段及所有下游产物，重新生成"
                >
                  🔄 重新生成（含下游）
                </button>
              )}

              {/* Step Debug: open execute modal for this stage's agent */}
              {!stage.isTestStage && (
                <button
                  className="mt-1 flex items-center gap-1 text-[10px] text-purple-400 hover:text-purple-300 cursor-pointer"
                  onClick={() => onRollback?.(stage.key)}
                  title="单独调试此阶段对应的 Agent"
                >
                  <Bug className="w-3 h-3 inline" /> 单步调试
                </button>
              )}

              {/* HITL buttons — shown on the stage that is awaiting approval */}
              {(session.phase.includes('approval') || session.phase === 'paused') && (
                (() => {
                  // Config-driven: use _current_stage_idx to find the HITL stage's artifact key
                  const currentIdx = ((session as Record<string, unknown>)?.['_current_stage_idx'] as number);
                  const hitlKey = currentIdx != null && currentIdx >= 0 && currentIdx < visible.length
                    ? visible[currentIdx].key
                    : '';
                  if (stage.key !== hitlKey) return null;
                  return (
                    <div className="mt-2 space-y-1">
                      {stage.isTestStage ? (
                        <button className="w-full text-[10px] px-2 py-1 rounded bg-primary/20 text-primary hover:bg-primary/30"
                          onClick={() => onApprove?.()}>
                          {loading ? '⏳ 执行中…' : '✅ 确认并执行测试'}
                        </button>
                      ) : (
                        <button className="w-full text-[10px] px-2 py-1 rounded bg-green-500/20 text-green-300 hover:bg-green-500/30"
                          onClick={() => onApprove?.()}>
                          ✅ 确认并继续
                        </button>
                      )}
                    </div>
                  );
                })()
              )}

              {/* Rollback — completed non-PRD stages */}
              {hasContent && status !== 'running' && !isPRDArtifact(artifact) && !(session.phase.includes('approval') || session.phase === 'paused') && (
                <button
                  className="mt-1 flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 cursor-pointer"
                  onClick={() => onRollback?.(stage.key)}
                  title="回退本阶段及下游"
                >
                  ↩ 回退
                </button>
              )}

              {!hasContent && status === 'waiting' && (
                <div className="text-xs text-gray-500 italic">等待上游完成...</div>
              )}
            </motion.div>
          );
        })}
      </div>

      {testReport && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className={`rounded-lg border p-4 ${rec === 'APPROVED' ? 'border-green-500/30 bg-green-500/5' : 'border-yellow-500/30 bg-yellow-500/5'}`}
        >
          <div className="flex items-center gap-2 mb-2">
            {rec === 'APPROVED' ? (
              <CheckCircle className="w-5 h-5 text-green-400" />
            ) : (
              <XCircle className="w-5 h-5 text-red-400" />
            )}
            <span className={`font-semibold ${rec === 'APPROVED' ? 'text-green-300' : 'text-red-300'}`}>
              {rec === 'APPROVED' ? '全部测试通过 — 应用已就绪' : `测试未通过（通过率 ${(passRate * 100).toFixed(0)}%）— 已自动回退修复`}
            </span>
          </div>
          {((testReport?.issues as Array<unknown> | undefined)?.length ?? 0) > 0 && (
            <div className="mt-2 space-y-1">
              {(testReport?.issues as any[])?.map((issue: any, i: number) => {
                const text = typeof issue === 'string' ? issue : (issue.title || issue.description || issue.message || '');
                const sev = issue.severity || '';
                return (
                  <div key={i} className="text-xs text-gray-400 flex items-start gap-1">
                    <span className={`${sev === 'P0' ? 'text-red-400' : 'text-yellow-400'} shrink-0 mt-0.5`}>
                      {sev ? `[${sev}]` : '!'}
                    </span>
                    <span>{text}</span>
                  </div>
                );
              })}
            </div>
          )}
          {(testReport?.results as Array<{ passed: boolean }> | undefined)?.some((r) => !r.passed) && (
            <div className="mt-3 space-y-1">
              <div className="text-xs text-gray-500 mb-1">失败详情：</div>
              {(testReport?.results as Array<{ passed: boolean; test_case_id: string; actual?: string; error?: string }>)
                .filter((r) => !r.passed)
                .map((r) => (
                  <div key={r.test_case_id} className="text-xs bg-dark-card rounded p-2 border border-dark-border">
                    <div className="text-red-300">{r.test_case_id}</div>
                    <div className="text-gray-500 mt-1">
                      <div>期望: {(testReport?.test_cases as Array<{ id: string; expected?: string }> | undefined)?.find((tc) => tc.id === r.test_case_id)?.expected || '—'}</div>
                      <div>实际: {r.actual || r.error || '—'}</div>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </motion.div>
      )}

      {(session.iteration ?? 0) > 0 && (
        <div className="text-xs text-gray-500 text-center">
          已迭代 {session.iteration} 次
          {session.error ? ` · ${session.error}` : ''}
        </div>
      )}

      {/* ── Code File Viewer (for flat {filename: content} dicts) ── */}
      <CodeFileViewer open={!!previewStage && !!previewData && isFlatFileDict(previewData)}
        files={previewData as Record<string, string>}
        title={previewStage?.label ? `${previewStage.label} · 产出预览` : '产出预览'}
        onClose={() => { setPreviewStage(null); setPreviewData(null); }}
      />

      {/* ── Preview Modal (fallback: raw JSON) ── */}
      {previewStage && previewData && !isFlatFileDict(previewData) && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => { setPreviewStage(null); setPreviewData(null); }}>
          <motion.div
            initial={{ scale: 0.95 }} animate={{ scale: 1 }}
            className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-3xl max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-100">{previewStage.label} · 产出预览</h2>
              <button
                className="text-gray-500 hover:text-gray-300 text-sm"
                onClick={() => { setPreviewStage(null); setPreviewData(null); }}
              >✕</button>
            </div>
            <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all bg-dark-hover rounded p-4 max-h-[70vh] overflow-y-auto">
              {JSON.stringify(previewData, null, 2)}
            </pre>
          </motion.div>
        </div>
      )}
    </div>
  );
};
