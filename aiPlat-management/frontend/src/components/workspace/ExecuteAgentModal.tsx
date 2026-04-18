import React, { useEffect, useState } from 'react';
import { workspaceAgentApi } from '../../services/coreApi';
import type { Agent } from '../../services';
import { Button, Modal, Textarea, toast } from '../ui';

interface ExecuteAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const ExecuteAgentModal: React.FC<ExecuteAgentModalProps> = ({ open, agent, onClose }) => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [helpLoading, setHelpLoading] = useState(false);
  const [helpMarkdown, setHelpMarkdown] = useState<string>('');
  const [examples, setExamples] = useState<Array<{ title: string; content: string }>>([]);
  const [result, setResult] = useState<{ status: string; execution_id?: string; output?: unknown; error?: string; error_detail?: any } | null>(null);
  const [toolset, setToolset] = useState<string>('workspace_default');

  useEffect(() => {
    const load = async () => {
      if (!open || !agent) return;
      // default toolset from agent metadata if present
      try {
        const t = String((agent as any)?.metadata?.toolset || '');
        if (t) setToolset(t);
        else setToolset('workspace_default');
      } catch {
        setToolset('workspace_default');
      }
      setHelpLoading(true);
      try {
        const res = await workspaceAgentApi.getExecutionHelp(agent.id);
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
  }, [open, agent?.id]);

  const handleExecute = async () => {
    if (!agent) return;
    let parsedInput: Record<string, unknown> = {};
    if (input.trim()) {
      try {
        parsedInput = JSON.parse(input);
      } catch {
        parsedInput = { message: input };
      }
    }
    setLoading(true);
    try {
      const result = await workspaceAgentApi.execute(agent.id, { input: parsedInput, options: { toolset } });
      const status = String((result as any)?.status || 'ok');
      const execution_id = (result as any)?.execution_id ? String((result as any).execution_id) : undefined;
      setResult({ status, execution_id, output: (result as any)?.output, error: (result as any)?.error, error_detail: (result as any)?.error_detail });
      toast.success(status === 'success' || status === 'completed' ? '执行成功' : `状态: ${status}`);
    } catch (e: any) {
      const msg = String(e?.message || e?.detail || '执行失败');
      setResult({ status: 'failed', error: msg });
      toast.error('执行失败', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); setInput(''); }}
      title={`执行 Agent: ${agent?.name || ''}`}
      width={980}
      footer={
        <>
          <Button variant="secondary" onClick={() => { onClose(); setInput(''); setResult(null); }} disabled={loading}>关闭</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
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
              <option value="full">full（全量/高风险）</option>
            </select>
            <div className="text-xs text-gray-500 mt-1">
              提示：toolset 在服务端强制生效；不在白名单内的工具调用会被 sys_tool_call 拦截并记录到诊断。
            </div>
          </div>
          <Textarea
            label="输入（JSON 或文本）"
            rows={14}
            value={input}
            onChange={(e: any) => setInput(e.target.value)}
            placeholder="可直接输入文本；或输入 JSON（推荐）"
          />
          <div className="text-xs text-gray-500 mt-2">
            提示：如果输入不是合法 JSON，会自动封装为 {"{ \"message\": \"...\" }"} 传给 Agent。
          </div>

          {result && (
            <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-100">执行结果（简版）</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    result.status === 'completed' || result.status === 'success' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
                  }`}
                >
                  {result.status}
                </span>
              </div>

              {(result.error || result.error_detail?.message) && (
                <div className="text-xs text-red-300 mb-2">
                  失败原因：
                  {result.error_detail?.code ? `[${String(result.error_detail.code)}] ` : ''}
                  {String(result.error_detail?.message || result.error)}
                </div>
              )}

              {result.output !== undefined && result.output !== null && (
                <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
                  {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
                </pre>
              )}

              {result.execution_id && (
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="text-xs text-gray-400 break-all">execution_id: {result.execution_id}</div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(result.execution_id || '');
                          toast.success('已复制');
                        } catch {
                          toast.error('复制失败');
                        }
                      }}
                      disabled={loading}
                    >
                      复制ID
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const url = `/diagnostics/links?execution_id=${encodeURIComponent(result.execution_id || '')}`;
                        window.open(url, '_blank', 'noopener,noreferrer');
                      }}
                      disabled={loading}
                    >
                      查看诊断详情
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
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
                      <Button
                        variant="secondary"
                        onClick={() => setInput(ex.content)}
                        disabled={loading}
                      >
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
    </Modal>
  );
};

export default ExecuteAgentModal;
