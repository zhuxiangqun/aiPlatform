import { useEffect, useState } from 'react';
import { BarChart3, TrendingUp, TrendingDown, AlertTriangle, ShieldCheck, Activity, RefreshCw } from 'lucide-react';

interface RAGMetrics {
  faithfulness_score: number;
  answer_relevancy_score: number;
  retrieval_precision: number;
  total_sessions: number;
  retry_rate: number;
}

interface RAGAnomaly {
  type: string;
  severity: string;
  detail: string;
}

interface RAGQualityData {
  overall_score: number;
  status: string;
  period: string;
  metrics: RAGMetrics;
  anomalies: RAGAnomaly[];
  detail: any;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  excellent: { label: '优秀', color: 'text-green-400', bg: 'bg-green-500/20' },
  good: { label: '良好', color: 'text-blue-400', bg: 'bg-blue-500/20' },
  fair: { label: '一般', color: 'text-yellow-400', bg: 'bg-yellow-500/20' },
  poor: { label: '差', color: 'text-orange-400', bg: 'bg-orange-500/20' },
  unavailable: { label: '不可用', color: 'text-gray-400', bg: 'bg-gray-500/20' },
  ok: { label: '正常', color: 'text-green-400', bg: 'bg-green-500/20' },
};

const RAGQuality: React.FC = () => {
  const [data, setData] = useState<RAGQualityData | null>(null);
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = (h: number) => {
    setLoading(true);
    setError('');
    fetch(`/api/core/diagnostics/rag-quality?hours=${h}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  };

  useEffect(() => { fetchData(hours); }, [hours]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (error || !data || !data.metrics) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400">
        <AlertTriangle className="w-5 h-5 mr-2" />{error || 'RAG 质量数据不可用'}
      </div>
    );
  }

  if (!data) return null;

  const st = STATUS_CONFIG[data.status] || STATUS_CONFIG.unavailable;
  const m = data.metrics;

  const ScoreBar: React.FC<{ label: string; value: number; suffix?: string; color: string }> = 
    ({ label, value, suffix, color }) => (
      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-gray-400">{label}</span>
          <span className={color}>{typeof value === 'number' ? (suffix ? `${(value * (suffix === '%' ? 100 : 1)).toFixed(1)}${suffix}` : value.toFixed(3)) : '—'}</span>
        </div>
        <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div className={`h-full ${color.replace('text-', 'bg-')} rounded-full`} 
               style={{ width: `${Math.min(value * 100, 100)}%` }} />
        </div>
      </div>
    );

  return (
    <div className="space-y-6 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 className="w-6 h-6 text-blue-400" />
          <div>
            <h2 className="text-lg font-semibold text-gray-200">RAG 质量仪表盘</h2>
            <p className="text-xs text-gray-500">检索增强生成质量评估 — 忠实度 · 相关度 · 检索精度 · 用户信号</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {[1, 6, 24, 72, 168].map(h => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`px-2 py-1 text-xs rounded ${hours === h ? 'bg-blue-500/30 text-blue-300' : 'bg-gray-700/30 text-gray-400 hover:bg-gray-700/50'}`}
            >
              {h >= 24 ? `${h / 24}d` : `${h}h`}
            </button>
          ))}
          <button onClick={() => fetchData(hours)} className="p-1.5 rounded bg-gray-700/30 text-gray-400 hover:bg-gray-700/50">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Overall score */}
      <div className={`rounded-xl p-6 ${st.bg} border border-white/10 text-center`}>
        <div className={`text-5xl font-bold ${st.color}`}>{data.overall_score}</div>
        <div className={`text-sm mt-2 ${st.color}`}>{st.label}</div>
        <div className="text-xs text-gray-500 mt-1">综合质量评分 · 过去 {data.period}</div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <MetricCard icon={ShieldCheck} label="忠实度" value={m.faithfulness_score} color="text-green-400" format="score" />
        <MetricCard icon={Activity} label="回答相关度" value={m.answer_relevancy_score} color="text-blue-400" format="score" />
        <MetricCard icon={TrendingUp} label="检索精度" value={m.retrieval_precision} color="text-purple-400" format="score" />
        <MetricCard icon={BarChart3} label="会话数" value={m.total_sessions} color="text-gray-200" format="int" />
        <MetricCard icon={TrendingDown} label="重复询问率" value={m.retry_rate} color="text-yellow-400" format="pct" />
      </div>

      {/* Score bars */}
      <div className="rounded-lg bg-gray-800/50 border border-gray-700/50 p-4 space-y-3">
        <div className="text-xs font-semibold text-gray-400 mb-2">质量维度</div>
        <ScoreBar label="忠实度 (Faithfulness)" value={m.faithfulness_score} color="text-green-400" />
        <ScoreBar label="回答相关度 (Relevancy)" value={m.answer_relevancy_score} color="text-blue-400" />
        <ScoreBar label="检索精度 (Precision)" value={m.retrieval_precision} color="text-purple-400" />
        <ScoreBar label="重复询问率 (Retry)" value={m.retry_rate} color="text-yellow-400" suffix="%" />
      </div>

      {/* Anomalies */}
      {data.anomalies && data.anomalies.length > 0 && (
        <div className="rounded-lg bg-gray-800/50 border border-gray-700/50 p-4">
          <div className="text-xs font-semibold text-gray-400 mb-3 flex items-center gap-1">
            <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />
            异常检测
          </div>
          <div className="space-y-2">
            {data.anomalies.map((a, i) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded bg-yellow-500/10 text-xs">
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                  a.severity === 'high' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'
                }`}>{a.severity}</span>
                <div>
                  <span className="text-yellow-300">{a.type}:</span>
                  <span className="text-gray-400 ml-1">{a.detail}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const MetricCard: React.FC<{
  icon: any; label: string; value: number; color: string; format: 'score' | 'pct' | 'int';
}> = ({ icon: Icon, label, value, color, format }) => {
  const display = format === 'score' ? (value * 100).toFixed(1) + '%'
    : format === 'pct' ? (value * 100).toFixed(1) + '%'
    : value.toLocaleString();

  return (
    <div className="rounded-lg bg-gray-800/50 border border-gray-700/50 p-3 text-center">
      <Icon className={`w-4 h-4 mx-auto mb-1 ${color}`} />
      <div className={`text-xl font-bold ${color}`}>{display}</div>
      <div className="text-[10px] text-gray-500 mt-0.5">{label}</div>
    </div>
  );
};

export default RAGQuality;
