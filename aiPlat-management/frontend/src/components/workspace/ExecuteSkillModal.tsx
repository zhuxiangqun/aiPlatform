import React, { useEffect, useMemo, useState } from 'react';

import { Button, Modal, Textarea, toast } from '../ui';
import { workspaceSkillApi } from '../../services';
import { toastGateError } from '../ui';
import './TraceFlowGraph';
import { buildExamplesFromSchema, isGenericExampleSet } from '../../utils/executionSamples';
import ExecuteResultPanel from '../execution/ExecuteResultPanel';
import ExecuteFlowFullscreen from '../execution/ExecuteFlowFullscreen';
import { RunVerdictBanner, deriveRunVerdict, outputAsText } from '../execution/runVerdict';
import { ArtifactDownloadBar, coerceSkillEnvelope, skillOutputDisplayText } from '../execution/artifactDownloads';
import {
  isSkillRunInFlight,
  normalizeSkillExecuteResult as normalizeSkillExecuteResultBase,
  shouldOpenSkillFlow,
} from '../../utils/skillExecute';
import { pollSkillExecutionUntilDone } from '../../utils/pollSkillExecution';

function normalizeSkillExecuteResult(res: any) {
  const n = normalizeSkillExecuteResultBase(res);
  return { ...n, output: coerceSkillEnvelope(n.output) };
}

interface ExecuteSkillModalProps {
  open: boolean;
  skill: { id: string; name: string; input_schema?: Record<string, unknown> | null } | null;
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
  const [llmGenerating, setLlmGenerating] = useState(false);

  const displayVerdict = useMemo(
    () =>
      result
        ? deriveRunVerdict({
            status: result.status,
            error: result.error_message || result.error,
            outputText: skillOutputDisplayText(result.output) || outputAsText(result.output),
          })
        : null,
    [result],
  );

  // Poll for result when stream mode returns immediately with run_id
  useEffect(() => {
    if (!result || !isSkillRunInFlight(result.status) || !result.run_id || !skill) return;
    const runId = result.run_id;
    let stopped = false;
    (async () => {
      const done = await pollSkillExecutionUntilDone(runId, { isStopped: () => stopped });
      if (stopped) return;
      setResult(
        normalizeSkillExecuteResult({
          ...done,
          run_id: runId,
          execution_id: runId,
        }),
      );
      if (done.status === 'completed') toast.success('执行成功');
      else if (done.status === 'failed' || done.status === 'error') toast.error('执行失败');
    })();
    return () => {
      stopped = true;
    };
  }, [(result as any)?.run_id, (result as any)?.status]);

  useEffect(() => {
    const load = async () => {
      if (!open || !skill) return;
      setHelpLoading(true);
      setInputText('');
      setResult(null);
      try {
        const res = await workspaceSkillApi.getExecutionHelp(skill.id);
        setHelpMarkdown(String((res as any)?.help_markdown || ''));
        let exs = (((res as any)?.examples || []) as Array<{ title: string; content: string }>);
        const schema =
          ((res as any)?.input_schema as Record<string, unknown> | null) ||
          skill.input_schema ||
          null;
        // Prefer schema-based cases when API still returns generic 通用 chips
        if (isGenericExampleSet(exs) && schema && Object.keys(schema).length > 0) {
          const generated = buildExamplesFromSchema(schema, skill.name || skill.id, {
            skillHint: `${skill.id || ''} ${skill.name || ''}`,
          });
          if (generated.length > 0) exs = generated;
        }
        setExamples(exs);
        // Do NOT auto-fill — user clicks「填入」
      } catch {
        // Offline / help failed: still try local schema from skill list row
        const generated = skill.input_schema
          ? buildExamplesFromSchema(skill.input_schema, skill.name || skill.id, {
              skillHint: `${skill.id || ''} ${skill.name || ''}`,
            })
          : [];
        setHelpMarkdown('');
        setExamples(generated);
      } finally {
        setHelpLoading(false);
      }
    };
    load();
  }, [open, skill?.id]);

  const handleGenerateLlmExamples = async (persist: boolean) => {
    if (!skill) return;
    try {
      setLlmGenerating(true);
      const res = await workspaceSkillApi.generateExecutionExamples(skill.id, { persist });
      const exs = (res?.examples || []) as Array<{ title: string; content: string }>;
      if (!exs.length) {
        toast.error('未生成可用用例');
        return;
      }
      setExamples(exs);
      if (exs[0]?.content) setInputText(exs[0].content);
      const src = res?.source === 'llm' ? 'LLM' : '启发式回退';
      if (persist && res?.persisted) {
        toast.success(`已生成 ${exs.length} 条（${src}）并写入 SKILL.md`);
      } else if (persist && !res?.persisted) {
        toast.warning(`已生成 ${exs.length} 条，但写入 SKILL.md 失败`);
      } else {
        toast.success(`已生成 ${exs.length} 条（${src}），已填入第一条`);
      }
      if (res?.warning) toast.warning(String(res.warning));
    } catch (e: any) {
      toastGateError(e, 'LLM 生成用例失败');
    } finally {
      setLlmGenerating(false);
    }
  };

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

      const streamOpts = {
        ...((payload.options || {}) as Record<string, unknown>),
        toolset,
        // stream/trial 由 workspaceSkillApi.execute → withSkillExecuteDefaults 统一注入
      };
      const res = await workspaceSkillApi.execute(skill.id, { input: payload, options: streamOpts, config: (payload.config || {}) as Record<string, unknown> });
      const normalized = normalizeSkillExecuteResult(res);
      setResult(normalized);
      const status = String(normalized.status || '');
      const legacyStatus = String((res as any)?.legacy_status || '');
      const errCode = String((res as any)?.error?.code || '');
      const runId = normalized.run_id || normalized.execution_id;

      if (legacyStatus === 'queued') {
        toast.success('已排队');
      } else if ((status === 'waiting_approval' || legacyStatus === 'approval_required' || errCode === 'APPROVAL_REQUIRED')) {
        const approvalId = (res as any)?.approval_request_id || (res as any)?.error?.detail?.approval_request_id;
        const reason = String((res as any)?.error?.detail?.reason || (res as any)?.error?.reason || '');
        const reasonHint =
          reason === 'no_trusted_key_matched'
            ? '已签名但公钥未匹配（≠已验签）。请用当前可信私钥在详情「治理」重新签名，或走审批单。'
            : reason === 'no_trusted_keys'
              ? '系统尚未配置可信公钥。请先在初始化向导生成签名密钥。'
              : '「已签名」只表示写过签名；「已验签」才表示公钥校验通过。';
        toast.error(
          '签名未验签，正式执行需治理审批',
          approvalId
            ? `${reasonHint} 审批单 ${String(approvalId).slice(0, 12)}…`
            : reasonHint,
        );
        // 不再自动跳转审批页，避免「点执行却进审批中心」
      } else if (legacyStatus === 'publish_required' || errCode === 'PUBLISH_REQUIRED') {
        const cid = (res as any)?.candidate_id || (res as any)?.error?.detail?.candidate_id;
        toast.error(
          '需要先发布治理候选',
          cid ? `candidate ${String(cid).slice(0, 12)}…` : '请到学习/发布页处理候选版本',
        );
      }

      // 有 run_id 立刻打开流程（stream 下 status=running，可边跑边看）
      if (runId && shouldOpenSkillFlow(status)) {
        setFlowFullscreen(true);
      }
      // 同步完成路径才在这里 toast；stream 完成由轮询通知
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
          {(() => {
            const prov = (skill as any)?.metadata?.provenance || {};
            if (prov?.signature && prov?.signature_verified !== true) {
              const reason = String(prov?.signature_verified_reason || '');
              return (
                <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90">
                  治理列「已签名」≠「已验签」。当前公钥未匹配
                  {reason ? `（${reason}）` : ''}
                  。本机「执行」按试跑放行；要变成已验签：详情 → 治理 → 用<strong>当前</strong>可信私钥重新签名。
                </div>
              );
            }
            return null;
          })()}
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
            placeholder='点右侧「填入」加载测试用例，或直接输入 JSON / 文本'
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
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-medium text-gray-300">测试用例 — 点「填入」写入左侧输入框</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={llmGenerating}
                  disabled={loading || llmGenerating}
                  onClick={() => handleGenerateLlmExamples(false)}
                  title="用 LLM 生成更贴合本 Skill 的冒烟用例（可选，不替换默认启发式）"
                >
                  ✨ LLM 生成
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  loading={llmGenerating}
                  disabled={loading || llmGenerating}
                  onClick={() => handleGenerateLlmExamples(true)}
                  title="生成后写入 SKILL.md 的 execution_examples，下次打开优先使用"
                >
                  生成并保存
                </Button>
              </div>
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
          {examples.length === 0 && !helpLoading && (
            <div className="space-y-2">
              <div className="text-xs text-gray-500">暂无测试用例。</div>
              <Button
                variant="secondary"
                size="sm"
                loading={llmGenerating}
                disabled={loading || llmGenerating}
                onClick={() => handleGenerateLlmExamples(false)}
              >
                ✨ LLM 生成用例
              </Button>
            </div>
          )}
        </div>
      </div>

      {result && (
        <ExecuteResultPanel
          result={result as any}
          loading={loading}
          onOpenFlow={result.run_id ? () => setFlowFullscreen(true) : undefined}
          renderOutput={(text) => (text ? <StructuredSkillOutput text={text} /> : null)}
        />
      )}

      <ExecuteFlowFullscreen
        open={!!(flowFullscreen && result?.run_id)}
        runId={String(result?.run_id || '')}
        title={`执行流程 · ${skill?.name || 'Skill'}`}
        verdict={displayVerdict}
        status={result?.status}
        running={isSkillRunInFlight(String(result?.status || ''))}
        onClose={() => setFlowFullscreen(false)}
        footer={
          result && displayVerdict ? (
            <div className="space-y-2">
              <RunVerdictBanner verdict={displayVerdict} />
              <ArtifactDownloadBar raw={result.output} />
              {skillOutputDisplayText(result.output) ? (
                <div className="text-xs text-gray-300 overflow-auto max-h-48">
                  <StructuredSkillOutput text={skillOutputDisplayText(result.output)} />
                </div>
              ) : null}
            </div>
          ) : null
        }
      />
    </Modal>
  );
};

export default ExecuteSkillModal;
