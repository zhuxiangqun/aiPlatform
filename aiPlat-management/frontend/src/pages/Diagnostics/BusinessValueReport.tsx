import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, Badge, Button } from '../../components/ui';
import { ArrowLeft, Download, TrendingUp, ShieldCheck, Zap, DollarSign, Clock, Award } from 'lucide-react';

const GRADE_COLORS: Record<string, string> = {
  A: 'text-green-400 bg-green-900/20 border-green-700/40',
  B: 'text-blue-400 bg-blue-900/20 border-blue-700/40',
  C: 'text-yellow-400 bg-yellow-900/20 border-yellow-700/40',
  D: 'text-orange-400 bg-orange-900/20 border-orange-700/40',
  F: 'text-red-400 bg-red-900/20 border-red-700/40',
};

const KPI_ICONS: Record<string, any> = {
  '流程自动化率': Zap,
  '合规零风险': ShieldCheck,
  '决策可信度': TrendingUp,
  '成本效率': DollarSign,
  '交付质量': Award,
  '节省人力': Clock,
};

const BusinessValuePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('project_id') || 'demo-project';
  const projectName = searchParams.get('name') || projectId;
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/core/agents/business-value/${encodeURIComponent(projectId)}?project_name=${encodeURIComponent(projectName)}&monthly_count=100`)
      .then(r => r.json()).then(setReport).catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [projectId, projectName]);

  if (loading) return <div className="p-4 text-gray-500">加载中...</div>;
  if (!report) return <div className="p-4 text-red-400">报告生成失败</div>;

  const mk = report.markdown || '';

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">{report.project_name} · 业务价值</h1>
          <p className="text-xs text-gray-500 mt-1">续费依据报告 · {new Date(report.generated_at * 1000).toISOString().slice(0,10)}</p>
        </div>
        <div className="flex gap-2">
          <a href={`data:text/markdown;charset=utf-8,${encodeURIComponent(mk)}`}
            download={`${report.project_name}-renewal-${new Date().toISOString().slice(0,10)}.md`}
            className="text-xs text-blue-400 hover:underline flex items-center gap-1">
            <Download className="w-3 h-3" />导出 .md
          </a>
          <Button variant="ghost" size="sm" onClick={() => window.history.back()}>
            <ArrowLeft className="w-3 h-3 mr-1" />返回
          </Button>
        </div>
      </div>

      {/* Grade card */}
      <Card className={`border-2 ${GRADE_COLORS[report.grade] || GRADE_COLORS.C}`}>
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <div className="text-5xl font-bold text-gray-100">{report.grade}</div>
            <div>
              <div className="text-sm text-gray-300">{report.score} 分</div>
              <div className="text-xs text-gray-500 mt-1">月执行 {report.monthly_exec_count} 次 · 节省 {report.hours_saved} 小时</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {(report.kpis || []).map((kpi: any) => {
          const Icon = KPI_ICONS[kpi.label] || TrendingUp;
          return (
            <Card key={kpi.label} className="bg-dark-card border-dark-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-4 h-4 text-blue-400" />
                  <span className="text-sm text-gray-300">{kpi.label}</span>
                  <span className="text-xs text-gray-500">{kpi.trend}</span>
                </div>
                <div className="text-2xl font-bold text-gray-100 mb-1">{kpi.value}</div>
                <div className="text-xs text-gray-500">{kpi.detail}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Agent breakdown */}
      {report.agent_breakdown?.length > 0 && (
        <Card className="border-dark-border/30">
          <CardHeader><span className="text-sm font-medium text-gray-200">项目 Agent 明细</span></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {report.agent_breakdown.map((a: any, i: number) => (
                <div key={i} className="flex items-center gap-3 text-xs">
                  <span className="text-gray-400 w-40 truncate">{a.agent_id}</span>
                  <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: `${a.task_completion}%` }} />
                  </div>
                  <span className="text-gray-300 w-10 text-right">{a.task_completion}%</span>
                  <span className="text-gray-600 w-16 text-right">{a.exec_count} 次</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recommendations */}
      {report.recommendations?.length > 0 && (
        <Card className="border-blue-700/40 bg-blue-950/20">
          <CardHeader><span className="text-sm font-medium text-gray-200">优化建议</span></CardHeader>
          <CardContent>
            {report.recommendations.map((r: string, i: number) => (
              <div key={i} className="text-sm text-blue-400 mb-1">💡 {r}</div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Renewal suggestion */}
      <Card className={report.score >= 80 ? 'border-green-700/40 bg-green-950/20' : 'border-yellow-700/40 bg-yellow-950/20'}>
        <CardContent className="p-4">
          <span className="text-sm font-medium text-gray-200">📋 {report.renewal_suggestion}</span>
        </CardContent>
      </Card>
    </div>
  );
};

export default BusinessValuePage;
