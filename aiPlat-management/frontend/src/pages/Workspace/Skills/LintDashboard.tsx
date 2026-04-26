import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../../components/common/PageHeader';
import { Alert, Badge, Button, Card, CardContent, CardHeader, Input, Modal, Select, Table, Textarea, toast } from '../../../components/ui';
import { jobApi, skillApi, workspaceSkillApi, type Job, type JobRun } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const JOB_ID = 'cron-skill-lint-scan';

const fmtTs = (ts?: number | null) => {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
};

const getPayload = (run: JobRun): any => {
  const r = (run as any)?.result;
  if (!r) return null;
  // job_scheduler stores: { ok: bool, payload: <ExecutionResult.payload> }
  return r?.payload || null;
};

const getTotals = (run: JobRun): any => getPayload(run)?.totals || null;
const getItems = (run: JobRun): any[] => getPayload(run)?.items || [];
const getTop = (run: JobRun): any => getPayload(run)?.top || null;
const isIssueCodeQuery = (q: string): boolean => {
  const s = String(q || '').trim().toLowerCase();
  if (!s) return false;
  // heuristic: snake_case-ish code names (e.g. missing_markdown / missing_permissions)
  return /^[a-z][a-z0-9_]{2,}$/.test(s) && s.includes('_');
};

const SkillLintDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [scope, setScope] = useState<'workspace' | 'engine' | 'workspace,engine'>('workspace');
  const [todoOpen, setTodoOpen] = useState(false);
  const [todoText, setTodoText] = useState('');
  const [blockedFilter, setBlockedFilter] = useState('');
  const [lintCache, setLintCache] = useState<Record<string, any>>({});
  const [lintModalOpen, setLintModalOpen] = useState(false);
  const [lintModalTitle, setLintModalTitle] = useState('');
  const [lintModalText, setLintModalText] = useState('');
  const [lintModalObj, setLintModalObj] = useState<any>(null);
  const [lintModalScope, setLintModalScope] = useState<'workspace' | 'engine'>('workspace');
  const [lintModalSkillId, setLintModalSkillId] = useState<string>('');
  const [applyRunning, setApplyRunning] = useState<Record<string, boolean>>({});
  const [explainOpen, setExplainOpen] = useState(false);
  const [explainTitle, setExplainTitle] = useState('');
  const [explainItems, setExplainItems] = useState<any[]>([]);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainScope, setExplainScope] = useState<'workspace' | 'engine'>('workspace');
  const [conflicts, setConflicts] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any[]>([]);
  const [obsHours, setObsHours] = useState<number>(24);

  const scopes = useMemo(() => {
    if (scope === 'workspace,engine') return ['workspace', 'engine'];
    return [scope];
  }, [scope]);

  const latestRun = runs?.[0] || null;
  const totals = latestRun ? getTotals(latestRun) : null;
  const blockedItems = latestRun ? getItems(latestRun).filter((x: any) => Boolean(x?.summary?.blocked)) : [];
  const blockedQuery = useMemo(() => (blockedFilter || '').trim().toLowerCase(), [blockedFilter]);
  const codeQuery = useMemo(() => (isIssueCodeQuery(blockedQuery) ? blockedQuery : ''), [blockedQuery]);

  const cacheKey = (scope0: string, skillId: string) => `${scope0}:${skillId}`;

  const ensureLintCached = async (scope0: string, skillId: string) => {
    const k = cacheKey(scope0, skillId);
    if (lintCache[k]) return lintCache[k];
    try {
      const res = scope0 === 'engine' ? await skillApi.lint(skillId) : await workspaceSkillApi.lint(skillId);
      setLintCache((p) => ({ ...(p || {}), [k]: res }));
      return res;
    } catch {
      // cache negative to prevent hot loop
      setLintCache((p) => ({ ...(p || {}), [k]: { error: 'fetch_failed' } }));
      return null;
    }
  };

  // When user types an issue code (e.g. missing_markdown), prefetch lint for blocked list (bounded).
  useEffect(() => {
    if (!codeQuery) return;
    const run = async () => {
      const list = blockedItems.slice(0, 50);
      for (const it of list) {
        const scope0 = String(it?.scope || 'workspace');
        const sid = String(it?.skill_id || '');
        if (!sid) continue;
        // eslint-disable-next-line no-await-in-loop
        await ensureLintCached(scope0, sid);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeQuery, blockedItems.length]);

  const blockedFiltered = useMemo(() => {
    const q = blockedQuery;
    if (!q) return blockedItems;
    return blockedItems.filter((it: any) => {
      const sid = String(it?.skill_id || '').toLowerCase();
      const name = String(it?.name || '').toLowerCase();
      const risk = String(it?.summary?.risk_level || '').toLowerCase();
      const scope0 = String(it?.scope || '').toLowerCase();

      // Regular substring matching
      if (sid.includes(q) || name.includes(q) || risk.includes(q) || scope0.includes(q)) return true;

      // Issue-code matching: requires fetching per-skill lint (only for blocked list, bounded).
      if (!codeQuery) return false;
      const k = cacheKey(scope0, sid);
      const lint = lintCache[k];
      const errors = Array.isArray(lint?.lint?.errors) ? lint.lint.errors : [];
      const warnings = Array.isArray(lint?.lint?.warnings) ? lint.lint.warnings : [];
      return errors.some((e: any) => String(e?.code || '').toLowerCase() === codeQuery) || warnings.some((w: any) => String(w?.code || '').toLowerCase() === codeQuery);
    });
  }, [blockedItems, blockedQuery, codeQuery, lintCache]);
  const top = latestRun ? getTop(latestRun) : null;
  const topErrors = Array.isArray(top?.errors) ? top.errors : [];
  const topWarnings = Array.isArray(top?.warnings) ? top.warnings : [];

  const load = async () => {
    setLoading(true);
    try {
      const j = await jobApi.get(JOB_ID);
      setJob(j);
      const rr = await jobApi.listRuns(JOB_ID, { limit: 50, offset: 0 });
      setRuns(rr.items || []);
    } catch (e: any) {
      setJob(null);
      setRuns([]);
      toast.error('加载巡检数据失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const loadConflictsAndMetrics = async () => {
    try {
      const resConf: any[] = [];
      const resMet: any[] = [];
      const resFun: any[] = [];
      let funnelMeta: any = null;
      if (scopes.includes('workspace')) {
        const c = await workspaceSkillApi.lintConflicts({ threshold: 0.35, min_overlap: 3, limit: 50 });
        resConf.push(...(c.items || []));
        const m = await workspaceSkillApi.skillMetrics({ since_hours: obsHours, limit: 8000 });
        resMet.push(...(m.items || []).map((x: any) => ({ ...x, scope: 'workspace' })));
        const f: any = await workspaceSkillApi.routingFunnel({ since_hours: obsHours, limit: 20000 });
        resFun.push(...(f.items || []).map((x: any) => ({ ...x, scope: 'workspace' })));
        funnelMeta = { ...(funnelMeta || {}), workspace: { totals: f?.totals, miss_rate: f?.miss_rate } };
      }
      if (scopes.includes('engine')) {
        const c = await skillApi.lintConflicts({ threshold: 0.35, min_overlap: 3, limit: 50 });
        resConf.push(...(c.items || []));
        const m = await skillApi.skillMetrics({ since_hours: obsHours, limit: 8000 });
        resMet.push(...(m.items || []).map((x: any) => ({ ...x, scope: 'engine' })));
        const f: any = await skillApi.routingFunnel({ since_hours: obsHours, limit: 20000 });
        resFun.push(...(f.items || []).map((x: any) => ({ ...x, scope: 'engine' })));
        funnelMeta = { ...(funnelMeta || {}), engine: { totals: f?.totals, miss_rate: f?.miss_rate } };
      }
      setConflicts(resConf);
      setMetrics(resMet);
      // store in metrics state as well, keep extra derived data in modal by reusing lintModalObj
      (window as any).__skillRoutingFunnel = resFun;
      (window as any).__skillRoutingFunnelMeta = funnelMeta;
    } catch (e: any) {
      toast.error('加载冲突/观测数据失败', String(e?.message || ''));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadConflictsAndMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, obsHours]);

  const openJobs = () => {
    try {
      window.open('/core/jobs', '_blank', 'noopener,noreferrer');
    } catch {
      // ignore
    }
  };

  const filterToSkills = (ids: string[]) => {
    navigate('/workspace/skills', { state: { filterSkillIds: ids } });
  };

  const handleRunNow = async () => {
    // Productized behavior:
    // - update job payload.scopes (best-effort)
    // - runNow and reload runs
    try {
      setLoading(true);
      const cur = job ? await jobApi.get(JOB_ID) : null;
      const payload = (cur?.payload || {}) as any;
      payload.scopes = scopes;
      await jobApi.update(JOB_ID, { payload });
      await jobApi.runNow(JOB_ID);
      await load();
      toast.success('已触发巡检');
    } catch (e: any) {
      toast.error('触发巡检失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const hintForCode = (code: string): string => {
    const c = String(code || '');
    // Keep it simple and deterministic (no LLM): map to the most common governance fixes.
    const m: Record<string, string> = {
      missing_output_schema: '为 SKILL.md 增加 output_schema，并保证字段稳定可回归。',
      missing_markdown: '在 output_schema 中补充 markdown 字段（type=string, required=true）。',
      invalid_markdown_schema: '修正 output_schema.markdown 为对象 schema，并确保 type=string。',
      markdown_type: '修正 output_schema.markdown.type 为 string。',
      missing_permissions: 'executable skill 必须声明 permissions（至少 llm:generate）。',
      weak_description: '补充 description（建议 >= 8 字），确保能被路由与解释。',
      long_description: '缩短 description（建议 <= 280 字），避免 L1 噪声影响匹配。',
      missing_triggers: '补充 trigger_conditions/trigger_keywords，提高召回与可解释性。',
      missing_input_schema: '补充 input_schema（字段/required/description），提高可测试性。',
      sop_missing_goal: '在 SOP 中补充“目标”章节。',
      sop_missing_flow: '在 SOP 中补充“流程/步骤”章节。',
      sop_missing_checklist: '在 SOP 中补充 Checklist/质量要求（便于回归）。',
    };
    return m[c] || '按 lint message 修复；优先处理 errors，再处理 warnings。';
  };

  const buildTodoMarkdown = (): string => {
    const runTs = latestRun ? fmtTs(latestRun.finished_at || latestRun.started_at || latestRun.created_at) : '-';
    const reqScopes = latestRun ? (getPayload(latestRun)?.request?.scopes || scopes) : scopes;
    const lines: string[] = [];
    lines.push(`# Skill Lint 修复待办`);
    lines.push('');
    lines.push(`- 时间：${runTs}`);
    lines.push(`- Scopes：${Array.isArray(reqScopes) ? reqScopes.join(',') : String(reqScopes)}`);
    lines.push(`- Totals：skills=${totals?.skills ?? '-'} blocked=${totals?.blocked ?? '-'} errors=${totals?.errors ?? '-'} warnings=${totals?.warnings ?? '-'}`);
    lines.push('');
    lines.push('## 1. Top Errors（优先级最高）');
    if (!topErrors.length) {
      lines.push('- （无）');
    } else {
      for (const it of topErrors.slice(0, 10)) {
        const code = String(it?.code || 'unknown');
        const count = Number(it?.count || 0);
        lines.push(`- [ ] ${code} ×${count}：${hintForCode(code)}`);
      }
    }
    lines.push('');
    lines.push('## 2. Blocked Skills（高风险 + errors，启用会被阻断）');
    if (!blockedItems.length) {
      lines.push('- （无）');
    } else {
      for (const it of blockedItems.slice(0, 50)) {
        const sid = String(it?.skill_id || '');
        const name = String(it?.name || '');
        const risk = String(it?.summary?.risk_level || '');
        lines.push(`- [ ] ${name} (${sid}) scope=${it?.scope} risk=${risk} E${it?.summary?.error_count}/W${it?.summary?.warning_count}`);
      }
    }
    lines.push('');
    lines.push('## 3. Top Warnings（可批量治理）');
    if (!topWarnings.length) {
      lines.push('- （无）');
    } else {
      for (const it of topWarnings.slice(0, 10)) {
        const code = String(it?.code || 'unknown');
        const count = Number(it?.count || 0);
        lines.push(`- [ ] ${code} ×${count}：${hintForCode(code)}`);
      }
    }
    lines.push('');
    return lines.join('\n');
  };

  const openTodo = () => {
    setTodoText(buildTodoMarkdown());
    setTodoOpen(true);
  };

  const downloadText = (filename: string, content: string, mime = 'text/plain;charset=utf-8') => {
    try {
      const blob = new Blob([content], { type: mime });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error('下载失败', String(e?.message || ''));
    }
  };

  const downloadTodoMd = () => {
    const ts = latestRun?.finished_at || latestRun?.started_at || latestRun?.created_at;
    const stamp = ts ? new Date(ts * 1000).toISOString().replace(/[:.]/g, '-') : 'latest';
    downloadText(`skill-lint-todo-${stamp}.md`, todoText || buildTodoMarkdown(), 'text/markdown;charset=utf-8');
  };

  const downloadLatestJson = () => {
    if (!latestRun) {
      toast.error('暂无巡检数据');
      return;
    }
    const payload = getPayload(latestRun) || {};
    const ts = latestRun?.finished_at || latestRun?.started_at || latestRun?.created_at;
    const stamp = ts ? new Date(ts * 1000).toISOString().replace(/[:.]/g, '-') : 'latest';
    downloadText(`skill-lint-report-${stamp}.json`, JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
  };

  const copyTodo = async () => {
    try {
      await navigator.clipboard.writeText(todoText || '');
      toast.success('已复制到剪贴板');
    } catch (e: any) {
      toast.error('复制失败', String(e?.message || ''));
    }
  };

  const openLintModal = async (scope0: string, skillId: string, name: string) => {
    const detail = await ensureLintCached(scope0, skillId);
    const txt = JSON.stringify(detail || {}, null, 2);
    setLintModalTitle(`Lint：${name} (${skillId}) [${scope0}]`);
    setLintModalText(txt);
    setLintModalObj(detail || null);
    setLintModalScope(scope0 === 'engine' ? 'engine' : 'workspace');
    setLintModalSkillId(String(skillId || ''));
    setLintModalOpen(true);
  };

  const applyFix = async (scope0: string, skillId: string, fixId: string) => {
    const key = `${scope0}:${skillId}:${fixId}`;
    setApplyRunning((p) => ({ ...(p || {}), [key]: true }));
    try {
      const api = scope0 === 'engine' ? skillApi : workspaceSkillApi;
      const res: any = await (api as any).applyLintFix(skillId, { fix_ids: [fixId], dry_run: false });
      toast.success('已应用修复');
      // refresh cache + modal content
      setLintCache((p) => {
        const next = { ...(p || {}) };
        delete next[cacheKey(scope0, skillId)];
        return next;
      });
      const detail = await ensureLintCached(scope0, skillId);
      setLintModalObj(detail || null);
      setLintModalText(JSON.stringify(detail || {}, null, 2));
      return res;
    } catch (e: any) {
      toastGateError(e, '应用修复失败');
    } finally {
      setApplyRunning((p) => ({ ...(p || {}), [key]: false }));
    }
  };

  const openExplain = async (r: any) => {
    const scope0 = String(r?.scope || '');
    const skillId = String(r?.name || '');
    setExplainScope(scope0 === 'engine' ? 'engine' : 'workspace');
    setExplainTitle(`${scope0}:${skillId}`);
    setExplainOpen(true);
    setExplainItems([]);
    setExplainLoading(true);
    try {
      const api = scope0 === 'engine' ? skillApi : workspaceSkillApi;
      const res: any = await (api as any).routingExplain({ since_hours: obsHours, limit: 50, skill_id: skillId, selected_kind: 'skill' });
      setExplainItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      toastGateError(e, '加载 routing_explain 失败');
    } finally {
      setExplainLoading(false);
    }
  };

  const runColumns = useMemo(
    () => [
      { title: '时间', key: 'time', width: 190, render: (_: unknown, r: JobRun) => fmtTs(r.finished_at || r.started_at || r.created_at) },
      { title: '状态', key: 'status', width: 110, render: (_: unknown, r: JobRun) => <Badge variant={(r.status || '').includes('fail') ? ('error' as any) : ('success' as any)}>{r.status}</Badge> },
      {
        title: 'Skills',
        key: 'skills',
        width: 90,
        align: 'center' as const,
        render: (_: unknown, r: JobRun) => String(getTotals(r)?.skills ?? '-'),
      },
      {
        title: 'Blocked',
        key: 'blocked',
        width: 90,
        align: 'center' as const,
        render: (_: unknown, r: JobRun) => {
          const v = Number(getTotals(r)?.blocked ?? 0);
          return <Badge variant={v > 0 ? ('error' as any) : ('success' as any)}>{v}</Badge>;
        },
      },
      { title: 'Errors', key: 'errors', width: 90, align: 'center' as const, render: (_: unknown, r: JobRun) => String(getTotals(r)?.errors ?? '-') },
      { title: 'Warnings', key: 'warnings', width: 100, align: 'center' as const, render: (_: unknown, r: JobRun) => String(getTotals(r)?.warnings ?? '-') },
      {
        title: 'Scopes',
        key: 'scopes',
        width: 140,
        render: (_: unknown, r: JobRun) => {
          const sc = getPayload(r)?.request?.scopes;
          return Array.isArray(sc) ? sc.join(',') : '-';
        },
      },
    ],
    []
  );

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Skill Lint 巡检" description="基于定时 Job（cron-skill-lint-scan）的质量巡检与趋势视图（JSON+Markdown 契约 / 权限风险 / SOP 质量）。" />

      {!job && (
        <Alert type="warning" title="未发现巡检 Job">
          <div className="text-sm text-gray-300">
            当前未找到 job_id=<code className="px-1">cron-skill-lint-scan</code>。请确认服务启动后已启用 Jobs（AIPLAT_ENABLE_JOBS=true）且未禁用
            Skill Lint Cron（AIPLAT_ENABLE_SKILL_LINT_CRON=true）。
          </div>
          <div className="mt-3">
            <Button variant="secondary" onClick={openJobs}>
              打开 Jobs/Cron
            </Button>
          </div>
        </Alert>
      )}

      <div className="flex items-center gap-2">
        <Select
          value={scope}
          onChange={(v: string) => setScope(v as any)}
          options={[
            { value: 'workspace', label: 'workspace' },
            { value: 'engine', label: 'engine' },
            { value: 'workspace,engine', label: 'workspace + engine' },
          ]}
        />
        <Button variant="secondary" onClick={load} disabled={loading}>
          刷新
        </Button>
        <Button variant="primary" onClick={handleRunNow} disabled={loading || !job}>
          立即巡检
        </Button>
        <Button variant="secondary" onClick={openTodo} disabled={!latestRun}>
          生成修复待办
        </Button>
        <Button variant="secondary" onClick={downloadLatestJson} disabled={!latestRun}>
          下载 JSON 报告
        </Button>
        <Button variant="secondary" onClick={openJobs}>
          Jobs/Cron
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card>
          <CardHeader title="最近一次" />
          <CardContent>
            <div className="text-sm text-gray-400">{latestRun ? fmtTs(latestRun.finished_at || latestRun.started_at) : '-'}</div>
            <div className="mt-2">
              <Badge variant={latestRun && (latestRun.status || '').includes('fail') ? ('error' as any) : ('success' as any)}>{latestRun?.status || 'n/a'}</Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="Skills" />
          <CardContent>
            <div className="text-2xl font-semibold text-gray-200">{totals?.skills ?? '-'}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="Blocked" />
          <CardContent>
            <div className="text-2xl font-semibold text-gray-200">{totals?.blocked ?? '-'}</div>
            <div className="text-xs text-gray-500 mt-1">高风险 + lint errors</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="Errors / Warnings" />
          <CardContent>
            <div className="text-2xl font-semibold text-gray-200">
              {totals?.errors ?? '-'} / {totals?.warnings ?? '-'}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader title="巡检历史（最近 50 次）" />
        <CardContent>
          <Table columns={runColumns as any} data={runs || []} rowKey="id" loading={loading} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card>
          <CardHeader title="Top Error Codes（最近一次）" />
          <CardContent>
            {topErrors.length === 0 ? (
              <div className="text-sm text-gray-500">暂无。</div>
            ) : (
              <div className="space-y-2">
                {topErrors.slice(0, 10).map((it: any) => (
                  <div key={String(it.code)} className="flex items-center justify-between">
                    <div className="text-sm text-gray-200">
                      <code className="text-gray-300">{String(it.code)}</code>
                      <span className="text-gray-500 ml-2">{hintForCode(String(it.code))}</span>
                    </div>
                    <Badge variant={'error' as any}>{Number(it.count || 0)}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="Top Warning Codes（最近一次）" />
          <CardContent>
            {topWarnings.length === 0 ? (
              <div className="text-sm text-gray-500">暂无。</div>
            ) : (
              <div className="space-y-2">
                {topWarnings.slice(0, 10).map((it: any) => (
                  <div key={String(it.code)} className="flex items-center justify-between">
                    <div className="text-sm text-gray-200">
                      <code className="text-gray-300">{String(it.code)}</code>
                      <span className="text-gray-500 ml-2">{hintForCode(String(it.code))}</span>
                    </div>
                    <Badge variant={'warning' as any}>{Number(it.count || 0)}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader title={`Blocked Skills（最近一次）`} />
        <CardContent>
          {blockedItems.length === 0 ? (
            <div className="text-sm text-gray-500">暂无 blocked。</div>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-3">
                <Badge variant={'error' as any}>{blockedItems.length}</Badge>
                <Input
                  value={blockedFilter}
                  onChange={(e: any) => setBlockedFilter(e.target.value)}
                  placeholder="过滤：skill_id/name/risk/scope"
                />
                <Button
                  variant="secondary"
                  onClick={() => filterToSkills(blockedFiltered.map((x: any) => String(x.skill_id || '')).filter(Boolean))}
                  disabled={blockedFiltered.length === 0}
                >
                  在 Skill库中过滤查看
                </Button>
              </div>
              <div className="space-y-2">
                {blockedFiltered.slice(0, 50).map((it: any) => (
                  <div key={`${it.scope}:${it.skill_id}`} className="flex items-center justify-between bg-dark-card border border-dark-border rounded-lg px-3 py-2">
                    <div className="min-w-0">
                      <div className="text-sm text-gray-200 truncate">
                        {it.name} <span className="text-gray-500">({it.skill_id})</span>
                      </div>
                      <div className="text-xs text-gray-500">
                        scope={it.scope} · risk={it.summary?.risk_level} · E{it.summary?.error_count}/W{it.summary?.warning_count}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="secondary" onClick={() => openLintModal(String(it.scope || 'workspace'), String(it.skill_id || ''), String(it.name || ''))}>
                        Lint
                      </Button>
                      <Button variant="secondary" onClick={() => filterToSkills([String(it.skill_id)])}>
                        查看
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="冲突检测（Routing Conflicts）" />
        <CardContent>
          {conflicts.length === 0 ? (
            <div className="text-sm text-gray-500">暂无明显冲突（基于 trigger_conditions/keywords 的 token 重合与 Jaccard）。</div>
          ) : (
            <Table
              rowKey={(r: any) => `${r.scope}:${r.skill_a?.skill_id}:${r.skill_b?.skill_id}`}
              data={conflicts.slice(0, 50)}
              columns={[
                { title: 'scope', dataIndex: 'scope', key: 'scope', width: 110 },
                {
                  title: 'A',
                  key: 'a',
                  render: (_: any, r: any) => (
                    <div className="text-sm text-gray-200">
                      {r?.skill_a?.name} <span className="text-gray-500">({r?.skill_a?.skill_id})</span>
                    </div>
                  ),
                },
                {
                  title: 'B',
                  key: 'b',
                  render: (_: any, r: any) => (
                    <div className="text-sm text-gray-200">
                      {r?.skill_b?.name} <span className="text-gray-500">({r?.skill_b?.skill_id})</span>
                    </div>
                  ),
                },
                { title: 'Jaccard', dataIndex: 'jaccard', key: 'jaccard', width: 90, render: (v: any) => Number(v || 0).toFixed(2) },
                {
                  title: '重合词（Top）',
                  key: 'overlap',
                  render: (_: any, r: any) => (
                    <div className="text-xs text-gray-400 break-words">{(r?.overlap_tokens || []).slice(0, 10).join(' · ') || '-'}</div>
                  ),
                },
              ]}
            />
          )}
          <div className="text-xs text-gray-500 mt-2">
            建议：为冲突对补充 <code>negative_triggers</code> 与更强的 <code>constraints</code>，并完善 <code>keywords.objects/actions</code> 以提高区分度。
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title={`Skill 调用观测（过去 ${obsHours} 小时）`} />
        <CardContent>
          <div className="flex items-center gap-2 mb-3">
            <Select
              value={String(obsHours)}
              onChange={(v: string) => setObsHours(Number(v || 24))}
              options={[
                { value: '1', label: '1h' },
                { value: '6', label: '6h' },
                { value: '24', label: '24h' },
                { value: '72', label: '72h' },
                { value: '168', label: '7d' },
              ]}
            />
            <Button variant="secondary" onClick={loadConflictsAndMetrics}>
              刷新观测
            </Button>
          </div>
          {metrics.length === 0 ? (
            <div className="text-sm text-gray-500">暂无 skill 调用数据（基于 syscall_events(kind=skill) 聚合）。</div>
          ) : (
            <Table
              rowKey={(r: any) => `${r.scope}:${r.name}`}
              data={metrics.slice(0, 50)}
              columns={[
                { title: 'scope', dataIndex: 'scope', key: 'scope', width: 110 },
                { title: 'skill', dataIndex: 'name', key: 'name' },
                { title: 'total', dataIndex: 'total', key: 'total', width: 80, align: 'center' as const },
                {
                  title: 'success',
                  key: 'success',
                  width: 90,
                  align: 'center' as const,
                  render: (_: any, r: any) => Number(r?.counts?.success || 0),
                },
                {
                  title: 'failed',
                  key: 'failed',
                  width: 90,
                  align: 'center' as const,
                  render: (_: any, r: any) => Number(r?.counts?.failed || 0),
                },
                {
                  title: 'policy_denied',
                  key: 'policy_denied',
                  width: 120,
                  align: 'center' as const,
                  render: (_: any, r: any) => Number(r?.counts?.policy_denied || 0),
                },
                {
                  title: 'approval_required',
                  key: 'approval_required',
                  width: 140,
                  align: 'center' as const,
                  render: (_: any, r: any) => Number(r?.counts?.approval_required || 0),
                },
                {
                  title: 'avg_ms',
                  key: 'avg',
                  width: 90,
                  align: 'center' as const,
                  render: (_: any, r: any) => Math.round(Number(r?.avg_duration_ms || 0)),
                },
                {
                  title: 'p95_ms',
                  key: 'p95',
                  width: 90,
                  align: 'center' as const,
                  render: (_: any, r: any) => (r?.p95_duration_ms ? Math.round(Number(r.p95_duration_ms)) : '-'),
                },
              ]}
            />
          )}
          <div className="text-xs text-gray-500 mt-2">
            说明：此处 routing-funnel 已同时使用 routing_decision + candidates_snapshot 计算 miss_rate / wrong_top1 / rank 指标；gap/top1_den/top1_ask 用于解释“为什么没选 top1”（被 deny/ask 或分数差距）。
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title={`路由漏斗（过去 ${obsHours} 小时）`} />
        <CardContent>
          {(() => {
            const funnel: any[] = (window as any).__skillRoutingFunnel || [];
            if (!Array.isArray(funnel) || funnel.length === 0) {
              return <div className="text-sm text-gray-500">暂无 routing 事件数据（syscall_events(kind=routing,name=skill_route)）。</div>;
            }
            return (
              <Table
                rowKey={(r: any) => `${r.scope}:${r.name}`}
                data={funnel.slice(0, 50)}
                columns={[
                  { title: 'scope', dataIndex: 'scope', key: 'scope', width: 110 },
                  { title: 'skill', dataIndex: 'name', key: 'name' },
                  {
                    title: 'why',
                    key: 'why',
                    width: 80,
                    align: 'center' as const,
                    render: (_: any, r: any) => (
                      <Button variant="secondary" onClick={() => openExplain(r)}>
                        explain
                      </Button>
                    ),
                  },
                  { title: 'selected', dataIndex: 'selected', key: 'selected', width: 90, align: 'center' as const },
                  { title: 'cand_any', dataIndex: 'candidate_any', key: 'candidate_any', width: 90, align: 'center' as const },
                  { title: 'cand_top1', dataIndex: 'candidate_top1', key: 'candidate_top1', width: 100, align: 'center' as const },
                  { title: 'wrong_top1', dataIndex: 'selected_not_top1', key: 'selected_not_top1', width: 110, align: 'center' as const },
                  { title: 'wrong_cand', dataIndex: 'selected_not_in_candidates', key: 'selected_not_in_candidates', width: 120, align: 'center' as const },
                  {
                    title: 'avg_rank',
                    key: 'avg_rank',
                    width: 90,
                    align: 'center' as const,
                    render: (_: any, r: any) => (r?.selected_rank_avg == null ? '-' : Number(r.selected_rank_avg).toFixed(1)),
                  },
                  {
                    title: 'gap',
                    key: 'gap',
                    width: 80,
                    align: 'center' as const,
                    render: (_: any, r: any) => (r?.score_gap_avg == null ? '-' : Number(r.score_gap_avg).toFixed(1)),
                  },
                  { title: 'rank≥3', dataIndex: 'selected_rank_ge3', key: 'selected_rank_ge3', width: 90, align: 'center' as const },
                  { title: 'top1_den', dataIndex: 'top1_permission_denied', key: 'top1_permission_denied', width: 90, align: 'center' as const },
                  { title: 'top1_ask', dataIndex: 'top1_approval_required', key: 'top1_approval_required', width: 90, align: 'center' as const },
                  { title: 'strict_miss', dataIndex: 'strict_missed_as_top1', key: 'strict_missed_as_top1', width: 100, align: 'center' as const },
                  { title: 'approval', dataIndex: 'approval_required', key: 'approval_required', width: 90, align: 'center' as const },
                  { title: 'denied', dataIndex: 'policy_denied', key: 'policy_denied', width: 90, align: 'center' as const },
                  { title: 'executed', dataIndex: 'executed', key: 'executed', width: 90, align: 'center' as const },
                  { title: 'success', dataIndex: 'success', key: 'success', width: 90, align: 'center' as const },
                  { title: 'failed', dataIndex: 'failed', key: 'failed', width: 90, align: 'center' as const },
                  {
                    title: 'cand→sel',
                    key: 'cand_to_sel',
                    width: 90,
                    align: 'center' as const,
                    render: (_: any, r: any) =>
                      r?.candidate_to_selected_rate == null ? '-' : `${Math.round(Number(r.candidate_to_selected_rate) * 100)}%`,
                  },
                  {
                    title: 'sel→exe',
                    key: 'sel_to_exe',
                    width: 90,
                    align: 'center' as const,
                    render: (_: any, r: any) =>
                      r?.selected_to_executed_rate == null ? '-' : `${Math.round(Number(r.selected_to_executed_rate) * 100)}%`,
                  },
                  {
                    title: 'exe SR',
                    key: 'exe_sr',
                    width: 90,
                    align: 'center' as const,
                    render: (_: any, r: any) => (r?.exec_success_rate == null ? '-' : `${Math.round(Number(r.exec_success_rate) * 100)}%`),
                  },
                ]}
              />
            );
          })()}
          {(() => {
            const meta: any = (window as any).__skillRoutingFunnelMeta || null;
            if (!meta) return null;
            return (
              <div className="text-xs text-gray-500 mt-2 space-y-1">
                {meta.workspace ? (
                  <div>
                    workspace miss_rate={(meta.workspace?.miss_rate == null ? '-' : `${Math.round(Number(meta.workspace.miss_rate) * 100)}%`)} totals=
                    {JSON.stringify(meta.workspace?.totals || {})}
                    {meta.workspace?.strict ? (
                      <span>
                        {' '}strict_miss_rate=
                        {meta.workspace.strict?.miss_rate == null ? '-' : `${Math.round(Number(meta.workspace.strict.miss_rate) * 100)}%`}{' '}
                        strict_totals={JSON.stringify(meta.workspace.strict?.totals || {})}
                      </span>
                    ) : null}
                  </div>
                ) : null}
                {meta.engine ? (
                  <div>
                    engine miss_rate={(meta.engine?.miss_rate == null ? '-' : `${Math.round(Number(meta.engine.miss_rate) * 100)}%`)} totals=
                    {JSON.stringify(meta.engine?.totals || {})}
                    {meta.engine?.strict ? (
                      <span>
                        {' '}strict_miss_rate=
                        {meta.engine.strict?.miss_rate == null ? '-' : `${Math.round(Number(meta.engine.strict.miss_rate) * 100)}%`}{' '}
                        strict_totals={JSON.stringify(meta.engine.strict?.totals || {})}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })()}
          <div className="text-xs text-gray-500 mt-2">
            解释：selected=进入 sys_skill_call 的调用尝试；approval/denied=门控结果；executed/success/failed=实际执行结果（来自 kind=skill）。
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="路由优化建议（从漏斗到修复）" />
        <CardContent>
          {(() => {
            const funnel: any[] = (window as any).__skillRoutingFunnel || [];
            const bad = (Array.isArray(funnel) ? funnel : [])
              .filter((x: any) => Number(x?.selected_not_top1 || 0) > 0 || Number(x?.selected_rank_ge3 || 0) > 0)
              .sort((a: any, b: any) => Number(b?.selected_not_top1 || 0) - Number(a?.selected_not_top1 || 0))
              .slice(0, 20);
            if (bad.length === 0) return <div className="text-sm text-gray-500">暂无明显错命中/低排名选择（wrong_top1/rank≥3）。</div>;
            return (
              <Table
                rowKey={(r: any) => `${r.scope}:${r.name}`}
                data={bad}
                columns={[
                  { title: 'scope', dataIndex: 'scope', key: 'scope', width: 110 },
                  { title: 'skill_id', dataIndex: 'name', key: 'name' },
                  { title: 'selected', dataIndex: 'selected', key: 'selected', width: 90, align: 'center' as const },
                  { title: 'wrong_top1', dataIndex: 'selected_not_top1', key: 'selected_not_top1', width: 110, align: 'center' as const },
                  { title: 'rank≥3', dataIndex: 'selected_rank_ge3', key: 'selected_rank_ge3', width: 90, align: 'center' as const },
                  {
                    title: '操作',
                    key: 'op',
                    width: 130,
                    render: (_: any, r: any) => (
                      <Button variant="secondary" onClick={() => openLintModal(String(r.scope || 'workspace'), String(r.name || ''), String(r.name || ''))}>
                        打开 Lint 并修复
                      </Button>
                    ),
                  },
                ]}
              />
            );
          })()}
          <div className="text-xs text-gray-500 mt-2">
            说明：打开 Lint 后会看到基于观测数据生成的修复项（如 <code>fix_routing_disambiguate</code>），可一键补充 constraints/negative_triggers，降低错命中。
          </div>
        </CardContent>
      </Card>

      <Modal
        open={todoOpen}
        onClose={() => setTodoOpen(false)}
        title="修复待办（可复制）"
        width={820}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTodoOpen(false)}>
              关闭
            </Button>
            <Button variant="secondary" onClick={downloadTodoMd} disabled={!todoText}>
              下载 .md
            </Button>
            <Button variant="secondary" onClick={copyTodo} disabled={!todoText}>
              复制
            </Button>
          </>
        }
      >
        <Textarea rows={18} value={todoText} onChange={(e: any) => setTodoText(e.target.value)} />
      </Modal>

      <Modal
        open={lintModalOpen}
        onClose={() => setLintModalOpen(false)}
        title={lintModalTitle || 'Lint'}
        width={820}
        footer={
          <>
            <Button variant="secondary" onClick={() => setLintModalOpen(false)}>
              关闭
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(lintModalText || '');
                  toast.success('已复制到剪贴板');
                } catch (e: any) {
                  toast.error('复制失败', String(e?.message || ''));
                }
              }}
              disabled={!lintModalText}
            >
              复制
            </Button>
          </>
        }
      >
        {Array.isArray(lintModalObj?.fixes) && lintModalObj.fixes.length > 0 && (
          <div className="mb-3 p-3 border border-dark-border rounded-lg bg-dark-card">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-gray-200">修复建议</div>
              <Badge variant={'warning' as any}>{lintModalObj.fixes.length}</Badge>
            </div>
            <div className="space-y-2">
              {lintModalObj.fixes.slice(0, 10).map((f: any) => (
                <div key={String(f.fix_id || f.issue_code)} className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm text-gray-200 truncate">
                      <code className="text-gray-300">{String(f.issue_code || '')}</code>
                      <span className="text-gray-500 ml-2">{String(f.title || '')}</span>
                    </div>
                    <div className="text-xs text-gray-500">
                      priority={String(f.priority || '')} · auto={String(!!f.auto_applicable)} · approval={String(!!f.requires_approval)}
                    </div>
                    {f?.markdown ? (
                      <details className="mt-1">
                        <summary className="text-xs text-gray-500 cursor-pointer">查看说明</summary>
                        <div className="mt-2 p-2 rounded bg-dark-bg border border-dark-border">
                          <pre className="text-xs text-gray-300 whitespace-pre-wrap">{String(f.markdown)}</pre>
                        </div>
                      </details>
                    ) : null}
                    {(f?.preview?.before_snippet || f?.preview?.after_snippet) && (
                      <details className="mt-1">
                        <summary className="text-xs text-gray-500 cursor-pointer">查看变更预览</summary>
                        <div className="mt-2 grid grid-cols-1 gap-2">
                          {f?.preview?.before_snippet && (
                            <div className="p-2 rounded bg-dark-bg border border-dark-border">
                              <div className="text-xs text-gray-500 mb-1">before</div>
                              <pre className="text-xs text-gray-300 whitespace-pre-wrap">{String(f.preview.before_snippet)}</pre>
                            </div>
                          )}
                          {f?.preview?.after_snippet && (
                            <div className="p-2 rounded bg-dark-bg border border-dark-border">
                              <div className="text-xs text-gray-500 mb-1">after</div>
                              <pre className="text-xs text-gray-300 whitespace-pre-wrap">{String(f.preview.after_snippet)}</pre>
                            </div>
                          )}
                        </div>
                      </details>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant={f.auto_applicable ? 'primary' : 'secondary'}
                      onClick={() => {
                        const ok = f.auto_applicable
                          ? true
                          : window.confirm(`该修复不是 auto_applicable，确认仍要应用？\n\n${String(f.title || f.fix_id || '')}`);
                        if (!ok) return;
                        applyFix(lintModalScope, lintModalSkillId, String(f.fix_id || ''));
                      }}
                      loading={applyRunning[`${lintModalScope}:${lintModalSkillId}:${String(f.fix_id || '')}`]}
                    >
                      应用修复
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(JSON.stringify(f.patch || {}, null, 2));
                          toast.success('已复制 patch');
                        } catch (e: any) {
                          toast.error('复制失败', String(e?.message || ''));
                        }
                      }}
                    >
                      复制 patch
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(String(f.markdown || ''));
                          toast.success('已复制说明');
                        } catch (e: any) {
                          toast.error('复制失败', String(e?.message || ''));
                        }
                      }}
                      disabled={!f.markdown}
                    >
                      复制说明
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        <Textarea rows={18} value={lintModalText} onChange={(e: any) => setLintModalText(e.target.value)} />
      </Modal>

      <Modal open={explainOpen} onClose={() => setExplainOpen(false)} title={`routing_explain：${explainTitle}`} width={920}>
        {explainLoading ? (
          <div className="text-sm text-gray-500">加载中...</div>
        ) : (
          <div className="space-y-2">
            {(!Array.isArray(explainItems) || explainItems.length === 0) && (
              <div className="text-sm text-gray-500">暂无 routing_explain（可能尚未产生，或 since_hours 太小）。</div>
            )}
            {Array.isArray(explainItems) &&
              explainItems.slice(0, 50).map((it: any, idx: number) => (
                <div key={idx} className="p-2 rounded border border-dark-border bg-dark-card">
                  <div className="text-xs text-gray-500">
                    decision_id=<code>{String(it?.routing_decision_id || '')}</code> · top1=<code>{String(it?.top1_skill_id || '')}</code> ·
                    gap=<code>{it?.score_gap == null ? '-' : Number(it.score_gap).toFixed(1)}</code> · gate=
                    <code>{String(it?.top1_gate_hint || '')}</code> · result=<code>{String(it?.result_status || '')}</code>
                  </div>
                  <div className="mt-1">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const did = String(it?.routing_decision_id || '');
                        if (!did) return;
                        navigate(`/diagnostics/routing-replay/${did}?scope=${explainScope}&since_hours=${obsHours}`);
                      }}
                    >
                      打开回放页
                    </Button>
                  </div>
                  <div className="text-xs text-gray-400 mt-1">{String(it?.query_excerpt || '')}</div>
                  <details className="mt-1">
                    <summary className="text-xs text-gray-500 cursor-pointer">candidates_top</summary>
                    <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(it?.candidates_top || [], null, 2)}</pre>
                  </details>
                </div>
              ))}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default SkillLintDashboard;
