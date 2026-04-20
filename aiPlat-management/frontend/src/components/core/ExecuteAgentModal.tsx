import React, { useState } from 'react';
import { agentApi, type Agent } from '../../services';
import { Button, Modal, Textarea, toast } from '../ui';
import { diagnosticsApi } from '../../services';
import { toastGateError } from '../../utils/governanceError';

interface ExecuteAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const ExecuteAgentModal: React.FC<ExecuteAgentModalProps> = ({ open, agent, onClose }) => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: string; execution_id?: string; output?: unknown; error?: any; error_message?: string; error_detail?: any } | null>(null);
  const [autoSmoke, setAutoSmoke] = useState(false);

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
      const result = await agentApi.execute(agent.id, { input: parsedInput });
      const status = String((result as any)?.status || 'ok');
      const legacyStatus = String((result as any)?.legacy_status || '');
      const execution_id = (result as any)?.execution_id ? String((result as any).execution_id) : undefined;
      setResult({
        status,
        execution_id,
        output: (result as any)?.output,
        error: (result as any)?.error,
        error_message: (result as any)?.error_message,
        error_detail: (result as any)?.error_detail,
      });
      if (legacyStatus === 'queued') toast.success('已排队');
      else toast.success(status === 'completed' ? '执行成功' : `状态: ${status}`);

      // 可选：自动触发全链路冒烟（用于你刚修改/新增 agent 后的快速验收）
      if (autoSmoke) {
        try {
          const smoke = await diagnosticsApi.runE2ESmoke({ tenant_id: 'ops_smoke', actor_id: 'admin', agent_model: 'deepseek-reasoner' });
          toast.success(smoke?.ok ? '全链路冒烟通过' : '全链路冒烟失败');
        } catch (e: any) {
          toast.error('全链路冒烟失败', String(e?.message || 'unknown'));
        }
      }
    } catch (e: any) {
      const msg = String(e?.message || e?.detail || '执行失败');
      setResult({ status: 'failed', error: msg });
      toastGateError(e, '执行失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); setInput(''); setResult(null); }}
      title={`执行 Agent: ${agent?.name || ''}`}
      width={820}
      footer={
        <>
          <Button variant="secondary" onClick={() => { onClose(); setInput(''); setResult(null); }} disabled={loading}>关闭</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
        </>
      }
    >
      <Textarea
        label="输入（JSON 或文本）"
        rows={8}
        value={input}
        onChange={(e: any) => setInput(e.target.value)}
        placeholder="输入 JSON 或文本"
      />

      <label className="mt-3 flex items-center gap-2 text-sm text-gray-400">
        <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
        执行后自动运行全链路冒烟（会创建/清理资源）
      </label>

      {result && (
        <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-100">执行结果（简版）</span>
            <span
              className={`text-xs px-2 py-0.5 rounded ${
                result.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
              }`}
            >
              {result.status}
            </span>
          </div>

          {((result as any).error || (result as any).error_detail || (result as any).error_message) && (
            <div className="text-xs text-red-300 mb-2">
              失败原因：
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

          {result.output !== undefined && result.output !== null && (
            <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
              {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
            </pre>
          )}

          {result.execution_id && (
            <div className="mt-3 flex items-center justify-between gap-2">
              <div className="text-xs text-gray-400 break-all">execution_id: {result.execution_id}</div>
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
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteAgentModal;
