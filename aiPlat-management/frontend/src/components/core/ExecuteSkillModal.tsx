import React, { useEffect, useMemo, useState } from 'react';

import { Button, Modal, Textarea, toast } from '../ui';
import { diagnosticsApi } from '../../services';
import { toastGateError } from '../ui';
import ExecuteResultPanel from '../execution/ExecuteResultPanel';
import ExecuteFlowFullscreen from '../execution/ExecuteFlowFullscreen';
import { RunVerdictBanner, deriveRunVerdict, outputAsText } from '../execution/runVerdict';
import {
  isSkillRunInFlight,
  normalizeSkillExecuteResult,
  shouldOpenSkillFlow,
} from '../../utils/skillExecute';
import { pollSkillExecutionUntilDone } from '../../utils/pollSkillExecution';

interface ExecuteSkillModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

/** Engine Core Skills — same stream + live flow contract as workspace Skills. */
const ExecuteSkillModal: React.FC<ExecuteSkillModalProps> = ({ open, skill, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReturnType<typeof normalizeSkillExecuteResult> | null>(null);
  const [inputText, setInputText] = useState('');
  const [autoSmoke, setAutoSmoke] = useState(false);
  const [flowFullscreen, setFlowFullscreen] = useState(false);

  const displayVerdict = useMemo(
    () =>
      result
        ? deriveRunVerdict({
            status: result.status,
            error: result.error_message || result.error,
            outputText: outputAsText(result.output),
          })
        : null,
    [result],
  );

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setInputText('');
    setFlowFullscreen(false);
  }, [open, skill?.id]);

  // Stream poll — identical contract to workspace ExecuteSkillModal
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
  }, [result?.run_id, result?.status, skill?.id]);

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
      // stream/trial defaults applied inside skillApi.execute
      const res = await skillApi.execute(skill.id, {
        input: payload,
        options: { ...((payload.options || {}) as Record<string, unknown>) },
      });
      const normalized = normalizeSkillExecuteResult(res);
      setResult(normalized);
      const st = String(normalized.status || '');
      const legacyStatus = String((res as any)?.legacy_status || '');
      const errCode = String((res as any)?.error?.code || '');
      const approvalId =
        (res as any)?.approval_request_id ||
        (res as any)?.error?.detail?.approval_request_id ||
        (res as any)?.error_detail?.approval_request_id;
      const runId = normalized.run_id || normalized.execution_id;

      if (legacyStatus === 'queued') {
        toast.success('已排队');
      } else if (st === 'waiting_approval' || legacyStatus === 'approval_required' || errCode === 'APPROVAL_REQUIRED') {
        toast.error(
          '签名未验签，正式执行需治理审批',
          approvalId
            ? `审批单 ${String(approvalId).slice(0, 12)}…（本机试跑已带 trial；或到 Skill 详情完成验签）`
            : '请到 Skill 详情完成签名验签后再试',
        );
      } else if (st === 'completed') {
        toast.success('执行成功');
      }

      if (runId && shouldOpenSkillFlow(st)) {
        setFlowFullscreen(true);
      }

      if (autoSmoke && !isSkillRunInFlight(st)) {
        try {
          const smoke = await diagnosticsApi.runE2ESmoke({
            tenant_id: 'ops_smoke',
            actor_id: 'admin',
            agent_model: 'deepseek-reasoner',
          });
          toast.success(smoke?.ok ? '全链路冒烟通过' : '全链路冒烟失败');
        } catch (e: any) {
          toast.error('全链路冒烟失败', String(e?.message || 'unknown'));
        }
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
    setFlowFullscreen(false);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={`执行 Skill: ${skill?.name || ''}`}
      width={720}
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

      <label className="mt-3 flex items-center gap-2 text-sm text-gray-400">
        <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
        执行后自动运行全链路冒烟（会创建/清理资源）
      </label>

      {result && (
        <div className="mt-4">
          <ExecuteResultPanel
            result={result as any}
            loading={loading || isSkillRunInFlight(result.status)}
            onOpenFlow={result.run_id ? () => setFlowFullscreen(true) : undefined}
          />
        </div>
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
            </div>
          ) : null
        }
      />
    </Modal>
  );
};

export default ExecuteSkillModal;
