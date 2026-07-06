import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { ArrowLeft, Wrench, RefreshCw, CheckCircle, AlertTriangle, ExternalLink, Sparkles, Play, Zap, ShieldCheck } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

const RepairCenter: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);
  const navigate = useNavigate();
  const [expandedSkill, setExpandedSkill] = useState(false);
  const [expandedPreview, setExpandedPreview] = useState<string | null>(null);
  const [previewCode, setPreviewCode] = useState<Record<string, string>>({});
  const [history, setHistory] = useState<any>(null);

  const fetchHistory = async () => {
    try {
      const r = await fetch('/api/core/diagnostics/repairs/history');
      setHistory(await r.json());
    } catch { }
  };

  const [goals, setGoals] = useState<any>(null);
  const [executingGoal, setExecutingGoal] = useState<string | null>(null);

  const fetchGoals = async () => {
    try {
      const r = await fetch('/api/core/diagnostics/goals');
      setGoals(await r.json());
    } catch { }
  };

  const executeGoal = async (id: string) => {
    setExecutingGoal(id);
    try {
      const r = await fetch(`/api/core/diagnostics/goals/${id}/execute`, { method: 'POST' });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert(err.detail || '执行失败');
      }
      fetchGoals();
      fetchHistory();
    } catch { }
    finally { setExecutingGoal(null); }
  };

  const fetchRepairs = async () => {
    setLoading(true);
    try {
      // Try cached first — instant if fresh
      const getR = await fetch('/api/core/diagnostics/repairs-latest');
      const getData = await getR.json();
      if (!getData.needs_diagnostics) {
        setData(getData);
        setLoading(false);
        return;
      }
      // Cold cache — fall back to full scan
      const r = await fetch('/api/core/diagnostics/repairs', { method: 'POST' });
      setData(await r.json());
    } catch { }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchRepairs(); fetchHistory(); fetchGoals(); }, []);
  useEffect(() => {
    const onFocus = () => { fetchRepairs(); fetchHistory(); fetchGoals(); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  const applyAutoFix = async (skillId: string, scope: string) => {
    setApplying(skillId);
    try {
      const base = scope === 'engine' 
        ? '/api/core/skills' 
        : '/api/core/workspace/skills';
      await fetch(`${base}/${skillId}/apply-lint-fix`, { method: 'POST' });
      fetchRepairs();
    } catch { }
    finally { setApplying(null); }
  };

  const navigateTo = (path: string) => {
    const loc = path.startsWith('http') ? path : `/workspace/agents?edit=${path}`;
    window.open(loc, path.startsWith('http') ? '_blank' : '_self');
  };

  const repairs = data?.repairs || [];
  const summary = data?.summary || {};

  const sourceConfig: Record<string, { icon: React.ReactNode; title: string; color: string }> = {
    skill_lint: { icon: <Sparkles className="w-4 h-4" />, title: 'Skill Lint', color: 'text-violet-400' },
    agent_shell: { icon: <AlertTriangle className="w-4 h-4" />, title: '空壳 Agent', color: 'text-yellow-400' },
    wiki_health: { icon: <ExternalLink className="w-4 h-4" />, title: 'Wiki 健康', color: 'text-blue-400' },
    capability: { icon: <Play className="w-4 h-4" />, title: '能力健康', color: 'text-amber-400' },
    lsp: { icon: <AlertTriangle className="w-4 h-4" />, title: 'LSP 类型错误', color: 'text-red-400' },
    governance: { icon: <ShieldCheck className="w-4 h-4" />, title: '治理', color: 'text-amber-400' },
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">修复中心</h1>
          <p className="text-xs text-gray-500 mt-0.5">发现 {summary.total_issues || 0} 个可修复问题 · {summary.auto_fixable || 0} 个可自动修复</p>
        </div>
        <Button variant="ghost" size="sm" onClick={fetchRepairs} loading={loading}>
          <RefreshCw className="w-3 h-3 mr-1" />刷新
        </Button>
      </div>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      {history && history.summary && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-medium text-gray-100">自主修复历史</span>
              <span className="text-[10px] text-gray-500">系统自动执行 · 只读</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="rounded-md bg-gray-800/40 p-2 text-center">
                <div className="text-lg font-semibold text-emerald-400">{history.summary.healing_actions ?? 0}</div>
                <div className="text-[11px] text-gray-500">流水线自愈动作</div>
              </div>
              <div className="rounded-md bg-gray-800/40 p-2 text-center">
                <div className="text-lg font-semibold text-violet-400">{history.summary.drafts_total ?? 0}</div>
                <div className="text-[11px] text-gray-500">自学习草稿 · 待审 {history.summary.drafts_pending ?? 0}</div>
              </div>
              <div className="rounded-md bg-gray-800/40 p-2 text-center">
                <div className="text-lg font-semibold text-blue-400">{history.summary.reviews_run ?? 0}</div>
                <div className="text-[11px] text-gray-500">代码审查 · clean {history.code_reviews?.clean_rate ?? '—'}</div>
              </div>
            </div>
            {Array.isArray(history.auto_learned_skills) && history.auto_learned_skills.length > 0 && (
              <div className="space-y-1">
                <div className="text-[11px] text-gray-500 mb-1">最近自学习草稿</div>
                {history.auto_learned_skills.slice(0, 6).map((d: any, i: number) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-gray-800/50">
                    <span className="text-gray-300 truncate">{d.name}</span>
                    <span className="flex items-center gap-2">
                      {d.confidence != null && <span className="text-gray-500">conf {Number(d.confidence).toFixed(2)}</span>}
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${d.status === 'pending_review' ? 'bg-yellow-500/20 text-yellow-300' : d.status === 'approved' ? 'bg-emerald-500/20 text-emerald-300' : d.status === 'rejected' ? 'bg-red-500/20 text-red-300' : 'bg-gray-600/30 text-gray-400'}`}>{d.status}</span>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {goals && Array.isArray(goals.goals) && goals.goals.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Wrench className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-medium text-gray-100">系统建议修复（诊断→修复闭环）</span>
              <span className="text-[10px] text-gray-500">
                {goals.auto_executable ?? 0} 项可执行 ·
                {goals.execute_enabled ? ' 已开启人工审批执行' : ' 执行未开启（AIPLAT_GOAL_EXECUTE_ENABLED=true）'}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {goals.goals.slice(0, 10).map((g: any) => (
                <div key={g.goal_id} className="flex items-center justify-between text-xs py-1.5 border-b border-gray-800/50">
                  <div className="min-w-0 flex-1">
                    <div className="text-gray-200 truncate">{g.title}</div>
                    <div className="text-[10px] text-gray-500">{g.goal_type} · {g.estimated_impact}</div>
                  </div>
                  <div className="flex items-center gap-2 ml-2 shrink-0">
                    {g.auto_executable
                      ? <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300">可执行</span>
                      : <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-600/30 text-gray-400">需人工</span>}
                    {g.auto_executable && goals.execute_enabled && (
                      <Button variant="ghost" size="sm" loading={executingGoal === g.goal_id}
                        onClick={() => executeGoal(g.goal_id)}>
                        <Play className="w-3 h-3 mr-1" />执行
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {summary.needs_diagnostics && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="text-center py-10">
            <Zap className="w-10 h-10 text-primary mx-auto mb-3 opacity-60" />
            <p className="text-gray-200 text-sm font-medium mb-1">诊断数据尚未准备</p>
            <p className="text-gray-500 text-xs mb-4">请先运行诊断中心以发现可修复的问题，完成后返回此处即可看到修复建议</p>
            <Button variant="primary" onClick={() => navigate('/diagnostics')}>
              <Zap className="w-3 h-3 mr-1" />
              去诊断中心
            </Button>
          </CardContent>
        </Card>
      )}

      {!summary.needs_diagnostics && repairs.length === 0 && !loading && (
        <Card className="bg-dark-card border-dark-border">
          <CardContent className="py-8 text-center">
            <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2" />
            <p className="text-gray-300 text-sm">所有系统健康，暂无需要修复的问题</p>
          </CardContent>
        </Card>
      )}

      {repairs.map((repair: any, idx: number) => {
        const cfg = sourceConfig[repair.source] || { icon: <Wrench className="w-4 h-4" />, title: repair.source, color: 'text-gray-400' };

        return (
          <Card key={idx} className="bg-dark-card border-dark-border">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cfg.color}>{cfg.icon}</span>
                  <span className="text-sm font-medium text-gray-200">
                    {cfg.title}
                    {repair.score != null && (
                      <span className={`ml-2 text-xs ${repair.score >= 75 ? 'text-green-400' : repair.score >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {repair.score}/{repair.grade || '?'}
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-gray-500">
                    {repair.items?.length || repair.fixes?.length || 0} 个问题
                  </span>
                  {repair.auto_fix_total != null && repair.auto_fix_total > 0 && (
                    <span className="text-[10px] text-green-400 bg-green-900/20 px-1.5 py-0.5 rounded">可自动修复</span>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {/* Skill Lint repairs — grouped */}
                {repair.source === 'skill_lint' && (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs text-gray-500">
                        共 {repair.items?.length || 0} 个 Skill，
                        {repair.auto_fix_total || 0} 个可自动修复
                      </span>
                      <button
                        className="text-[10px] text-gray-500 hover:text-gray-300"
                        onClick={() => setExpandedSkill(!expandedSkill)}
                      >
                        {expandedSkill ? '收起' : '展开列表'}
                      </button>
                    </div>
                    {expandedSkill && (
                      <div className="space-y-1 max-h-64 overflow-y-auto border border-dark-border rounded p-2">
                        {repair.items?.map((item: any, i: number) => (
                          <div key={i} className="flex items-center justify-between text-xs py-0.5 hover:bg-dark-bg/50 rounded px-1">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-gray-300 truncate max-w-[120px]">{item.name}</span>
                              <span className="text-[10px] text-gray-600">({item.scope})</span>
                              {item.error_codes?.length > 0 && (
                                <span className="text-red-400 text-[10px] truncate">{item.error_codes.join(', ')}</span>
                              )}
                              {item.warning_count > 0 && (
                                <span className="text-yellow-400 text-[10px]">{item.warning_count}W</span>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              {item.auto_fix_count > 0 && (
                                <Button
                                  variant="primary" size="sm" loading={applying === item.skill_id}
                                  onClick={() => applyAutoFix(item.skill_id, item.scope)}
                                >
                                  <Wrench className="w-3 h-3 mr-1" />
                                  修复 ({item.auto_fix_count})
                                </Button>
                              )}
                              <Button variant="ghost" size="sm" onClick={() => {
                                navigate(item.scope === 'engine' ? `/core/skills?edit=${item.skill_id}` : `/workspace/skills?edit=${item.skill_id}`);
                              }}>
                                →
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Agent Shell repairs */}
                {repair.source === 'agent_shell' && (
                  <div>
                    <p className="text-xs text-gray-500 mb-2">{repair.detail}</p>
                    <div className="flex flex-wrap gap-1 mb-2">
                      {repair.items?.map((item: any, i: number) => (
                        <span key={i} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${
                          item.severity === 'error' ? 'bg-red-900/20 text-red-300' : 'bg-yellow-900/20 text-yellow-300'
                        }`}>
                          {item.dir}
                        </span>
                      ))}
                    </div>
                    {repair.can_auto_fill && (
                      <div className="flex items-center gap-2 mt-2">
                        <Button variant="primary" size="sm" onClick={() => navigateTo('/workspace/agents')}>
                          <Sparkles className="w-3 h-3 mr-1" />
                          打开 Agent 管理 — AI 智能填充
                        </Button>
                        <Button variant="secondary" size="sm" loading={applying === 'batch-fill'} onClick={async () => {
                          setApplying('batch-fill');
                          const names = (repair.items || []).map(
                            (item: any) => item.dir?.replace('workspace:', '') || item.dir
                          ).filter(Boolean);
                          if (names.length > 0) {
                            try {
                              await fetch('/api/core/workspace/agents/auto-fill-batch', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({names}),
                              });
                            } catch {}
                          }
                          setApplying(null);
                          fetchRepairs();
                        }}>
                          <Sparkles className="w-3 h-3 mr-1" />
                          批量 AI 填充 ({repair.items?.length || 0})
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {/* Wiki Health repairs */}
                {repair.source === 'wiki_health' && (
                  <div className="space-y-1">
                    {repair.items?.slice(0, 8).map((item: any, i: number) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] px-1 py-0.5 rounded ${
                            item.severity === 'high' ? 'bg-red-900/20 text-red-300' :
                              item.severity === 'medium' ? 'bg-yellow-900/20 text-yellow-300' :
                                'bg-dark-bg text-gray-400'
                          }`}>{item.type}</span>
                          <span className="text-gray-400">{item.page_a || item.page}</span>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => navigateTo(`/platform/kb?page=${item.page}`)}>
                          编辑 →
                        </Button>
                      </div>
                    ))}
                    {repair.items?.length > 8 && (
                      <p className="text-[10px] text-gray-600">还有 {repair.items.length - 8} 个问题</p>
                    )}
                  </div>
                )}

                {/* Capability repairs */}
                {repair.source === 'capability' && (
                  <div className="space-y-1">
                    {repair.items?.slice(0, 8).map((item: any, i: number) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] px-1 py-0.5 rounded ${
                            item.type === 'duplicate_entry' ? 'bg-red-900/20 text-red-300' :
                              item.type === 'orphan_agent' ? 'bg-yellow-900/20 text-yellow-300' :
                                'bg-dark-bg text-gray-400'
                          }`}>{item.type}</span>
                          <span className="text-gray-400">{item.name}</span>
                        </div>
                        <span className="text-gray-500 text-[10px]">{item.suggestion || item.detail}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Overview repairs */}
                {repair.source === 'overview' && (
                  <div className="space-y-1.5">
                    {repair.items?.map((item: any, i: number) => (
                      <div key={i} className="flex items-center justify-between text-xs py-1 px-1.5 rounded bg-dark-bg/50">
                        <div className="flex items-center gap-2">
                          <span className="text-red-400 text-[10px]">❌</span>
                          <span className="text-gray-300">{item.name}</span>
                        </div>
                        <span className="text-gray-500 text-[10px] text-right max-w-[60%]">{item.suggestion}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Arch Guard repairs */}
                {repair.source === 'arch_guard' && (
                  <div className="space-y-1">
                    <p className="text-[10px] text-gray-500 mb-1">
                      共 {repair.total_violations} 个违规 · 显示 {repair.items?.length || 0} 个代表性条目
                    </p>
                    <div className="max-h-48 overflow-y-auto space-y-0.5 border border-dark-border rounded p-1.5">
                      {repair.items?.map((item: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs py-0.5">
                          <span className="text-red-400 text-[10px] shrink-0">{item.section}</span>
                          <span className="text-gray-400 truncate flex-1 text-[10px]">{item.message?.slice(0, 80)}</span>
                          <span className="text-gray-600 text-[9px] truncate max-w-[120px]">{item.sample_file?.split(':')[0]?.split('/').slice(-2).join('/')}</span>
                          <a
                            href={`/system-graph?tab=code&node=${encodeURIComponent(item.sample_file?.split(':')[0] || '')}`}
                            className="text-blue-400 hover:text-blue-300 text-[9px] shrink-0"
                            title="在图谱中定位"
                          >🔍</a>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dead Code repairs */}
                {repair.source === 'dead_code' && (
                  <div className="space-y-1">
                    <p className="text-[10px] text-gray-500 mb-1">{repair.detail || ''}</p>
                    <div className="max-h-48 overflow-y-auto space-y-0.5 border border-dark-border rounded p-1.5">
                      {repair.items?.map((item: any, i: number) => (
                        <div key={i}>
                          <div className="flex items-center gap-2 text-xs py-0.5">
                            <span className="text-yellow-400 text-[10px] shrink-0">⚠️</span>
                            <span className="text-gray-400 truncate flex-1 text-[10px]">{item.file?.split('/').slice(-2).join('/')}</span>
                            <button
                              onClick={async () => {
                                if (expandedPreview === item.file) { setExpandedPreview(null); return; }
                                setExpandedPreview(item.file);
                                if (!previewCode[item.file]) {
                                  const r = await fetch(`/api/core/knowledge-graph/node/${encodeURIComponent(item.file)}`);
                                  const d = await r.json();
                                  setPreviewCode(prev => ({...prev, [item.file]: d.codeSnippet || ''}));
                                }
                              }}
                              className="text-gray-500 hover:text-gray-300 text-[9px] shrink-0"
                            >{expandedPreview === item.file ? '收起' : '👁'}</button>
                            <a
                              href={`/system-graph?tab=code&node=${encodeURIComponent(item.file || '')}`}
                              className="text-blue-400 hover:text-blue-300 text-[9px] shrink-0"
                              title="在图谱中定位"
                            >🔍</a>
                          </div>
                          {expandedPreview === item.file && previewCode[item.file] && (
                            <pre className="text-[9px] text-gray-500 max-h-32 overflow-auto bg-dark-bg rounded p-1.5 mt-0.5 mx-2 border border-dark-border">
                              {previewCode[item.file]?.slice(0, 500)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* LSP Fixable Errors */}
                {repair.source === 'lsp' && (
                  <div className="space-y-1">
                    <p className="text-[10px] text-gray-500 mb-1">{repair.detail || ''}</p>
                    <div className="max-h-48 overflow-y-auto space-y-0.5 border border-dark-border rounded p-1.5">
                      {repair.items?.map((item: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs py-0.5">
                          <span className="text-red-400 text-[10px] shrink-0">❌</span>
                          <span className="text-gray-500 text-[9px] shrink-0">{item.file?.split('/').slice(-2).join('/')}:{item.line}</span>
                          <span className="text-gray-400 truncate flex-1 text-[10px]" title={item.message}>{item.message?.slice(0, 80)}</span>
                          <span className="text-gray-600 text-[9px] shrink-0">{item.rule}</span>
                        </div>
                      ))}
                    </div>
                    {repair.warning_items?.length > 0 && (
                      <p className="text-[9px] text-gray-600 mt-1">{repair.warning_items.length} 个警告（非阻断）</p>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};

export default RepairCenter;
