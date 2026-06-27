import React, { useEffect, useState } from 'react';

import { Button, Modal, Textarea, toast } from '../ui';
import { workspaceSkillApi } from '../../services';
import { toastGateError } from '../ui';
import './TraceFlowGraph';
import ExecutionViewer, { StructuredDetail } from '../ExecutionViewer/ExecutionViewer';

interface ExecuteSkillModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

// ── StructuredSkillOutput — renders markdown engine output as sectioned cards ──

const StructuredSkillOutput: React.FC<{ text: string }> = ({ text }) => {
  if (!text) return <div className="text-xs text-gray-500">(空)</div>;

  // Clean up HTML comments and engine internal instructions
  text = text.replace(/<!--[\s\S]*?-->/g, '');
  text = text.replace(/(?:# END OF last30days|Pass through ONLY the PASS-THROUGH|Do not append a trailing|If your response contains)[\s\S]*$/i, '');

  // Split by ## headings, keep heading as part of section content
  const rawSections = text.split(/(^##\s+[^\n]*$)/m);
  
  // Collect sections with their headings
  const headed: { heading: string; body: string }[] = [];
  for (let i = 1; i < rawSections.length; i += 2) {
    const heading = (rawSections[i] || '').replace(/^##\s+/, '').trim();
    const body = (rawSections[i + 1] || '').trim();
    headed.push({ heading, body });
  }

  // Determine icon/label/collapsible from heading
  const classify = (h: string, b: string) => {
    const hl = h.toLowerCase();
    if (!b.trim()) return null; // skip empty sections
    if (hl.includes('warning') || hl.includes('degraded') || hl.includes('pre-research') || hl.includes('警告'))
      return { icon: '⚠️', label: '警告', collapsible: true, color: 'border-amber-500/30 bg-amber-500/5' };
    if (hl.includes('ranked evidence') || hl.includes('cluster'))
      return { icon: '📊', label: '搜索结果', collapsible: true, color: 'border-blue-500/30 bg-blue-500/5' };
    if (hl.includes('stats') || hl.includes('source coverage') || hl.includes('统计'))
      return { icon: '📈', label: '统计', collapsible: true, color: 'border-emerald-500/30 bg-emerald-500/5' };
    return { icon: '📋', label: h, collapsible: true, color: '' };
  };

  // Build classified sections, merging adjacent same-icon ones
  const classified = headed
    .map(h => ({ ...h, ...(classify(h.heading, h.body) || {}) }))
    .filter((h: any) => h.icon);

  // Merge adjacent sections with same icon
  const merged: any[] = [];
  for (const c of classified) {
    const prev = merged[merged.length - 1];
    if (prev && prev.icon === c.icon) {
      prev.body += '\n\n## ' + c.heading + '\n' + c.body;
    } else {
      merged.push({ ...c });
    }
  }

  // Extract overview: first section is before any ##
  const firstH2Idx = text.search(/\n##\s+/m);
  const overview = firstH2Idx > 0 ? text.slice(0, firstH2Idx).trim() : (merged.length === 0 ? text.trim() : '');

  // Build cards list
  const cards: { icon: string; label: string; body: string; collapsible: boolean; color: string }[] = [];
  
  // Overview card (extract badge + date + sources)
  if (overview) {
    const badgeMatch = overview.match(/^(🌐\s*last30days[^\n]*)/m);
    const dateMatch = overview.match(/Date range:\s*([^\n]+)/);
    const sourcesMatch = overview.match(/- Sources:\s*([^\n]+)/);
    const summaryLines = [badgeMatch?.[1], dateMatch?.[0], sourcesMatch?.[0]].filter(Boolean).join('\n');
    const rest = overview.replace(badgeMatch?.[0] || '', '').replace(dateMatch?.[0] || '', '').replace(sourcesMatch?.[0] || '', '').replace(/\n{3,}/g, '\n\n').trim();
    cards.push({
      icon: '🌐',
      label: '概览',
      body: summaryLines + (rest ? '\n\n' + rest : ''),
      collapsible: false,
      color: 'border-sky-500/30 bg-sky-500/5',
    });
  }

  // Section cards
  for (const c of merged) {
    cards.push({
      icon: c.icon,
      label: c.label,
      body: c.body,
      collapsible: c.collapsible,
      color: c.color,
    });
  }

  // Footer: extract ✅ All agents block
  const footerMatch = text.match(/^(✅\s*All agents[^\n]*\n(?:[├└─│].*\n?)*)/m);
  if (footerMatch) {
    cards.push({
      icon: '🦶',
      label: 'Footer',
      body: footerMatch[1].trim(),
      collapsible: true,
      color: 'border-gray-500/30 bg-gray-500/5',
    });
  }

  if (cards.length === 0) {
    return <div className="text-xs text-gray-300 whitespace-pre-wrap">{text.slice(0, 2000)}</div>;
  }

  const Card: React.FC<{ icon: string; label: string; body: string; collapsible: boolean; color: string }> = ({ icon, label, body, collapsible, color }) => {
    const [expanded, setExpanded] = useState(!collapsible);
    return (
      <div className={`rounded-lg border ${color || 'border-dark-border'} p-3`}>
        <div className="flex items-center gap-2 mb-2" onClick={collapsible ? () => setExpanded(!expanded) : undefined} style={{ cursor: collapsible ? 'pointer' : 'default' }}>
          <span className="text-sm">{icon}</span>
          <span className="text-xs font-semibold text-gray-200">{label}</span>
          {collapsible && <span className="text-xs text-gray-500 ml-auto">{expanded ? '▼' : '▶'}</span>}
        </div>
        {(!collapsible || expanded) && (
          <div className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">{body}</div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-2 max-h-80 overflow-y-auto">
      {cards.map((c, i) => <Card key={i} {...c} />)}
    </div>
  );
};

const ExecuteSkillModal: React.FC<ExecuteSkillModalProps> = ({ open, skill, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: string; run_id?: string; output?: unknown; error?: any; error_message?: string; error_detail?: any; duration_ms?: number; tokens?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } } | null>(null);
  const [inputText, setInputText] = useState('');
  const [helpLoading, setHelpLoading] = useState(false);
  const [helpMarkdown, setHelpMarkdown] = useState<string>('');
  const [examples, setExamples] = useState<Array<{ title: string; content: string }>>([]);
  const [toolset, setToolset] = useState<string>('workspace_default');
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [selectedFlowNode, setSelectedFlowNode] = useState<any>(null);

  // Poll for result when streaming (POST returns immediately with run_id)
  useEffect(() => {
    const r = result as any;
    if (!r || (r.status !== 'running' && r.status !== 'accepted') || !r.run_id || !skill) return;
    const runId = r.run_id;
    let attempts = 0;
    const MAX_ATTEMPTS = 90; // 90 seconds timeout
    const timer = setInterval(async () => {
      attempts++;
      if (attempts > MAX_ATTEMPTS) {
        clearInterval(timer);
        setResult({ status: 'failed', error: '执行超时', run_id: runId });
        return;
      }
      try {
        const resp = await fetch(`/api/core/syscalls/events?run_id=${encodeURIComponent(runId)}&limit=20`);
        const data = await resp.json();
        const items = data?.items || data?.events || [];
        // API returns 'result' (parsed object), not 'result_json' (raw string)
        const done = items.find((e: any) =>
          (e.status === 'success' || e.status === 'ok') && e.kind === 'skill' && e.result
        );
        if (done) {
          setResult({
            status: 'completed',
            output: done.result?.output || done.result,
            duration_ms: done.duration_ms,
            run_id: runId,
          });
          clearInterval(timer);
        } else if (items.some((e: any) => e.status === 'failed' || e.status === 'error')) {
          const failed = items.find((e: any) => e.status === 'failed' || e.status === 'error');
          setResult({ status: 'failed', error: failed?.error || '执行失败', run_id: runId });
          clearInterval(timer);
        }
      } catch { /* keep polling */ }
    }, 1000);
    return () => clearInterval(timer);
  }, [(result as any)?.run_id, (result as any)?.status]);

  useEffect(() => {
    const load = async () => {
      if (!open || !skill) return;
      setHelpLoading(true);
      try {
        const res = await workspaceSkillApi.getExecutionHelp(skill.id);
        setHelpMarkdown(String((res as any)?.help_markdown || ''));
        setExamples(((res as any)?.examples || []) as any);
      } catch {
        setHelpMarkdown('');
        setExamples([]);
      } finally {
        setHelpLoading(false);
      }
    };
    load();
  }, [open, skill?.id]);

  const handleExecute = async () => {
    if (!skill) return;
    try {
      setLoading(true);
      setResult(null);

      let payload: Record<string, unknown> = {};
      if (inputText.trim()) {
        try {
          payload = JSON.parse(inputText);
        } catch {
          payload = { message: inputText };
        }
      }

      const streamOpts = { ...((payload.options || {}) as Record<string, unknown>), toolset, stream: true };
      const res = await workspaceSkillApi.execute(skill.id, { input: payload, options: streamOpts, config: (payload.config || {}) as Record<string, unknown> });
      setResult(res as any);
      const status = String((res as any)?.status || '');
      const legacyStatus = String((res as any)?.legacy_status || '');
      const errCode = String((res as any)?.error?.code || '');
      const runId = (res as any)?.run_id || (res as any)?.execution_id;

      if (legacyStatus === 'queued') {
        toast.success('已排队');
      } else if ((status === 'waiting_approval' || legacyStatus === 'approval_required' || errCode === 'APPROVAL_REQUIRED')) {
        const approvalId = (res as any)?.approval_request_id || (res as any)?.error?.detail?.approval_request_id;
        toast.error(`需要审批：${String(approvalId || '').slice(0, 10)}`);
        try { window.open('/core/approvals', '_blank', 'noopener,noreferrer'); } catch {}
      } else if (legacyStatus === 'publish_required' || errCode === 'PUBLISH_REQUIRED') {
        const cid = (res as any)?.candidate_id || (res as any)?.error?.detail?.candidate_id;
        toast.error(`需要发布候选：${String(cid || '').slice(0, 10)}...`);
        try { window.open('/core/learning/releases', '_blank', 'noopener,noreferrer'); } catch {}
      }

      // Open fullscreen flow immediately when streaming
      if (runId && (status === 'running' || status === 'completed' || status === 'accepted')) {
        setFlowFullscreen(true);
      }
      if (status === 'completed') {
        toast.success('执行成功');
      }
    } catch (error: any) {
      toastGateError(error, '执行失败');
      setResult({ status: 'error', error: error.message || 'Unknown error' });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    setInputText('');
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={`执行 Skill: ${skill?.name || ''}`}
      width={980}
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={loading}>
            关闭
          </Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>
            执行
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="mb-3">
            <div className="text-sm font-medium text-gray-300 mb-2">Toolset（运行时工具集）</div>
            <select
              value={toolset}
              onChange={(e) => setToolset(e.target.value)}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
              disabled={loading}
            >
              <option value="safe_readonly">safe_readonly（只读）</option>
              <option value="workspace_default">workspace_default（默认）</option>
              <option value="browser">browser（浏览器/HTTP）</option>
              <option value="full">full（全量/高风险）</option>
            </select>
            <div className="text-xs text-gray-500 mt-1">
              提示：toolset 在服务端强制生效；不在白名单内的工具调用会被 sys_tool_call 拦截并记录到诊断。
            </div>
          </div>
          <Textarea
            label="输入（JSON 或文本）"
            rows={12}
            value={inputText}
            onChange={(e: any) => setInputText(e.target.value)}
            placeholder='{"query": "搜索关键词"} 或直接输入文本'
          />
          <div className="text-xs text-gray-500 mt-2">
            提示：如果输入不是合法 JSON，会自动封装为 {"{ \"message\": \"...\" }"} 传给 Skill。
          </div>
        </div>
        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium text-gray-200">使用说明 / 示例</div>
            <div className="text-xs text-gray-500">{helpLoading ? '加载中...' : ''}</div>
          </div>

          {helpMarkdown ? (
            <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed mb-3">
              {helpMarkdown}
            </div>
          ) : (
            <div className="text-xs text-gray-500 mb-3">暂无说明。</div>
          )}

          {examples.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-gray-300">一键填入示例</div>
              <div className="flex flex-col gap-2">
                {examples.map((ex, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-2">
                    <div className="text-xs text-gray-300 truncate">{ex.title}</div>
                    <div className="flex gap-2">
                      <Button variant="secondary" onClick={() => setInputText(ex.content)} disabled={loading}>
                        填入
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(ex.content);
                            toast.success('已复制');
                          } catch {
                            toast.error('复制失败');
                          }
                        }}
                        disabled={loading}
                      >
                        复制
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {result && (
        <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-100">执行结果</span>
            <span className={`text-xs px-2 py-0.5 rounded ${result.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
              {result.status}
            </span>
            {result.tokens && (
              <span className="text-xs text-gray-400 ml-3">
                Token: {result.tokens.total_tokens?.toLocaleString() || '-'}
                <span className="text-gray-500 ml-1">
                  (Prompt {result.tokens.prompt_tokens?.toLocaleString() || '-'} + Output {result.tokens.completion_tokens?.toLocaleString() || '-'})
                </span>
              </span>
            )}
          </div>
          {result.duration_ms != null && <div className="text-xs text-gray-400 mb-2">耗时: {result.duration_ms}ms</div>}
          {result.output !== undefined && result.output !== null && (
            (() => {
              const out = result.output;
              // Unwrap handler output: {topic, output, success, ...} → extract .output string
              if (typeof out === 'object' && out !== null && typeof (out as any).output === 'string') {
                return <StructuredSkillOutput text={(out as any).output} />;
              }
              if (typeof out === 'string') {
                return <StructuredSkillOutput text={out} />;
              }
              return <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">{JSON.stringify(out as object, null, 2)}</pre>;
            })()
          )}
          {(((result as any).error || (result as any).error_message || (result as any)?.error_detail?.message) && !result.output) && (
            <div className="text-xs text-red-300 mt-2">
              {(() => {
                const errObj =
                  (result as any).error_detail || (typeof (result as any).error === 'object' ? (result as any).error : null);
                const errMsg =
                  (result as any).error_message ||
                  (typeof (result as any).error === 'string' ? (result as any).error : '') ||
                  (errObj?.message ? String(errObj.message) : '');
                const errCode = errObj?.code ? String(errObj.code) : '';
                return `${errCode ? `[${errCode}] ` : ''}${errMsg}`;
              })()}
            </div>
          )}

          {(result as any)?.run_id && (
            <div className="mt-3 flex items-center gap-3">
              <Button variant="primary" onClick={() => setFlowFullscreen(true)} disabled={loading}>
                ▶ 查看执行流程（全屏）
              </Button>
            </div>
          )}

          {(result as any)?.execution_id && (
            <div className="mt-3 flex items-center justify-end">
              <Button
                variant="secondary"
                onClick={() => {
                  const url = `/diagnostics/links?execution_id=${encodeURIComponent(String((result as any).execution_id))}`;
                  window.open(url, '_blank', 'noopener,noreferrer');
                }}
                disabled={loading}
              >
                查看诊断详情
              </Button>
            </div>
          )}
        </div>
      )}

      {/* ── 全屏执行流程弹窗 ── */}
      {flowFullscreen && result && (result as any)?.run_id && (
        <div className="fixed inset-0 z-[60] bg-dark-bg flex flex-col">
          <div className="h-10 flex items-center justify-between px-4 border-b border-dark-border bg-dark-card flex-shrink-0">
            <span className="text-sm font-medium text-gray-200">
              ▶ 执行流程 · {skill?.name || 'Skill'}
              {result.duration_ms != null && <span className="text-gray-500 ml-2 text-xs">({result.duration_ms}ms)</span>}
            </span>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded ${result.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
                {result.status}
              </span>
              <Button variant="secondary" onClick={() => setFlowFullscreen(false)}>✕ 关闭</Button>
            </div>
          </div>
          <div className="flex-1 flex flex-col overflow-hidden">
            <ExecutionViewer
              runId={String((result as any).run_id)}
              live={true}
              title=""
              height={window.innerHeight - 180}
              onNodeClick={(node: any) => setSelectedFlowNode(node)}
            />
          </div>
          {/* Node detail panel (fixed at bottom, uses full StructuredDetail) */}
          {selectedFlowNode && (
            <div className="fixed bottom-0 left-0 right-0 z-[70] border-t border-dark-border bg-dark-card p-4 max-h-72 overflow-y-auto shadow-2xl">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold" style={{ color: selectedFlowNode.color || '#e5e7eb' }}>
                  {selectedFlowNode.icon} {selectedFlowNode.name}
                </span>
                <button onClick={() => setSelectedFlowNode(null)} className="text-gray-500 hover:text-gray-300 text-lg">✕</button>
              </div>
              <div className="flex gap-4 text-xs mb-3">
                <span className="text-gray-400">类型: {selectedFlowNode.type}</span>
                <span className="text-gray-400">状态: {selectedFlowNode.status}</span>
                {selectedFlowNode.duration ? <span className="text-gray-400">耗时: {selectedFlowNode.duration}ms</span> : null}
              </div>
              <StructuredDetail node={selectedFlowNode} />
            </div>
          )}
          {result.status === 'running' && (
            <div className="flex-shrink-0 border-t border-dark-border bg-dark-card p-4 text-center">
              <span className="text-sm text-blue-400 animate-pulse">⏳ 执行中...</span>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteSkillModal;
