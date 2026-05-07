import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, RefreshCw, TrendingUp, TrendingDown, Minus, Zap } from 'lucide-react';
import { insightApi, type AgentInsight } from '../../../services';
import { Card, CardHeader, CardContent, Button, toast } from '../../../components/ui';

const AGENT_NAMES: Record<string, string> = {
  architect_agent: '系统架构师', programmer_agent: '程序员', pm_agent: '产品经理',
  qa_agent: '测试经理', frontend_engineer: '前端工程师', backend_developer: '后端开发工程师',
  devops_engineer: 'DevOps工程师', security_engineer: '安全工程师', database_engineer: '数据库工程师',
  code_reviewer: '代码审查员', ai_engineer: 'AI工程师', sre_engineer: 'SRE工程师',
  ui_designer: 'UI设计师', ux_researcher: 'UX研究员', accessibility_auditor: '可访问性审计师',
  performance_tester: '性能测试工程师', api_tester: 'API测试工程师',
  sprint_prioritizer: '迭代规划师', trend_researcher: '趋势研究员', feedback_synthesizer: '反馈整合分析师',
  project_shepherd: '项目牧羊人', experiment_tracker: '实验追踪员',
  sales_outreach: '销售拓展专员', support_responder: '客户支持专员', legal_compliance: '法律合规顾问',
};

const MetricCard: React.FC<{ label: string; value: number; suffix?: string; kids?: React.ReactNode }> = ({ label, value, suffix, kids }) => (
  <div className="p-3 rounded-lg border border-dark-border bg-dark-card">
    <div className="text-xs text-gray-500 mb-1">{label}</div>
    <div className="text-xl font-bold text-gray-100">{value}{suffix || ''}</div>
    {kids}
  </div>
);

const AgentInsightPage: React.FC = () => {
  const { agentId } = useParams<{ agentId: string }>();
  const nav = useNavigate();
  const [insight, setInsight] = useState<AgentInsight | null>(null);
  const [allInsights, setAllInsights] = useState<Record<string, AgentInsight>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      if (agentId) {
        const d = await insightApi.get(agentId);
        setInsight(d);
      }
      const all = await insightApi.all();
      setAllInsights(all || {});
    } catch { /* ok */ }
    finally { setLoading(false); }
  }, [agentId]);

  useEffect(() => { load(); }, [load]);

  const refresh = async () => {
    try { await insightApi.refresh(); toast.success('已刷新'); load(); } catch { toast.error('刷新失败'); }
  };

  const trend = (val: number) => {
    if (val >= 0.8) return <TrendingUp className="w-3 h-3 text-green-400" />;
    if (val >= 0.5) return <Minus className="w-3 h-3 text-yellow-400" />;
    return <TrendingDown className="w-3 h-3 text-red-400" />;
  };

  const renderOverview = () => (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-4 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100">Agent 能力仪表板</h1>
          <p className="text-xs text-gray-500 mt-1">{Object.keys(allInsights).length} 个 Agent 已记录</p>
        </div>
        <Button variant="primary" size="sm" onClick={refresh} icon={<RefreshCw className="w-3.5 h-3.5" />}>刷新数据</Button>
      </div>

      {loading ? <div className="text-sm text-gray-500">加载中...</div> : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(allInsights).map(([id, ins]) => (
            <motion.div key={id} layout whileHover={{ y: -1 }}
              className="rounded-xl border border-dark-border bg-dark-card p-5 cursor-pointer hover:border-primary/40"
              onClick={() => nav(`/core/agent-insight/${id}`)}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-gray-100">{AGENT_NAMES[id] || id}</span>
                <Zap className={`w-4 h-4 ${ins.first_pass_rate >= 0.7 ? 'text-green-400' : ins.first_pass_rate >= 0.4 ? 'text-yellow-400' : 'text-red-400'}`} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center gap-1"><span className="text-gray-500">一通过率</span>{trend(ins.first_pass_rate)}<span className="ml-auto text-gray-200">{(ins.first_pass_rate * 100).toFixed(0)}%</span></div>
                <div className="flex items-center gap-1"><span className="text-gray-500">驳回率</span>{ins.rejection_rate > 0.3 ? <TrendingDown className="w-3 h-3 text-red-400" /> : <Minus className="w-3 h-3 text-yellow-400" />}<span className="ml-auto text-gray-200">{(ins.rejection_rate * 100).toFixed(0)}%</span></div>
                <div className="flex items-center gap-1"><span className="text-gray-500">QA回退率</span><span className="ml-auto text-gray-200">{(ins.qa_rollback_rate * 100).toFixed(0)}%</span></div>
                <div className="flex items-center gap-1"><span className="text-gray-500">运行次数</span><span className="ml-auto text-gray-200">{ins.total_runs}</span></div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  );

  if (!agentId) return renderOverview();

  const ins = insight;
  if (!ins) return <div className="p-4 text-sm text-gray-500">加载中...</div>;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <Button variant="ghost" onClick={() => nav('/core/agent-insight')}><ArrowLeft className="w-4 h-4" /></Button>
        <h1 className="text-xl font-bold text-gray-100">{AGENT_NAMES[agentId] || agentId}</h1>
        <span className="text-xs text-gray-500">{agentId}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="一通过率" value={(ins.first_pass_rate * 100).toFixed(0)} suffix="%" kids={trend(ins.first_pass_rate)} />
        <MetricCard label="驳回率" value={(ins.rejection_rate * 100).toFixed(0)} suffix="%" kids={ins.rejection_rate > 0.3 ? <TrendingDown className="w-3 h-3 text-red-400" /> : <Minus className="w-3 h-3 text-yellow-400" />} />
        <MetricCard label="QA回退率" value={(ins.qa_rollback_rate * 100).toFixed(0)} suffix="%" />
        <MetricCard label="运行次数" value={ins.total_runs} />
      </div>

      <Card>
        <CardHeader title="最近运行" />
        <CardContent>
          {(ins.recent_runs || []).length === 0 ? <div className="text-xs text-gray-500">暂无数据</div> : (
            <div className="space-y-2">
              {ins.recent_runs?.map((r, i) => (
                <div key={i} className="text-xs p-2 rounded border border-dark-border flex items-center gap-3">
                  <span className="text-gray-500 w-28 truncate">{r.project || '-'}</span>
                  <span className="text-gray-400">{r.phase || '-'}</span>
                  {r.pass_rate != null && <span className={r.pass_rate >= 0.8 ? 'text-green-400' : 'text-yellow-400'}>通过率 {(r.pass_rate * 100).toFixed(0)}%</span>}
                  {r.error && <span className="text-red-400 truncate flex-1">{r.error}</span>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
};

export default AgentInsightPage;
