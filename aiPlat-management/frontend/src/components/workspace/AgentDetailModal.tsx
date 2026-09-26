import React, { useEffect, useState } from 'react';
import { Copy, ExternalLink } from 'lucide-react';
import { Modal, Button, Input, Tabs, toast } from '../ui';
import { workspaceAgentApi, skillApi, toolApi, packagesApi } from '../../services';
import { toastGateError } from '../ui';
import type { Agent } from '../../services';

interface AgentDetailModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const typeLabels: Record<string, string> = {
  base: '基础',
  react: 'ReAct',
  plan: '规划型',
  tool: '工具型',
  rag: 'RAG',
  conversational: '对话型',
};

const listingStatusConfig: Record<string, { cls: string; text: string }> = {
  draft: { cls: 'bg-gray-800 text-gray-400', text: '草稿' },
  ready: { cls: 'bg-amber-900/40 text-amber-300', text: '待审核' },
  published: { cls: 'bg-blue-900/40 text-blue-300', text: '已发布' },
  listed: { cls: 'bg-green-900/40 text-green-300', text: '已上架' },
  deprecated: { cls: 'bg-gray-800 text-gray-500', text: '已废弃' },
  running: { cls: 'bg-green-900/40 text-green-300', text: '运行中' },
  idle: { cls: 'bg-yellow-900/40 text-yellow-300', text: '空闲' },
  stopped: { cls: 'bg-red-900/40 text-red-300', text: '已停止' },
  error: { cls: 'bg-red-900/40 text-red-300', text: '错误' },
  pending: { cls: 'bg-gray-800 text-gray-400', text: '待启动' },
};

const runStatusConfig: Record<string, { cls: string; text: string }> = {
  completed: { cls: 'bg-green-900/50 text-green-300', text: '已完成' },
  success: { cls: 'bg-green-900/50 text-green-300', text: '已完成' },
  ok: { cls: 'bg-green-900/50 text-green-300', text: '已完成' },
  running: { cls: 'bg-blue-900/50 text-blue-300', text: '执行中' },
  accepted: { cls: 'bg-blue-900/50 text-blue-300', text: '已受理' },
  failed: { cls: 'bg-red-900/50 text-red-300', text: '失败' },
  error: { cls: 'bg-red-900/50 text-red-300', text: '失败' },
  timeout: { cls: 'bg-amber-900/50 text-amber-200', text: '超时' },
  cancelled: { cls: 'bg-gray-700 text-gray-300', text: '已取消' },
  canceled: { cls: 'bg-gray-700 text-gray-300', text: '已取消' },
};

function formatTs(ts?: number | string | null): string {
  if (ts == null || ts === '') return '—';
  const n = typeof ts === 'number' ? ts : Number(ts);
  if (!Number.isFinite(n) || n <= 0) {
    const s = String(ts);
    return s.length > 19 ? s.slice(0, 19) : s;
  }
  const ms = n > 1e12 ? n : n * 1000;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return String(ts);
  }
}

function formatDuration(ms?: number | null): string {
  if (ms == null || !Number.isFinite(Number(ms)) || Number(ms) <= 0) return '';
  const n = Number(ms);
  if (n < 1000) return `${Math.round(n)}ms`;
  return `${(n / 1000).toFixed(1)}s`;
}

function summarizeInput(input: unknown): string {
  if (input == null) return '（无输入摘要）';
  if (typeof input === 'string') {
    const t = input.trim();
    return t ? t.slice(0, 120) : '（空输入）';
  }
  if (typeof input === 'object') {
    const o = input as Record<string, unknown>;
    const text = o.text ?? o.message ?? o.query ?? o.input;
    if (typeof text === 'string' && text.trim()) return text.trim().slice(0, 120);
    try {
      const s = JSON.stringify(input);
      if (!s || s === 'null' || s === '{}') return '（无输入摘要）';
      return s.slice(0, 120);
    } catch {
      return '（无输入摘要）';
    }
  }
  return String(input).slice(0, 120);
}

function copyText(text: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success('已复制'),
    () => toast.error('复制失败'),
  );
}

function SectionTitle({ children, extra }: { children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <div className="text-sm text-gray-300 font-medium">{children}</div>
      {extra}
    </div>
  );
}

function BindingChip({
  label,
  id,
  tone,
}: {
  label: string;
  id?: string;
  tone: 'blue' | 'purple' | 'emerald' | 'orange' | 'rose';
}) {
  const tones: Record<string, string> = {
    blue: 'bg-blue-500/15 text-blue-300 border-blue-500/25',
    purple: 'bg-purple-500/15 text-purple-300 border-purple-500/25',
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
    orange: 'bg-orange-500/15 text-orange-300 border-orange-500/25',
    rose: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium border ${tones[tone]}`} title={id || label}>
      <span>{label}</span>
      {id && id !== label ? <span className="text-[10px] opacity-70 font-mono">{id}</span> : null}
    </span>
  );
}

const AgentDetailModal: React.FC<AgentDetailModalProps> = ({ open, agent, onClose }) => {
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const [skillMap, setSkillMap] = useState<Record<string, string>>({});
  const [toolMap, setToolMap] = useState<Record<string, string>>({});
  const [sop, setSop] = useState<string | null>(null);
  const [sopLoading, setSopLoading] = useState(false);
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [versions, setVersions] = useState<any[] | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [history, setHistory] = useState<any[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [pubName, setPubName] = useState('');
  const [pubLoading, setPubLoading] = useState(false);
  const [signing, setSigning] = useState(false);
  const [signKey, setSignKey] = useState('');
  const [signResult, setSignResult] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    if (open && agent) {
      setLoading(true);
      setActiveTab('overview');
      setPromptExpanded(false);
      setSignResult(null);
      setSignKey('');
      Promise.all([
        workspaceAgentApi.get(agent.id),
        skillApi.list({ limit: 500 }).catch(() => ({ skills: [] })),
        toolApi.list({ limit: 200 }).catch(() => ({ tools: [] })),
      ])
        .then(([res, skillList, toolList]: [any, any, any]) => {
          setDetail(res);
          const sItems = skillList?.skills || skillList?.items || skillList || [];
          if (Array.isArray(sItems)) {
            const map: Record<string, string> = {};
            sItems.forEach((s: any) => {
              map[s.id] = s.name || s.display_name || s.id;
            });
            setSkillMap(map);
          }
          const tItems = toolList?.tools || toolList?.items || toolList || [];
          if (Array.isArray(tItems)) {
            const map: Record<string, string> = {};
            tItems.forEach((t: any) => {
              map[t.name] = t.description || t.display_name || t.name;
            });
            setToolMap(map);
          }
        })
        .catch(() => setDetail(null))
        .finally(() => setLoading(false));
      setSop(null);
      setVersions(null);
      setHistory(null);
    } else {
      setDetail(null);
      setSop(null);
      setVersions(null);
      setHistory(null);
    }
  }, [open, agent]);

  const loadSop = () => {
    if (!agent) return;
    setSopLoading(true);
    workspaceAgentApi
      .getSop(agent.id)
      .then((r: any) => setSop(r?.sop || '(无内容)'))
      .catch(() => setSop('(加载失败)'))
      .finally(() => setSopLoading(false));
  };

  const loadVersions = () => {
    if (!agent) return;
    setVersionsLoading(true);
    workspaceAgentApi
      .getVersions(agent.id)
      .then((r: any) => setVersions(r?.versions || []))
      .catch(() => setVersions([]))
      .finally(() => setVersionsLoading(false));
  };

  const handleRollback = async (version: string) => {
    if (!agent || !confirm(`回滚到版本 ${version}？`)) return;
    try {
      await workspaceAgentApi.rollbackVersion(agent.id, version);
      setVersions(null);
      loadVersions();
      toast.success('已回滚');
    } catch (e: any) {
      toast.error('回滚失败', e?.message || 'unknown');
    }
  };

  const loadHistory = () => {
    if (!agent) return;
    setHistoryLoading(true);
    workspaceAgentApi
      .getHistory(agent.id)
      .then((r: any) => setHistory(r?.history || []))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (key === 'docs' && sop === null && !sopLoading) loadSop();
    if (key === 'history') {
      if (history === null && !historyLoading) loadHistory();
      if (versions === null && !versionsLoading) loadVersions();
    }
  };

  if (!agent) return null;

  const statusCfg = listingStatusConfig[agent.status] || { cls: 'bg-gray-800 text-gray-400', text: agent.status };
  const skills = detail?.skills || agent.skills || [];
  const tools = detail?.tools || agent.tools || [];
  const mcpIds = (detail?.mcp_ids || (agent as any)?.mcp_ids || []) as string[];
  const workflowIds = (detail?.workflow_ids || (agent as any)?.workflow_ids || []) as string[];
  const boundAgentIds = (detail?.agent_ids || (agent as any)?.agent_ids || []) as string[];
  const config = (detail?.config || {}) as Record<string, unknown>;
  const displayName = detail?.display_name || agent.name;
  const description = detail?.description || '';
  const category = detail?.category || '';
  const tags: string[] = detail?.tags || [];
  const phase = detail?.phase || '';

  const model = String(config.model || detail?.model || (agent as any)?.model || '—');
  const systemPrompt = String(config.system_prompt || detail?.system_prompt || '');
  // plain compute — must NOT use hooks after `if (!agent) return null` above
  const otherConfig = Object.entries(config).filter(([k]) => k !== 'system_prompt' && k !== 'model');

  const resolveSkillName = (id: string) => skillMap[id] || id;
  const resolveToolName = (id: string) => {
    const desc = toolMap[id];
    if (!desc || desc === id) return id;
    // Prefer short label: take first clause of Chinese/English description
    const short = desc.split(/[（(·|]/)[0]?.trim() || desc;
    return short.length > 28 ? `${short.slice(0, 28)}…` : short;
  };

  const bindingTotal = skills.length + tools.length + mcpIds.length + workflowIds.length + boundAgentIds.length;

  const handlePublish = async () => {
    if (!agent || !pubName.trim()) {
      toast.error('请输入包名称');
      return;
    }
    setPubLoading(true);
    try {
      await packagesApi.publish(pubName.trim(), { source_path: `~/.aiplat/workspace/agents/${agent.id}` });
      toast.success(`已发布 ${pubName.trim()}`);
      setPublishOpen(false);
      setPubName('');
    } catch (e: any) {
      toast.error(`发布失败：${e?.message || e}`);
    } finally {
      setPubLoading(false);
    }
  };

  const handleSign = async () => {
    if (!agent?.id || !signKey.trim()) return;
    setSigning(true);
    setSignResult(null);
    try {
      const res = await workspaceAgentApi.sign(agent.id, { private_key: signKey.trim() });
      setSignResult(res.signature);
      toast.success('签名成功');
      setSignKey('');
    } catch (e: any) {
      toastGateError(e, '签名失败');
      setSignResult(null);
    } finally {
      setSigning(false);
    }
  };

  const overviewTab = (
    <div className="space-y-4">
      {description ? (
        <p className="text-sm text-gray-300 leading-relaxed">{description}</p>
      ) : (
        <p className="text-sm text-gray-500">暂无简介。职责与流程见「说明与配置」中的 AGENT.md。</p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
          <div className="text-[11px] text-gray-500 mb-1">ID</div>
          <div className="flex items-center gap-1.5">
            <code className="text-sm text-gray-100 font-mono truncate">{agent.id}</code>
            <button type="button" className="text-gray-500 hover:text-gray-300" onClick={() => copyText(agent.id)} title="复制 ID">
              <Copy className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
        <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
          <div className="text-[11px] text-gray-500 mb-1">类型</div>
          <div className="text-sm text-gray-100">{typeLabels[agent.agent_type] || agent.agent_type}</div>
        </div>
        <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
          <div className="text-[11px] text-gray-500 mb-1">上架状态</div>
          <span className={`inline-flex text-xs px-2 py-0.5 rounded ${statusCfg.cls}`}>{statusCfg.text}</span>
        </div>
        <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
          <div className="text-[11px] text-gray-500 mb-1">模型</div>
          <div className="text-sm text-gray-100 font-mono truncate" title={model}>
            {model}
          </div>
        </div>
      </div>

      {(category || phase || tags.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {category && (
            <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/25">
              {category}
            </span>
          )}
          {phase && (
            <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-amber-500/15 text-amber-300 border border-amber-500/25">
              {phase}
            </span>
          )}
          {tags.map((t: string) => (
            <span key={t} className="inline-flex px-2 py-0.5 rounded text-xs bg-gray-500/15 text-gray-400 border border-gray-500/25">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="p-3 rounded-lg border border-dark-border bg-dark-card">
        <div className="text-xs text-gray-400 mb-2">能力速览</div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center">
          {[
            { label: '技能', n: skills.length },
            { label: '工具', n: tools.length },
            { label: 'MCP', n: mcpIds.length },
            { label: 'Workflow', n: workflowIds.length },
            { label: '子 Agent', n: boundAgentIds.length },
          ].map((x) => (
            <div key={x.label} className="rounded bg-dark-bg border border-dark-border py-2">
              <div className="text-lg font-semibold text-gray-100">{x.n}</div>
              <div className="text-[11px] text-gray-500">{x.label}</div>
            </div>
          ))}
        </div>
        <div className="mt-2 text-[11px] text-gray-500">
          {bindingTotal > 0 ? '详情见「能力绑定」页签。' : '尚未绑定技能/工具等能力。'}
        </div>
      </div>
    </div>
  );

  const bindingsTab = (
    <div className="space-y-5">
      {bindingTotal === 0 ? (
        <div className="text-sm text-gray-500 py-6 text-center border border-dashed border-dark-border rounded-lg">
          暂未绑定技能、工具、MCP、Workflow 或子 Agent
        </div>
      ) : null}

      <div>
        <SectionTitle>技能 · {skills.length}</SectionTitle>
        {skills.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {skills.map((id: string) => (
              <BindingChip key={id} label={resolveSkillName(id)} id={id} tone="blue" />
            ))}
          </div>
        ) : (
          <div className="text-xs text-gray-500">无</div>
        )}
      </div>

      <div>
        <SectionTitle>工具 · {tools.length}</SectionTitle>
        {tools.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {tools.map((id: string) => (
              <BindingChip key={id} label={resolveToolName(id)} id={id} tone="purple" />
            ))}
          </div>
        ) : (
          <div className="text-xs text-gray-500">无</div>
        )}
      </div>

      <div>
        <SectionTitle>MCP · {mcpIds.length}</SectionTitle>
        {mcpIds.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {mcpIds.map((id: string) => (
              <BindingChip key={id} label={id} tone="emerald" />
            ))}
          </div>
        ) : (
          <div className="text-xs text-gray-500">无</div>
        )}
      </div>

      <div>
        <SectionTitle>Workflow · {workflowIds.length}</SectionTitle>
        {workflowIds.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {workflowIds.map((id: string) => (
              <BindingChip key={id} label={id} tone="orange" />
            ))}
          </div>
        ) : (
          <div className="text-xs text-gray-500">无</div>
        )}
      </div>

      <div>
        <SectionTitle>子 Agent · {boundAgentIds.length}</SectionTitle>
        {boundAgentIds.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {boundAgentIds.map((id: string) => (
              <BindingChip key={id} label={id} tone="rose" />
            ))}
          </div>
        ) : (
          <div className="text-xs text-gray-500">无</div>
        )}
      </div>
    </div>
  );

  const docsTab = (
    <div className="space-y-5">
      <div>
        <SectionTitle>运行配置</SectionTitle>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
          <div className="p-2.5 rounded-lg bg-dark-bg border border-dark-border text-xs">
            <span className="text-gray-500">model</span>
            <div className="text-gray-200 font-mono mt-0.5 break-all">{model}</div>
          </div>
          {otherConfig.slice(0, 6).map(([k, v]) => (
            <div key={k} className="p-2.5 rounded-lg bg-dark-bg border border-dark-border text-xs">
              <span className="text-gray-500">{k}</span>
              <div className="text-gray-200 mt-0.5 break-all">{String(v)}</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <SectionTitle
          extra={
            systemPrompt ? (
              <button
                type="button"
                className="text-xs text-blue-400 hover:text-blue-300"
                onClick={() => setPromptExpanded((v) => !v)}
              >
                {promptExpanded ? '收起' : '展开全文'}
              </button>
            ) : null
          }
        >
          系统提示词 (system_prompt)
        </SectionTitle>
        {systemPrompt ? (
          <pre
            className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto whitespace-pre-wrap leading-relaxed"
            style={{ maxHeight: promptExpanded ? 420 : 140 }}
          >
            {systemPrompt}
          </pre>
        ) : (
          <div className="text-xs text-gray-500">未配置 system_prompt（运行时可能回退到 AGENT.md / CLAUDE.md）</div>
        )}
      </div>

      <div>
        <SectionTitle
          extra={
            sop === null ? (
              <button type="button" onClick={loadSop} disabled={sopLoading} className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600">
                {sopLoading ? '加载中…' : '加载 AGENT.md'}
              </button>
            ) : (
              <button type="button" onClick={() => setSop(null)} className="text-xs text-gray-500 hover:text-gray-400">
                收起
              </button>
            )
          }
        >
          AGENT.md（工作流程说明）
        </SectionTitle>
        {sop !== null ? (
          <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto whitespace-pre-wrap leading-relaxed" style={{ maxHeight: 360 }}>
            {sop}
          </pre>
        ) : (
          <div className="text-xs text-gray-500">点击「加载 AGENT.md」查看 SOP / 目标 / 权限说明。</div>
        )}
      </div>
    </div>
  );

  const historyTab = (
    <div className="space-y-6">
      <div>
        <SectionTitle
          extra={
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={loadHistory}
                disabled={historyLoading}
                className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600"
              >
                {historyLoading ? '刷新中…' : '刷新'}
              </button>
            </div>
          }
        >
          最近执行
        </SectionTitle>
        {historyLoading && history === null ? (
          <div className="text-xs text-gray-500 py-3">加载执行记录…</div>
        ) : history !== null && history.length === 0 ? (
          <div className="text-xs text-gray-500 py-3">暂无执行记录</div>
        ) : history !== null ? (
          <div className="space-y-2 max-h-72 overflow-auto">
            {history.slice(0, 12).map((h: any, i: number) => {
              const st = String(h.status || 'unknown').toLowerCase();
              const sc = runStatusConfig[st] || { cls: 'bg-gray-800 text-gray-300', text: st };
              const eid = String(h.execution_id || h.id || '');
              const dur = formatDuration(h.duration_ms);
              return (
                <div key={eid || i} className="p-2.5 rounded-lg bg-dark-card border border-dark-border text-xs">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <code className="text-gray-400 font-mono truncate" title={eid}>
                      {eid ? `${eid.slice(0, 18)}${eid.length > 18 ? '…' : ''}` : '—'}
                    </code>
                    <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] ${sc.cls}`}>{sc.text}</span>
                  </div>
                  <div className="text-gray-300 truncate mb-1.5" title={summarizeInput(h.input)}>
                    {summarizeInput(h.input)}
                  </div>
                  <div className="flex items-center justify-between gap-2 text-[11px] text-gray-500">
                    <span>
                      {formatTs(h.start_time || h.created_at)}
                      {dur ? ` · ${dur}` : ''}
                    </span>
                    {eid ? (
                      <a
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                        href={`/diagnostics/links?execution_id=${encodeURIComponent(eid)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        诊断 <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-xs text-gray-500 py-3">切换到此页签后自动加载。</div>
        )}
      </div>

      <div>
        <SectionTitle
          extra={
            <button type="button" onClick={loadVersions} disabled={versionsLoading} className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600">
              {versionsLoading ? '刷新中…' : '刷新'}
            </button>
          }
        >
          版本历史
        </SectionTitle>
        {versions !== null && versions.length > 0 ? (
          <div className="space-y-1 max-h-40 overflow-auto">
            {versions.map((v, i) => (
              <div key={i} className="flex items-center justify-between text-xs py-1.5 px-2 rounded bg-dark-card border border-dark-border gap-2">
                <span className="text-gray-300 font-mono">{v.version}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${v.status === 'current' ? 'bg-green-900/50 text-green-300' : 'bg-gray-700/50 text-gray-400'}`}>
                  {v.status === 'current' ? '当前' : v.status || '历史'}
                </span>
                <span className="text-gray-500 flex-1 text-right truncate">{v.created_at?.slice?.(0, 19) || ''}</span>
                {v.status !== 'current' && (
                  <button type="button" onClick={() => handleRollback(v.version)} className="text-amber-400 hover:text-amber-300 shrink-0">
                    回滚
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : versions !== null ? (
          <div className="text-xs text-gray-500">暂无版本记录</div>
        ) : (
          <div className="text-xs text-gray-500">切换到此页签后自动加载。</div>
        )}
      </div>
    </div>
  );

  const govTab = (
    <div className="space-y-5">
      <div className="p-3 rounded-lg border border-dark-border bg-dark-card text-xs text-gray-400 leading-relaxed">
        签名与发布属于上架/分发能力，日常运行 Agent 不需要操作这里。开发自测可直接执行；对外发布前再完成签名。
        「生成密钥」只会打开签名密钥一步，不必做完整初始化向导。
      </div>

      <div>
        <SectionTitle>Ed25519 签名</SectionTitle>
        {signResult ? (
          <div className="flex items-center gap-2 text-green-400 text-xs">
            <span>✓</span>
            <span className="font-mono">{signResult.slice(0, 24)}…</span>
            <button type="button" onClick={() => setSignResult(null)} className="text-gray-500 hover:text-gray-300 ml-2">
              重新签名
            </button>
          </div>
        ) : (
          <div className="flex items-start gap-2">
            <textarea
              className="flex-1 h-16 px-3 py-2 bg-dark-card border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
              placeholder="粘贴 Ed25519 私钥 PEM（仅本地签名，不会用于日常执行）"
              value={signKey}
              onChange={(e) => setSignKey(e.target.value)}
            />
            <div className="flex flex-col gap-1">
              <Button size="sm" onClick={handleSign} disabled={!signKey.trim() || signing} loading={signing}>
                签名
              </Button>
              <button
                type="button"
                className="px-2 py-1 rounded text-xs text-gray-500 hover:text-gray-300"
                onClick={() => {
                  try {
                    window.open('/onboarding?step=sign_keys', '_blank', 'noopener,noreferrer');
                  } catch {
                    /* ignore */
                  }
                }}
              >
                生成密钥
              </button>
            </div>
          </div>
        )}
      </div>

      <div>
        <SectionTitle>发布到商城</SectionTitle>
        <Button variant="secondary" size="sm" onClick={() => setPublishOpen(true)}>
          打包发布…
        </Button>
      </div>
    </div>
  );

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={displayName}
        width={820}
        footer={
          <>
            <Button variant="secondary" onClick={() => setActiveTab('gov')}>
              治理 / 发布
            </Button>
            <Button onClick={onClose}>关闭</Button>
          </>
        }
      >
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="text-gray-400">加载中…</div>
          </div>
        ) : (
          <Tabs
            key={agent.id}
            defaultActiveKey={activeTab}
            onChange={handleTabChange}
            className="agent-detail-tabs"
            tabs={[
              { key: 'overview', label: '概览', children: overviewTab },
              { key: 'bindings', label: `能力绑定 (${bindingTotal})`, children: bindingsTab },
              { key: 'docs', label: '说明与配置', children: docsTab },
              { key: 'history', label: '历史', children: historyTab },
              { key: 'gov', label: '治理', children: govTab },
            ]}
          />
        )}
      </Modal>

      <Modal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        title="发布到商城"
        width={440}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPublishOpen(false)}>
              取消
            </Button>
            <Button variant="primary" loading={pubLoading} onClick={handlePublish}>
              发布
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="text-sm text-gray-300">
            将当前 Agent（<span className="text-primary">{agent?.name}</span>）打包发布到商城。
          </div>
          <Input label="包名称" value={pubName} onChange={(e) => setPubName(e.target.value)} placeholder={agent?.id || 'my-agent-package'} />
          <div className="text-xs text-gray-500">发布后可在商城的「已发布包」Tab 中查看和安装</div>
        </div>
      </Modal>
    </>
  );
};

export default AgentDetailModal;
