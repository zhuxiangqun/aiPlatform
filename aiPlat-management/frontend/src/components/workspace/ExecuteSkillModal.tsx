import React, { useEffect, useState } from 'react';

import { Button, Modal, Textarea, toast } from '../ui';
import { workspaceSkillApi } from '../../services/coreApi';

interface ExecuteSkillModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

const ExecuteSkillModal: React.FC<ExecuteSkillModalProps> = ({ open, skill, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: string; output?: unknown; error?: string; duration_ms?: number } | null>(null);
  const [inputText, setInputText] = useState('');
  const [helpLoading, setHelpLoading] = useState(false);
  const [helpMarkdown, setHelpMarkdown] = useState<string>('');
  const [examples, setExamples] = useState<Array<{ title: string; content: string }>>([]);

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

      const res = await workspaceSkillApi.execute(skill.id, { input: payload });
      setResult(res as any);
      toast.success((res as any).status === 'completed' || (res as any).status === 'success' ? '执行成功' : `状态: ${(res as any).status}`);
    } catch (error: any) {
      toast.error('执行失败');
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
            <span className={`text-xs px-2 py-0.5 rounded ${result.status === 'completed' || result.status === 'success' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
              {result.status}
            </span>
          </div>
          {result.duration_ms != null && <div className="text-xs text-gray-400 mb-2">耗时: {result.duration_ms}ms</div>}
          {result.output !== undefined && result.output !== null && (
            <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
              {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
            </pre>
          )}
          {result.error && !result.output && <div className="text-xs text-red-300 mt-2">{result.error}</div>}

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
    </Modal>
  );
};

export default ExecuteSkillModal;
