import React, { useEffect, useState } from 'react';
import { workspaceAgentApi } from '../../services/coreApi';
import type { Agent } from '../../services';
import { Button, Modal, Textarea, notify, toast } from '../ui';

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

  useEffect(() => {
    const load = async () => {
      if (!open || !agent) return;
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
      const result = await workspaceAgentApi.execute(agent.id, { input: parsedInput });
      toast.success('执行完成', String((result as any)?.status || 'ok'));
      if ((result as any)?.execution_id) {
        notify.success(
          `Agent 执行完成：${agent.name}`,
          `execution_id: ${(result as any).execution_id}`,
          `/diagnostics/links?execution_id=${encodeURIComponent(String((result as any).execution_id))}`
        );
      }
      onClose();
      setInput('');
    } catch {
      toast.error('执行失败');
      notify.error(`Agent 执行失败：${agent.name}`);
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
          <Button variant="secondary" onClick={() => { onClose(); setInput(''); }} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
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
