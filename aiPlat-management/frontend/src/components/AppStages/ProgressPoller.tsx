import React, { useState, useEffect, useCallback } from 'react';
import { Card, Progress } from '../../ui';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';

interface ProgressConfig {
  status_field?: string;
  poll_ms?: number;
  stages?: string[];
  labels?: Record<string, string>;
  input?: Record<string, string>;
}

interface Props {
  config: ProgressConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  stageInput?: Record<string, any>;
}

export const ProgressPoller: React.FC<Props> = ({ config, onExecute, skill, stageInput }) => {
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [result, setResult] = useState<any>(null);

  const stages = config.stages || ['pending', 'processing', 'completed'];
  const pollMs = config.poll_ms || 3000;
  const labels = config.labels || {};

  const poll = useCallback(async () => {
    try {
      const params = { ...(config.input || {}), ...(stageInput || {}) };
      const res = await onExecute(skill, params);
      const st = typeof res === 'string' ? res : (res?.[config.status_field || 'status'] || res?.reply || '');
      setStatus(st);

      const idx = stages.indexOf(st);
      if (idx >= 0) setProgress(Math.round((idx / (stages.length - 1)) * 100));

      if (st === 'completed' || st === 'done') {
        setDone(true);
        setResult(res);
      }
      if (st === 'failed' || st === 'error') {
        setError(res?.error || '处理失败');
        setDone(true);
      }
    } catch (e: any) {
      setError(e?.message || '轮询失败');
    }
  }, [skill, config, stageInput, stages, pollMs, onExecute]);

  useEffect(() => {
    poll(); // immediate first poll
    if (done) return;
    const timer = setInterval(poll, pollMs);
    return () => clearInterval(timer);
  }, [poll, done, pollMs]);

  const statusLabel = labels[status] || status || '处理中';

  return (
    <Card className="p-6 max-w-lg mx-auto">
      <h2 className="text-lg font-semibold mb-4 text-gray-100">处理进度</h2>
      <Progress value={progress} className="mb-4" />
      <div className="flex items-center gap-2 text-sm">
        {!done && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
        {done && !error && <CheckCircle className="w-4 h-4 text-green-400" />}
        {error && <XCircle className="w-4 h-4 text-red-400" />}
        <span className={error ? 'text-red-400' : done ? 'text-green-400' : 'text-gray-300'}>
          {error || statusLabel}
        </span>
      </div>
    </Card>
  );
};
