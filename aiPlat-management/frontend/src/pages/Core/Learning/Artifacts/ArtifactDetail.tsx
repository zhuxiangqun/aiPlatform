import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, ExternalLink, RefreshCw, Wand2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Statistic, Tabs, toast } from '../../../../components/ui';
import { learningApi, type LearningArtifact } from '../../../../services';

function formatTs(v: any): string {
  if (v == null) return '-';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isFinite(n) && n > 1e12) return new Date(n).toISOString();
  if (Number.isFinite(n) && n > 1e9) return new Date(n * 1000).toISOString();
  return String(v);
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('已复制');
  } catch {
    toast.error('复制失败（浏览器权限限制）');
  }
}

const ArtifactDetail: React.FC = () => {
  const navigate = useNavigate();
  const { artifactId } = useParams();
  const [loading, setLoading] = useState(false);
  const [artifact, setArtifact] = useState<LearningArtifact | null>(null);
  const [genLoading, setGenLoading] = useState(false);

  const fetchOne = async () => {
    if (!artifactId) return;
    setLoading(true);
    try {
      const res = await learningApi.getArtifact(artifactId);
      setArtifact(res);
    } catch (e: any) {
      toast.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOne();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactId]);

  const kind = artifact?.kind || '-';
  const status = artifact?.status || '-';
  const target = artifact ? `${artifact.target_type}:${artifact.target_id}` : '-';
  const meta: any = artifact?.metadata || {};
  const payload: any = artifact?.payload || {};

  const releaseArtifactIds: string[] = useMemo(() => {
    if (kind !== 'release_candidate') return [];
    const ids = payload?.artifact_ids;
    return Array.isArray(ids) ? ids.filter((x) => typeof x === 'string') : [];
  }, [kind, payload]);

  const regressionEvidence: any = useMemo(() => {
    if (kind !== 'regression_report') return null;
    return payload?.deltas?.evidence || null;
  }, [kind, payload]);

  const decision: any = useMemo(() => {
    if (kind !== 'regression_report') return null;
    return payload?.decision || null;
  }, [kind, payload]);

  const evalSummary: any = useMemo(() => {
    if (kind !== 'evaluation_report') return null;
    const rep = payload || {};
    const issues = Array.isArray(rep.issues) ? rep.issues : [];
    return {
      pass: rep.pass,
      functionality: rep?.score?.functionality,
      regression: rep?.regression,
      issues,
      evidence_pack_id: rep?.evidence_pack_id,
      evidence_diff_id: rep?.evidence_diff_id,
      evidence_diff_summary: rep?.evidence_diff_summary,
    };
  }, [kind, payload]);

  const severityBadge = (sev: any) => {
    const s = String(sev || '').toUpperCase();
    if (s === 'P0') return 'error';
    if (s === 'P1') return 'warning';
    if (s === 'P2') return 'info';
    return 'default';
  };

  const evidencePackSummary: any = useMemo(() => {
    if (kind !== 'evidence_pack') return null;
    return { url: payload?.url, error: payload?.error };
  }, [kind, payload]);

  const evidenceDiffSummary: any = useMemo(() => {
    if (kind !== 'evidence_diff') return null;
    return { summary: payload?.summary, metrics: payload?.metrics, diff: payload?.diff };
  }, [kind, payload]);

  const runStateSummary: any = useMemo(() => {
    if (kind !== 'run_state') return null;
    const todo = Array.isArray(payload?.todo) ? payload.todo : [];
    const done = todo.filter((t: any) => String(t?.status || '').toLowerCase() === 'completed' || String(t?.status || '').toLowerCase() === 'done').length;
    return { locked: payload?.locked, next_step: payload?.next_step, todo_total: todo.length, todo_done: done };
  }, [kind, payload]);

  const evalPolicySummary: any = useMemo(() => {
    if (kind !== 'evaluation_policy') return null;
    return {
      thresholds: payload?.thresholds,
      regression_gate: payload?.regression_gate,
      default_tag_template: payload?.default_tag_template,
      templates: payload?.tag_templates ? Object.keys(payload.tag_templates) : [],
    };
  }, [kind, payload]);

  const tabs = useMemo(() => {
    return [
      {
        key: 'overview',
        label: '概览',
        children: (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-gray-200">基础信息</div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <Statistic title="Kind" value={kind} />
                  <Statistic title="Status" value={status} />
                  <Statistic title="Target" value={target} />
                  <Statistic title="Version" value={artifact?.version || '-'} />
                </div>
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                  <Statistic title="Created At" value={formatTs(artifact?.created_at)} />
                  <Statistic title="Run ID" value={artifact?.run_id || '-'} />
                  <Statistic title="Trace ID" value={artifact?.trace_id || '-'} />
                  <Statistic title="Artifact ID" value={artifact?.artifact_id || '-'} />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-gray-200">关键字段</div>
              </CardHeader>
              <CardContent>
                {kind === 'release_candidate' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div>
                      artifacts: <span className="text-gray-400">{releaseArtifactIds.length}</span>
                    </div>
                    <div>
                      expires_at: <span className="text-gray-400">{formatTs(meta?.expires_at)}</span>
                    </div>
                    <div>
                      ttl_seconds: <span className="text-gray-400">{meta?.ttl_seconds ?? '-'}</span>
                    </div>
                    <div>
                      rollback_regression_report_id:{' '}
                      <span className="text-gray-400">{meta?.rollback_regression_report_id ?? '-'}</span>
                    </div>
                  </div>
                ) : kind === 'regression_report' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div>
                      should_rollback: <span className="text-gray-400">{String(decision?.should_rollback ?? '-')}</span>
                    </div>
                    <div>
                      reason: <span className="text-gray-400">{decision?.reason ?? '-'}</span>
                    </div>
                    <div>
                      linked_current: <span className="text-gray-400">{(regressionEvidence?.linked_current_execution_ids || []).length}</span>
                    </div>
                    <div>
                      linked_baseline: <span className="text-gray-400">{(regressionEvidence?.linked_baseline_execution_ids || []).length}</span>
                    </div>
                  </div>
                ) : kind === 'evaluation_report' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div className="flex items-center gap-2">
                      <Badge variant={evalSummary?.pass ? 'success' : 'error'}>{evalSummary?.pass ? 'PASS' : 'FAIL'}</Badge>
                      {typeof evalSummary?.functionality !== 'undefined' && (
                        <Badge variant="info">functionality: {String(evalSummary.functionality)}</Badge>
                      )}
                      {evalSummary?.regression?.is_regression && <Badge variant="warning">Regression</Badge>}
                    </div>
                    <div>
                      issues: <span className="text-gray-400">{evalSummary?.issues?.length ?? 0}</span>
                    </div>
                    {evalSummary?.evidence_diff_summary && (
                      <div className="text-xs text-gray-400">evidence_diff: {String(evalSummary.evidence_diff_summary).slice(0, 200)}</div>
                    )}
                    <div className="flex flex-wrap gap-2 pt-1">
                      {evalSummary?.evidence_pack_id && (
                        <Button variant="secondary" icon={<ExternalLink size={14} />} onClick={() => navigate(`/core/learning/artifacts/${String(evalSummary.evidence_pack_id)}`)}>
                          打开 Evidence Pack
                        </Button>
                      )}
                      {evalSummary?.evidence_diff_id && (
                        <Button variant="secondary" icon={<ExternalLink size={14} />} onClick={() => navigate(`/core/learning/artifacts/${String(evalSummary.evidence_diff_id)}`)}>
                          打开 Evidence Diff
                        </Button>
                      )}
                    </div>
                  </div>
                ) : kind === 'evidence_pack' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div>
                      url: <span className="text-gray-400 break-all">{String(evidencePackSummary?.url || '-')}</span>
                    </div>
                    {evidencePackSummary?.error && (
                      <div>
                        error: <span className="text-gray-400 break-all">{String(evidencePackSummary.error)}</span>
                      </div>
                    )}
                  </div>
                ) : kind === 'evidence_diff' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div className="text-xs text-gray-400">{String(evidenceDiffSummary?.summary || '').slice(0, 240)}</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(evidenceDiffSummary?.metrics || {}).map(([k, v]) => (
                        <Badge key={k} variant="info">
                          {k}:{String(v)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : kind === 'run_state' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div>
                      locked: <span className="text-gray-400">{String(runStateSummary?.locked ?? '-')}</span>
                    </div>
                    <div>
                      todo: <span className="text-gray-400">{String(runStateSummary?.todo_done ?? 0)}</span> / {String(runStateSummary?.todo_total ?? 0)}
                    </div>
                    <div className="text-xs text-gray-400 break-words">next_step: {String(runStateSummary?.next_step || '').slice(0, 260) || '-'}</div>
                  </div>
                ) : kind === 'evaluation_policy' ? (
                  <div className="space-y-2 text-sm text-gray-200">
                    <div>
                      default_tag_template: <span className="text-gray-400">{String(evalPolicySummary?.default_tag_template || '-')}</span>
                    </div>
                    <div className="text-xs text-gray-400">
                      thresholds: <span className="text-gray-500">{Object.keys(evalPolicySummary?.thresholds || {}).join(',') || '-'}</span>
                    </div>
                    <div className="text-xs text-gray-400">
                      templates: <span className="text-gray-500">{(evalPolicySummary?.templates || []).join(',') || '-'}</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">无特定视图，详情请查看 Payload/Metadata。</div>
                )}
              </CardContent>
            </Card>
          </div>
        ),
      },
      ...(kind === 'evaluation_report'
        ? [
            {
              key: 'issues',
              label: `Issues（${Array.isArray(payload?.issues) ? payload.issues.length : 0}）`,
              children: (
                <div className="space-y-4">
                  {!Array.isArray(payload?.issues) || payload.issues.length === 0 ? (
                    <Card>
                      <CardContent>
                        <div className="text-sm text-gray-500">无 issues。</div>
                      </CardContent>
                    </Card>
                  ) : (
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <div className="text-sm font-semibold text-gray-200">Issues 列表</div>
                            <div className="text-xs text-gray-500 mt-1">按严重程度展示，P0/P1 优先修复</div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {payload?.evidence_pack_id && (
                              <Button variant="secondary" icon={<ExternalLink size={14} />} onClick={() => navigate(`/core/learning/artifacts/${String(payload.evidence_pack_id)}`)}>
                                Evidence Pack
                              </Button>
                            )}
                            {payload?.evidence_diff_id && (
                              <Button variant="secondary" icon={<ExternalLink size={14} />} onClick={() => navigate(`/core/learning/artifacts/${String(payload.evidence_diff_id)}`)}>
                                Evidence Diff
                              </Button>
                            )}
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-3">
                          {payload.issues.slice(0, 50).map((it: any, idx: number) => (
                            <div key={idx} className="rounded-lg border border-dark-border bg-dark-hover p-3">
                              <div className="flex items-start gap-2">
                                <Badge variant={severityBadge(it?.severity) as any}>{String(it?.severity || 'P?')}</Badge>
                                <div className="min-w-0 flex-1">
                                  <div className="text-sm text-gray-200 break-words">{String(it?.title || '')}</div>
                                  {it?.suggested_fix && <div className="text-xs text-gray-500 mt-1 break-words">{String(it.suggested_fix)}</div>}
                                  {it?.expected != null || it?.actual != null ? (
                                    <details className="mt-2">
                                      <summary className="text-xs text-gray-400 cursor-pointer select-none">查看 expected / actual</summary>
                                      <pre className="mt-2 text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
                                        {JSON.stringify({ expected: it?.expected, actual: it?.actual }, null, 2)}
                                      </pre>
                                    </details>
                                  ) : null}
                                  {it?.evidence ? (
                                    <details className="mt-2">
                                      <summary className="text-xs text-gray-400 cursor-pointer select-none">查看 evidence</summary>
                                      <pre className="mt-2 text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
                                        {JSON.stringify(it?.evidence, null, 2)}
                                      </pre>
                                    </details>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  <Card>
                    <CardHeader>
                      <div className="text-sm font-semibold text-gray-200">原始报告（折叠）</div>
                    </CardHeader>
                    <CardContent>
                      <details className="rounded-lg border border-dark-border bg-dark-hover p-3">
                        <summary className="text-xs text-gray-400 cursor-pointer select-none">展开 raw JSON</summary>
                        <pre className="mt-2 text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
                          {JSON.stringify(payload || {}, null, 2)}
                        </pre>
                      </details>
                    </CardContent>
                  </Card>
                </div>
              ),
            },
          ]
        : []),
      {
        key: 'links',
        label: '关联与跳转',
        children: (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-gray-200">快速跳转</div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {artifact?.trace_id && (
                    <Button variant="secondary" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/traces/${artifact.trace_id}`)}>
                      打开 Trace
                    </Button>
                  )}
                  {artifact?.run_id && (
                    <Button variant="secondary" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/graphs/${artifact.run_id}`)}>
                      打开 Run
                    </Button>
                  )}
                  <Button variant="ghost" onClick={() => navigate('/core/learning/artifacts')}>
                    返回列表
                  </Button>
                </div>
              </CardContent>
            </Card>

            {kind === 'release_candidate' && (
              <Card>
                <CardHeader>
                  <div className="text-sm font-semibold text-gray-200">候选包含的 artifacts</div>
                </CardHeader>
                <CardContent>
                  {releaseArtifactIds.length ? (
                    <div className="flex flex-col gap-2">
                      {releaseArtifactIds.map((id) => (
                        <div key={id} className="flex items-center justify-between gap-2">
                          <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{id}</code>
                          <div className="flex gap-2">
                            <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/core/learning/artifacts/${id}`)}>
                              打开
                            </Button>
                            <Button variant="ghost" icon={<Copy size={14} />} onClick={() => copyText(id)}>
                              复制
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500">该候选未包含 artifact_ids。</div>
                  )}
                </CardContent>
              </Card>
            )}

            {kind === 'release_candidate' && meta?.rollback_regression_report_id && (
              <Card>
                <CardHeader>
                  <div className="text-sm font-semibold text-gray-200">回滚原因（regression_report）</div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between gap-2">
                    <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(meta.rollback_regression_report_id)}</code>
                    <Button
                      variant="secondary"
                      icon={<ExternalLink size={14} />}
                      onClick={() => navigate(`/core/learning/artifacts/${String(meta.rollback_regression_report_id)}`)}
                    >
                      打开回滚报告
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        ),
      },
      {
        key: 'payload',
        label: 'Payload',
        children: (
          <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(payload || {}, null, 2)}
          </pre>
        ),
      },
      {
        key: 'metadata',
        label: 'Metadata',
        children: (
          <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(meta || {}, null, 2)}
          </pre>
        ),
      },
      {
        key: 'raw',
        label: 'Raw',
        children: (
          <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(artifact || {}, null, 2)}
          </pre>
        ),
      },
    ];
  }, [artifact, decision, kind, meta, navigate, payload, regressionEvidence, releaseArtifactIds, status, target]);

  const generatePromptRevision = async () => {
    if (!artifactId) return;
    setGenLoading(true);
    try {
      const res = await learningApi.autocaptureToPromptRevision({ artifact_id: artifactId, create_release_candidate: true });
      const rcId = res?.release_candidate?.artifact_id;
      const prId = res?.prompt_revision?.artifact_id;
      toast.success('已生成草案');
      if (rcId) navigate(`/core/learning/artifacts/${encodeURIComponent(String(rcId))}`);
      else if (prId) navigate(`/core/learning/artifacts/${encodeURIComponent(String(prId))}`);
      else await fetchOne();
    } catch (e: any) {
      toast.error('生成失败', String(e?.message || ''));
    } finally {
      setGenLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => navigate(-1)}>
              返回
            </Button>
            <h1 className="text-2xl font-semibold text-gray-200">Artifact 详情</h1>
            {artifact?.status && (
              <Badge variant={artifact.status === 'published' ? 'success' : artifact.status === 'rolled_back' ? 'error' : 'default'}>
                {artifact.status}
              </Badge>
            )}
            {artifact?.kind && <Badge variant="info">{artifact.kind}</Badge>}
          </div>
          <div className="text-sm text-gray-500 mt-1">
            <span>artifact_id: </span>
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{artifactId}</code>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchOne} loading={loading}>
            刷新
          </Button>
          {artifact?.kind === 'feedback_summary' && (
            <Button variant="primary" icon={<Wand2 size={16} />} onClick={generatePromptRevision} loading={genLoading}>
              生成 Prompt Revision
            </Button>
          )}
          {artifactId && (
            <Button variant="secondary" icon={<Copy size={16} />} onClick={() => copyText(artifactId)}>
              复制 ID
            </Button>
          )}
        </div>
      </div>

      {artifact ? <Tabs tabs={tabs} defaultActiveKey="overview" /> : <Card><CardContent><div className="text-sm text-gray-500">未加载到 artifact。</div></CardContent></Card>}
    </div>
  );
};

export default ArtifactDetail;
