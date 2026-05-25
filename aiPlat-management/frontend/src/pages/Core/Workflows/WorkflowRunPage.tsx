import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw, CheckCircle2, XCircle, Clock, Loader2, AlertTriangle } from 'lucide-react';
import { workflowApi } from '../../../services';

const NODE_ICONS: Record<string, string> = { start: '▶️', end: '🏁', agent: '🤖', llm: '🧠', code: '💻', http: '🌐', condition: '🔀', human: '👤', loop: '🔄', knowledge: '📚', tool: '🔧', template: '📄', list: '📋', aggregator: '📦', assigner: '✏️' };
const STATUS_ICON: Record<string, React.FC<any>> = {
  idle: () => <Clock className="w-3.5 h-3.5 text-gray-500" />,
  running: () => <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />,
  done: () => <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />,
  failed: () => <XCircle className="w-3.5 h-3.5 text-red-400" />,
  skipped: () => <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />,
};

const WorkflowRunPage: React.FC = () => {
  const { id, projectId } = useParams<{ id: string; projectId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState('');
  const [stages, setStages] = useState<any[]>([]);
  const [error, setError] = useState('');
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  const refresh = useCallback(async () => {
    if (!projectId || !id) return;
    try {
      const [wf, eventsRes] = await Promise.all([
        workflowApi.get(id),
        workflowApi.listEvents(projectId),
      ]);
      const events = eventsRes?.events || [];
      // Merge all event state_json for complete picture
      const mergedState: any = {};
      let phaseFromEvents = '';
      for (const ev of events) {
        try {
          const st = JSON.parse(ev.state_json || '{}');
          Object.assign(mergedState, st);
          if (st.phase) phaseFromEvents = st.phase;
        } catch {}
      }
      const p = phaseFromEvents || mergedState.phase || 'executing';
      setPhase(p);
      const graphTrace: any[] = mergedState._graph_trace || [];
      const failedId: string = mergedState._stage_failed_id || '';
      const stageErr: string = mergedState._stage_error || '';
      const nodes = Array.isArray(wf.nodes) ? wf.nodes : [];
      const stageList = nodes.map((n: any) => {
        const d: any = n.data || {};
        const nid = n.id;
        const done = mergedState[`_stage_${nid}_done`] || false;
        const stId = failedId === nid ? 'failed' : done ? 'done' : graphTrace.some((e: any) => e.node_id === nid && e.event === 'started') ? 'running' : 'idle';
        const rawOutput = mergedState[`_stage_output_${nid}`] || '';
        const elapsedVal = mergedState[`_stage_elapsed_${nid}`] || 0;
        const cleanOutput = (() => {
          const s = String(rawOutput);
          if (s === '{}' || !s) return '';
          for (const key of ['response', 'raw_output', 'content', 'text', 'output']) {
            const re = new RegExp(`['"]${key}['"]\\s*:\\s*['"]([^'"]+)['"]`);
            const m = s.match(re);
            if (m) return m[1];
          }
          return s.slice(0, 1000);
        })();
        const errText = stId === 'failed' ? stageErr : '';
        return { id: nid, label: d.label || nid, type: d.type || 'agent', status: stId, output: cleanOutput, error: errText, elapsed: elapsedVal };
      });

      setStages(stageList);
      if (p === 'done' || p === 'failed') {
        if (timerRef.current) clearInterval(timerRef.current);
      }
    } catch (e: any) {
      setError(e?.detail || e?.message || String(e) || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [id, projectId]);

  useEffect(() => {
    refresh();
    timerRef.current = setInterval(refresh, 3000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [refresh]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(`/core/workflows/${id}/edit`)} className="text-gray-500 hover:text-gray-300"><ArrowLeft className="w-4 h-4" /></button>
        <div>
          <h1 className="text-sm font-semibold text-gray-100">运行结果</h1>
          <p className="text-[10px] text-gray-500 font-mono">{projectId}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className={`text-xs font-medium px-2 py-0.5 rounded ${phase === 'done' ? 'bg-green-500/10 text-green-400' : phase === 'failed' ? 'bg-red-500/10 text-red-400' : phase === 'executing' ? 'bg-blue-500/10 text-blue-400' : 'bg-dark-bg text-gray-500'}`}>{phase || 'idle'}</span>
          <button onClick={refresh} className="p-1 rounded hover:bg-dark-hover text-gray-500 hover:text-gray-300"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-500 text-sm">加载运行状态...</div>
      ) : error ? (
        <div className="text-center py-16 text-red-400 text-sm">{error}</div>
      ) : (
        <div className="space-y-2">
          {stages.map((s, i) => {
            const Icon = STATUS_ICON[s.status] || STATUS_ICON.idle;
            return (
              <div key={s.id || i} className="rounded-lg border border-dark-border bg-dark-card overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-2.5 border-b border-dark-border/30">
                  <span className="text-xs">{NODE_ICONS[s.type] || '🤖'}</span>
                  <span className="text-xs text-gray-200 font-medium">{s.label}</span>
                  <span className="text-[10px] text-gray-600">{s.type}</span>
                  <div className="ml-auto flex items-center gap-1.5">
                    {s.elapsed > 0 && <span className="text-[10px] text-gray-600 font-mono">{s.elapsed}s</span>}
                    <Icon />
                    <span className={`text-[10px] ${s.status === 'done' ? 'text-green-400' : s.status === 'failed' ? 'text-red-400' : s.status === 'running' ? 'text-blue-400' : 'text-gray-500'}`}>{s.status}</span>
                  </div>
                </div>
                {s.output && (
                  <div className="px-4 py-2 bg-dark-bg">
                    <div className="text-[10px] text-gray-600 mb-1">输出</div>
                    <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all font-mono max-h-40 overflow-y-auto">{typeof s.output === 'string' ? s.output : JSON.stringify(s.output).slice(0, 500)}</pre>
                  </div>
                )}
                {s.error && (
                  <div className="px-4 py-2 bg-red-500/5 border-t border-red-500/20">
                    <div className="text-[10px] text-red-400 mb-1">错误</div>
                    <pre className="text-xs text-red-300 whitespace-pre-wrap break-all font-mono max-h-20 overflow-y-auto">{String(s.error).slice(0, 500)}</pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default WorkflowRunPage;
