import React, { useState } from 'react';
import { agentApi, type Agent } from '../../services';
import { Button, Modal, Textarea, toast } from '../ui';
import { toastGateError } from '../ui';
import ExecutionViewer, { StructuredDetail } from '../ExecutionViewer/ExecutionViewer';

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
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [selectedFlowNode, setSelectedFlowNode] = useState<any>(null);

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
        options: { force_react: forceReAct, stream: true },
      });
      setResult(result);
      const status = String((result as any)?.status || '');
      const runId = (result as any)?.run_id || (result as any)?.execution_id || '';
      if (runId && (status === 'running' || status === 'completed' || status === 'accepted')) {
        setFlowFullscreen(true);
      }
      toast.success(status === 'completed' ? '执行成功' : `状态: ${status}`);

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

      {result && !flowFullscreen && (
        <div className="mt-4 space-y-3">
          {compareMode && compareResult ? (
            <div className="grid grid-cols-2 gap-3">
              {renderResult(result, `当前模型 (${(agent as any).config?.model || '?'})`, '#3b82f6')}
              {renderResult(compareResult, `对比模型 (${compareModel})`, '#a855f7')}
            </div>
          ) : (
            renderResult(result, '执行结果', '#3b82f6')
          )}
          {(result as any)?.run_id && (
            <div className="mt-3">
              <Button variant="primary" onClick={() => setFlowFullscreen(true)}>▶ 查看执行流程（全屏）</Button>
            </div>
          )}
        </div>
      )}

      {/* ── 全屏执行流程弹窗 ── */}
      {flowFullscreen && result && (result as any)?.run_id && (
        <div className="fixed inset-0 z-[60] bg-dark-bg flex flex-col">
          <div className="h-10 flex items-center justify-between px-4 border-b border-dark-border bg-dark-card flex-shrink-0">
            <span className="text-sm font-medium text-gray-200">
              ▶ ReAct 执行流程 · {agent?.name || 'Agent'}
            </span>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded ${(result as any)?.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-blue-900/50 text-blue-300'}`}>
                {(result as any)?.status || 'running'}
              </span>
              <Button variant="secondary" onClick={() => setFlowFullscreen(false)}>✕ 关闭</Button>
            </div>
          </div>
          <ExecutionViewer
            runId={String((result as any).run_id)}
            live={true}
            title=""
            height={window.innerHeight - 40}
            onNodeClick={(node: any) => setSelectedFlowNode(node)}
          />
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
        </div>
      )}
    </Modal>
  );
};

export default ExecuteAgentModal;
