import { Link } from 'react-router-dom';
import { useState, useEffect, useRef, useReducer, useCallback, startTransition } from 'react';
import { Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';

interface ReviewResult {
  file: string;
  score: number;
  p0: number;
  p1: number;
  p2: number;
}

type ReviewState = {
  running: boolean;
  filesDone: number;
  filesTotal: number;
  current: string;
  elapsed: number;
  results: ReviewResult[];
  status: string;
  finalScore: number | null;
  finalP0: number;
  finalP1: number;
};

type ReviewAction =
  | { type: 'start' }
  | { type: 'progress'; data: Record<string, any> }
  | { type: 'done'; data: Record<string, any> }
  | { type: 'error'; error: string };

function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case 'start':
      return { running: true, filesDone: 0, filesTotal: 0, current: '', elapsed: 0,
               results: [], status: '', finalScore: null, finalP0: 0, finalP1: 0 };
    case 'progress':
      return {
        ...state,
        running: true,
        filesDone: action.data.files_done ?? state.filesDone,
        filesTotal: action.data.files_total ?? state.filesTotal,
        current: action.data.current ?? state.current,
        elapsed: action.data.elapsed_s ?? state.elapsed,
        results: action.data.results ?? state.results,
        status: action.data.status ?? state.status,
      };
    case 'done':
      return {
        ...state,
        running: false,
        filesDone: action.data.files_done ?? state.filesDone,
        filesTotal: action.data.files_total ?? state.filesTotal,
        results: action.data.results ?? state.results,
        status: 'done',
        finalScore: action.data.score ?? 0,
        finalP0: action.data.p0 ?? 0,
        finalP1: action.data.p1 ?? 0,
      };
    case 'error':
      return { ...state, running: false, status: 'error' };
    default:
      return state;
  }
}

const initialState: ReviewState = {
  running: false, filesDone: 0, filesTotal: 0, current: '', elapsed: 0,
  results: [], status: '', finalScore: null, finalP0: 0, finalP1: 0,
};

export default function LLMReview() {
  const [state, dispatch] = useReducer(reviewReducer, initialState);
  const [maxFiles, setMaxFiles] = useState(15);
  const [focus, setFocus] = useState('comprehensive');
  const [history, setHistory] = useState<any[]>([]);
  const [costStats, setCostStats] = useState<{ total_cost: number; total_tokens: number; runs: number }>({ total_cost: 0, total_tokens: 0, runs: 0 });
  const runIdRef = useRef('');
  const intervalRef = useRef<number | null>(null);
  const [progressPct, setProgressPct] = useState(0);

  const startReview = async () => {
    dispatch({ type: 'start' });
    try {
      const res = await fetch('/api/core/diagnostics/llm-review/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_files: maxFiles, focus, max_chars: 12000 }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      runIdRef.current = data.run_id;

      intervalRef.current = window.setInterval(() => {
        pollStatus(data.run_id);
      }, 3000);
    } catch (e: any) {
      toast.error('启动审查失败: ' + (e?.message || String(e)));
      dispatch({ type: 'start' });
    }
  };

  const pollStatus = async (rid: string) => {
    try {
      const res = await fetch(`/api/core/diagnostics/llm-review/status?run_id=${rid}`);
      if (!res.ok) return;
      const data = await res.json();

      // Batch all state updates via startTransition to avoid forced reflow
      startTransition(() => {
        if (data.status === 'running') {
          dispatch({ type: 'progress', data });
          setProgressPct((data.files_done || 0) / Math.max(data.files_total || 1, 1) * 100);
        } else if (data.status === 'done') {
          dispatch({ type: 'done', data });
          if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
          if ((data.p0 || 0) > 0) {
            toast.error(`审查完成: ${data.files_done}文件, P0=${data.p0}, score=${data.score}`);
          } else if ((data.p1 || 0) > 0) {
            toast.warning(`审查完成: ${data.files_done}文件, P1=${data.p1}, score=${data.score}`);
          } else {
            toast.success(`审查完成: ${data.files_done}文件, 0 issues, score=${data.score}`);
          }
        } else if (data.status === 'error') {
          dispatch({ type: 'error', error: data.error || '未知错误' });
          if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
          toast.error('审查失败: ' + (data.error || '未知错误'));
        } else if (data.status === 'not_found' && state.elapsed > 10) {
          dispatch({ type: 'error', error: 'not_found' });
          if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
          toast.warning('审查任务未找到，请刷新后重新开始');
        }
      });
    } catch { /* poll silently */ }
  };

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Load history + cost stats on mount
  useEffect(() => {
    fetch('/api/core/diagnostics/llm-review/history?limit=10')
      .then(r => r.json())
      .then(d => setHistory(d.items || []))
      .catch(() => {});
    fetch('/api/core/diagnostics/llm-review/summary-stats')
      .then(r => r.json())
      .then(d => setCostStats({ total_cost: d.total_cost || 0, total_tokens: d.total_tokens || 0, runs: d.runs || 0 }))
      .catch(() => {});
  }, []);

  const { running, filesDone, filesTotal, current, elapsed, results, status, finalScore, finalP0, finalP1 } = state;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Link to="/diagnostics" className="text-xs text-gray-500 hover:text-gray-300">← 返回诊断中心</Link>
        <Zap className="w-6 h-6 text-cyan-400" />
        <h1 className="text-2xl font-semibold text-gray-200">LLM 审查</h1>
        <span className="text-xs text-gray-500 bg-dark-bg px-2 py-0.5 rounded">~150K tokens/次</span>
        {costStats.runs > 0 && (
          <span className="text-xs text-gray-500">
            累计: ${costStats.total_cost.toFixed(4)} · {costStats.total_tokens.toLocaleString()} tokens · {costStats.runs} 次
          </span>
        )}
      </div>

      {/* ── Config ── */}
      <Card>
        <CardHeader>
          <span className="text-sm font-semibold text-gray-200">⚙ 审查配置</span>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400">文件数:</label>
              <select
                value={maxFiles}
                onChange={(e) => setMaxFiles(Number(e.target.value))}
                className="bg-dark-bg border border-dark-border rounded px-2 py-1 text-xs text-gray-200"
                disabled={running}
              >
                <option value={5}>5</option>
                <option value={15}>15</option>
                <option value={30}>30</option>
                <option value={50}>全部（最多 50）</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400">维度:</label>
              <select
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                className="bg-dark-bg border border-dark-border rounded px-2 py-1 text-xs text-gray-200"
                disabled={running}
              >
                <option value="comprehensive">全面 (P0+P1+P2)</option>
                <option value="security">安全 (P0)</option>
                <option value="logic">逻辑错误 (P1)</option>
                <option value="error_handling">错误处理 (P1)</option>
                <option value="performance">性能 (P1)</option>
                <option value="style">风格 (P2)</option>
                <option value="naming">命名规范 (P2)</option>
                <option value="dead_code">死代码 (P2)</option>
              </select>
            </div>
            <Button variant="primary" size="sm" disabled={running} onClick={startReview}>
              {running ? '⏳ 审查中...' : '▶ 开始审查'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── Progress ── */}
      {running && (
        <Card className="border-cyan-500/30">
          <CardHeader>
            <span className="text-sm font-semibold text-gray-200">📊 审查进度</span>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                  <span>{filesDone}/{filesTotal} 文件</span>
                  <span>{elapsed}s</span>
                </div>
                <div className="w-full bg-dark-bg rounded-full h-2">
                  <div
                    className="bg-cyan-400 h-2 rounded-full"
                    style={{ width: `${progressPct}%`, transition: 'width 0.5s ease-out' }}
                  />
                </div>
              </div>
              {current && (
                <div className="text-xs text-gray-400">
                  正在审查: <span className="text-gray-200">{current}</span>
                </div>
              )}
              {results.length > 0 && (
                <div className="mt-3 space-y-1 max-h-60 overflow-y-auto">
                  {results.map((r, i) => (
                    <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-dark-border">
                      <span className="text-gray-300 truncate flex-1">{r.file}</span>
                      <span className={`ml-2 ${r.p0 > 0 ? 'text-red-400' : r.p1 > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                        {r.p0 > 0 ? `P0=${r.p0}` : r.p1 > 0 ? `P1=${r.p1}` : '✅'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Results ── */}
      {finalScore !== null && (
        <Card className={finalP0 > 0 ? 'border-red-500/30' : finalP1 > 0 ? 'border-yellow-500/30' : 'border-green-500/30'}>
          <CardHeader>
            <span className="text-sm font-semibold text-gray-200">📋 审查结果</span>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4 mb-3">
              <span className={`text-2xl font-bold ${finalP0 > 0 ? 'text-red-400' : finalP1 > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                {finalScore}
              </span>
              <span className="text-xs text-gray-500">
                P0={finalP0}, P1={finalP1}, {filesDone} 文件
                {filesDone > 0 && (
                  <span className="ml-2 text-gray-600">
                    ~${((filesDone * 2 * 3000 / 1000000 * 0.27) + (filesDone * 2 * 2000 / 1000000 * 1.10)).toFixed(3)}
                  </span>
                )}
              </span>
            </div>
            {results.length > 0 && (
              <div className="space-y-1 max-h-80 overflow-y-auto">
                {results.map((r, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-dark-border">
                    <span className="text-gray-300 truncate flex-1">{r.file}</span>
                    <span className="ml-2 text-gray-500">score={r.score}</span>
                    <span className={`ml-2 w-16 text-right ${r.p0 > 0 ? 'text-red-400' : r.p1 > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
                      P0={r.p0} P1={r.p1}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── History ── */}
      {history.length > 0 && (
        <Card>
          <CardHeader>
            <span className="text-sm font-semibold text-gray-200">📜 历史审查</span>
            <span className="text-xs text-gray-500 ml-2">（最近 {history.length} 次）</span>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {history.map((h: any, i: number) => {
                const color = h.status === 'done'
                  ? (h.p0 > 0 ? 'text-red-400' : h.p1 > 0 ? 'text-yellow-400' : 'text-green-400')
                  : h.status === 'running' ? 'text-blue-400' : 'text-gray-500';
                return (
                  <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-dark-border">
                    <span className="text-gray-500 w-16">{Math.floor(h.age_s / 60)}m{h.age_s % 60}s前</span>
                    <span className={`font-medium flex-1 ${color}`}>{h.status === 'done' ? h.score : h.status}</span>
                    <span className="text-gray-600">{h.files_done}/{h.files_total}文件</span>
                    <span className="text-gray-500 ml-2">P0={h.p0} P1={h.p1}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
