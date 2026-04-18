import React, { useState } from 'react';

import { Button, Modal, Textarea, toast } from '../ui';

interface ExecuteSkillModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

const ExecuteSkillModal: React.FC<ExecuteSkillModalProps> = ({ open, skill, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: string; output?: unknown; error?: any; error_message?: string; error_detail?: any; duration_ms?: number } | null>(null);
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

      const { skillApi } = await import('../../services');
      const res = await skillApi.execute(skill.id, { input: payload });
      setResult(res as any);
      toast.success(res.status === 'completed' || res.status === 'success' ? '执行成功' : `状态: ${res.status}`);
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
          {result.duration_ms != null && (
            <div className="text-xs text-gray-400 mb-2">耗时: {result.duration_ms}ms</div>
          )}
          {result.output !== undefined && result.output !== null && (
            <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
              {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
            </pre>
          )}
          {(((result as any).error || (result as any).error_detail || (result as any).error_message) && !result.output) && (
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
