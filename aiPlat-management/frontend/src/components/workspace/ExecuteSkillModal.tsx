import React, { useState } from 'react';

import { Button, Modal, Textarea, notify, toast } from '../ui';
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
      if ((res as any)?.execution_id) {
        notify.success(
          `Skill 执行完成：${skill.name}`,
          `execution_id: ${(res as any).execution_id}`,
          `/diagnostics/links?execution_id=${encodeURIComponent(String((res as any).execution_id))}`
        );
      }
    } catch (error: any) {
      toast.error('执行失败');
      notify.error(`Skill 执行失败：${skill?.name || ''}`, String(error?.message || ''));
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
      width={640}
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
      <Textarea
        label="输入参数"
        rows={4}
        value={inputText}
        onChange={(e: any) => setInputText(e.target.value)}
        placeholder='{"query": "搜索关键词"} 或直接输入文本'
      />

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
        </div>
      )}
    </Modal>
  );
};

export default ExecuteSkillModal;

