import React, { useState } from 'react';
import { agentApi, type Agent } from '../../services';
import { Button, Modal, Textarea, toast } from '../ui';
import { toastGateError } from '../ui';

interface ExecuteAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const ExecuteAgentModal: React.FC<ExecuteAgentModalProps> = ({ open, agent, onClose }) => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [compareResult, setCompareResult] = useState<any>(null);
  const [forceReAct, setForceReAct] = useState(true);
  const [compareMode, setCompareMode] = useState(false);
  const [compareModel, setCompareModel] = useState('deepseek-chat');

  const handleExecute = async () => {
    if (!agent) return;
    let parsedInput: Record<string, unknown> = {};
    if (input.trim()) {
      try { parsedInput = JSON.parse(input); } catch { parsedInput = { message: input }; }
    }
    setLoading(true);
    setResult(null);
    setCompareResult(null);
    try {
      const result = await agentApi.execute(agent.id, {
        input: parsedInput,
        options: { force_react: forceReAct },
      });
      setResult(result);
      toast.success((result as any)?.status === 'completed' ? '执行成功' : `状态: ${(result as any)?.status}`);

      if (compareMode) {
        // Run same prompt against comparison model
        const compareRes = await agentApi.execute(agent.id, {
          input: { ...parsedInput },
          options: { force_react: forceReAct, _model: compareModel } as any,
        });
        setCompareResult(compareRes);
      }
    } catch (e: any) {
      setResult({ status: 'failed', error: String(e?.message || '执行失败') });
      toastGateError(e, '执行失败');
    } finally {
      setLoading(false);
    }
  };

  const renderResult = (res: any, label: string, color: string) => (
    <div className="p-3 rounded-lg border bg-dark-card" style={{ borderColor: color + '40' }}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium" style={{ color }}>{label}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${res?.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
          {res?.status || '?'}
        </span>
      </div>
      {res?.duration_ms && <div className="text-[10px] text-gray-500 mb-1">{res.duration_ms}ms · {res?.metadata?.engine || '?'} · {res?.metadata?.loop_type || '?'}</div>}
      {(res as any)?.error && <div className="text-xs text-red-300 mb-1">{String((res as any).error)}</div>}
      {res?.output !== undefined && res?.output !== null && (
        <pre className="text-xs text-gray-300 overflow-auto max-h-40 whitespace-pre-wrap">{typeof res.output === 'string' ? res.output.slice(0, 600) : JSON.stringify(res.output, null, 2).slice(0, 600)}</pre>
      )}
    </div>
  );

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

      <div className="flex flex-wrap items-center gap-4 mt-3">
        <label className="flex items-center gap-2 text-sm text-gray-400">
          <input type="checkbox" checked={forceReAct} onChange={(e) => setForceReAct(e.target.checked)} />
          ReAct 模式
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-400">
          <input type="checkbox" checked={compareMode} onChange={(e) => setCompareMode(e.target.checked)} />
          对比模式 (同时跑2个模型)
        </label>
        {compareMode && (
          <select value={compareModel} onChange={(e) => setCompareModel(e.target.value)}
            className="h-8 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
            <option value="deepseek-chat">deepseek-chat</option>
            <option value="deepseek-reasoner">deepseek-reasoner</option>
          </select>
        )}
      </div>

      {result && (
        <div className="mt-4 space-y-3">
          {compareMode && compareResult ? (
            <div className="grid grid-cols-2 gap-3">
              {renderResult(result, `当前模型 (${(agent as any).config?.model || '?'})`, '#3b82f6')}
              {renderResult(compareResult, `对比模型 (${compareModel})`, '#a855f7')}
            </div>
          ) : (
            renderResult(result, '执行结果', '#3b82f6')
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteAgentModal;
