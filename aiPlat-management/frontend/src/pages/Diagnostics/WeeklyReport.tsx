import { useEffect, useState } from 'react';
import { FileText, Copy, Edit3 } from 'lucide-react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';

type WeeklyReport = {
  generated_at?: string;
  period?: string;
  rag_quality?: {
    avg_faithfulness?: number;
    avg_relevancy?: number;
    quality_gate_pass_rate?: number;
    abandon_rate?: number;
    anomaly_count?: number;
    error?: string;
  };
  hallucination?: {
    total_reports?: number;
    bad_case_count?: number;
    error?: string;
  };
  user_signals?: {
    pattern_count?: number;
    affected_specs?: number;
    error?: string;
  };
  nl_summary?: string;
};

export default function WeeklyReport() {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState('');

  useEffect(() => {
    fetch('/api/core/diagnostics/latest')
      .then(r => r.json())
      .then(d => {
        if (d.weekly_report) {
          setReport(d.weekly_report);
          setEditedText(d.weekly_report.nl_summary || '');
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleCopyForClient = () => {
    if (!report?.nl_summary) return;
    const text = report.nl_summary
      .replace(/RAGDiagnosticsCollector\(168h\)/g, '系统自动分析')
      .replace(/HallucinationTracker/g, '系统自动分析')
      .replace(/FeedbackRadar/g, '系统自动分析');
    navigator.clipboard.writeText(text).then(
      () => toast.success('已复制为客户简报'),
      () => toast.error('复制失败'),
    );
  };

  const handleSaveRevision = () => {
    setReport(prev => prev ? { ...prev, nl_summary: editedText } : null);
    setEditing(false);
    toast.success('批注已保存（本地）');
  };

  if (loading) return null;
  if (!report) return null;

  return (
    <Card className="border-blue-500/30 bg-blue-500/5 mt-4">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
            <FileText className="w-4 h-4 text-blue-400" />
            本周 FDE 周报
            {report.generated_at && (
              <span className="text-xs text-gray-500 font-normal">
                · 生成于 {new Date(report.generated_at).toLocaleDateString('zh-CN')}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={handleCopyForClient} disabled={!report.nl_summary}>
              <Copy className="w-3 h-3 mr-1" />一键复制为客户简报
            </Button>
            <Button
              size="sm"
              variant={editing ? 'default' : 'outline'}
              onClick={() => {
                if (editing) { handleSaveRevision(); } else { setEditing(true); setEditedText(report.nl_summary || ''); }
              }}
            >
              <Edit3 className="w-3 h-3 mr-1" />
              {editing ? '保存批注' : 'FDE 批注修订'}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Metrics summary grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-center text-xs">
          {[
            { label: 'RAG 忠实度', value: report.rag_quality?.avg_faithfulness, unit: '', warn: 0.7 },
            { label: '质量门通过率', value: report.rag_quality?.quality_gate_pass_rate, unit: '%', warn: 80, isPct: true },
            { label: '疑似幻觉', value: report.hallucination?.bad_case_count, unit: ' 条' },
            { label: '用户信号异常', value: report.user_signals?.pattern_count, unit: ' 项' },
          ].map(m => (
            <div key={m.label}>
              <div className="text-gray-500">{m.label}</div>
              <div className={`text-lg font-bold ${
                typeof m.value === 'number'
                  ? m.isPct ? (m.value >= (m.warn || 80) ? 'text-green-400' : 'text-yellow-400')
                  : m.warn ? (m.value >= m.warn ? 'text-green-400' : 'text-yellow-400')
                  : 'text-gray-200'
                  : 'text-gray-400'
              }`}>
                {m.value ?? '-'}{m.unit}
              </div>
            </div>
          ))}
        </div>

        {/* NL report section */}
        {editing ? (
          <textarea
            className="w-full h-48 p-3 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 font-mono resize-y"
            value={editedText}
            onChange={e => setEditedText(e.target.value)}
          />
        ) : report.nl_summary ? (
          <div className="prose prose-invert prose-sm max-w-none text-gray-300 whitespace-pre-wrap text-sm leading-relaxed">
            {report.nl_summary}
          </div>
        ) : (
          <div className="text-gray-500 text-sm italic">本周无足够数据，建议保持默认配置。</div>
        )}
      </CardContent>
    </Card>
  );
}
