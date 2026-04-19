import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { diagnosticsApi } from '../../services';
import { Card, CardContent, CardHeader, Badge, Button, Table } from '../../components/ui';
import { ActionableFixes } from '../../components/common/ActionableFixes';
import { Copy } from 'lucide-react';

const Doctor: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [runningSmoke, setRunningSmoke] = useState(false);

  const refresh = async () => {
    setError(null);
    const res = await diagnosticsApi.getDoctor();
    setData(res);
  };

  useEffect(() => {
    let mounted = true;
    (async () => {
      setError(null);
      try {
        const res = await diagnosticsApi.getDoctor();
        if (mounted) setData(res);
      } catch (e: any) {
        if (mounted) setError(e?.message || '加载失败');
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const jsonText = useMemo(() => JSON.stringify(data || {}, null, 2), [data]);
  const repo = data?.repo?.changeset || null;
  const changesets = data?.changesets || null;
  const repoActions = useMemo(() => {
    const a: Record<string, any> = {};
    if (data?.actions?.record_repo_changeset) a.record_repo_changeset = data.actions.record_repo_changeset;
    if (data?.actions?.run_repo_tests) a.run_repo_tests = data.actions.run_repo_tests;
    return Object.keys(a).length > 0 ? a : null;
  }, [data]);
  const changesetItems = Array.isArray(changesets?.items) ? changesets.items : [];
  const [repoPatchOpen, setRepoPatchOpen] = useState(false);
  const [repoPatchLoading, setRepoPatchLoading] = useState(false);
  const [repoPatch, setRepoPatch] = useState<string>('');
  const [stagedOpen, setStagedOpen] = useState(false);
  const [stagedLoading, setStagedLoading] = useState(false);
  const [stagedPreview, setStagedPreview] = useState<any>(null);

  const formatTs = (ts: any) => {
    const n = Number(ts);
    if (!Number.isFinite(n) || n <= 0) return '-';
    try {
      return new Date(n * 1000).toLocaleString();
    } catch {
      return String(ts);
    }
  };

  const statusVariant = (s: any) => {
    const v = String(s || '').toLowerCase();
    if (v === 'success' || v === 'ok' || v === 'completed') return 'success';
    if (v.includes('fail') || v === 'error') return 'error';
    if (v.includes('approval')) return 'warning';
    return 'default';
  };

  const openChangesetInSyscalls = (r: any) => {
    const q = new URLSearchParams();
    q.set('kind', 'changeset');
    if (r?.name) q.set('name', String(r.name));
    if (r?.approval_request_id) q.set('approval_request_id', String(r.approval_request_id));
    if (r?.target_type) q.set('target_type', String(r.target_type));
    if (r?.target_id) q.set('target_id', String(r.target_id));
    navigate(`/diagnostics/syscalls?${q.toString()}`);
  };

  const copyReport = async () => {
    try {
      await navigator.clipboard.writeText(jsonText);
    } catch (e) {
      console.error(e);
    }
  };

  const downloadReport = () => {
    const blob = new Blob([jsonText], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `doctor-report-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const runSmoke = async () => {
    setRunningSmoke(true);
    try {
      await diagnosticsApi.runE2ESmoke({});
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setRunningSmoke(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Doctor</h1>
          <p className="text-sm text-gray-500 mt-1">一键聚合诊断：健康检查、adapter 配置、autosmoke 配置与建议</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/onboarding"
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            去初始化向导
          </Link>
          <button
            onClick={runSmoke}
            disabled={runningSmoke}
            className="px-3 py-2 rounded-lg bg-primary text-white hover:opacity-90 disabled:opacity-60 transition-colors text-sm"
          >
            {runningSmoke ? '运行中…' : '一键跑 Smoke'}
          </button>
          <button
            onClick={copyReport}
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            复制报告
          </button>
          <button
            onClick={downloadReport}
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            下载 JSON
          </button>
          <button
            onClick={refresh}
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            刷新
          </button>
        </div>
      </div>

      {error && <div className="text-sm text-error bg-error-light border border-dark-border rounded-lg p-3">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Health</div>
              <Badge variant="info">/diagnostics/doctor</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(data?.health || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Context Status Sample</div>
              <Badge variant={data?.context_status_sample && Object.keys(data?.context_status_sample || {}).length > 0 ? 'success' : 'default'}>
                {data?.context_status_sample && Object.keys(data?.context_status_sample || {}).length > 0 ? 'ok' : 'n/a'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-gray-500 mb-2">来源：core prompt assemble（最小 messages），仅展示 context_status，不展示 prompt 内容</div>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(data?.context_status_sample || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Adapters</div>
              <Badge variant={(data?.adapters?.total || 0) > 0 ? 'success' : 'warning'}>{data?.adapters?.total ?? 0}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(data?.adapters || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Repo（AIPLAT_REPO_ROOT）</div>
              <Badge variant={repo?.status_lines > 0 ? 'warning' : 'success'}>{repo?.status_lines ?? 0} changes</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {!repo ? (
              <div className="text-sm text-gray-500">未配置 repo_root 或无法读取 git 状态（设置 AIPLAT_REPO_ROOT 后可显示）。</div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="text-xs text-gray-400">
                    <div>branch: <span className="text-gray-200">{repo?.branch || '-'}</span></div>
                    <div>head: <span className="text-gray-200">{(repo?.head || '').slice(0, 12) || '-'}</span></div>
                    <div>last_commit: <span className="text-gray-200">{(repo?.last_commit?.sha || '').slice(0, 12) || '-'}</span> <span className="text-gray-500">{repo?.last_commit?.subject || ''}</span></div>
                    <div>diff_sha256: <span className="text-gray-200">{(repo?.diff_sha256 || '').slice(0, 16) || '-'}</span></div>
                  </div>
                  <div className="text-xs text-gray-400">
                    <div>working_tree: <span className="text-gray-200">{repo?.working_tree?.files_changed ?? 0} files</span>, +{repo?.working_tree?.lines_added ?? 0}/-{repo?.working_tree?.lines_deleted ?? 0}</div>
                    <div>staged: <span className="text-gray-200">{repo?.staged?.files_changed ?? 0} files</span>, +{repo?.staged?.lines_added ?? 0}/-{repo?.staged?.lines_deleted ?? 0}</div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="secondary"
                    onClick={async () => {
                      const next = !repoPatchOpen;
                      setRepoPatchOpen(next);
                      if (next && !repoPatch) {
                        setRepoPatchLoading(true);
                        try {
                          const res = await diagnosticsApi.getRepoChangesetPatch();
                          setRepoPatch(String(res?.patch || ''));
                        } finally {
                          setRepoPatchLoading(false);
                        }
                      }
                    }}
                    loading={repoPatchLoading}
                  >
                    {repoPatchOpen ? '隐藏 diff' : '查看 diff'}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={async () => {
                      const next = !stagedOpen;
                      setStagedOpen(next);
                      if (next && !stagedPreview) {
                        setStagedLoading(true);
                        try {
                          const res = await diagnosticsApi.getRepoStagedPreview();
                          setStagedPreview(res || {});
                        } finally {
                          setStagedLoading(false);
                        }
                      }
                    }}
                    loading={stagedLoading}
                  >
                    {stagedOpen ? '隐藏 staged' : '查看 staged'}
                  </Button>
                </div>

                {repoPatchOpen && (
                  <pre className="text-[11px] text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[420px]">
                    {repoPatch || '(empty)'}
                  </pre>
                )}

                {stagedOpen && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="text-xs text-gray-500">
                        staged: {stagedPreview?.staged?.files_changed ?? 0} files, +{stagedPreview?.staged?.lines_added ?? 0}/-{stagedPreview?.staged?.lines_deleted ?? 0}
                      </div>
                      {stagedPreview?.suggested_commit_message && (
                        <Button
                          variant="ghost"
                          icon={<Copy size={14} />}
                          onClick={() => navigator.clipboard.writeText(String(stagedPreview?.suggested_commit_message || ''))}
                          title="复制建议 commit message"
                        />
                      )}
                    </div>
                    {stagedPreview?.suggested_commit_message && (
                      <div className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-2">
                        <span className="text-gray-500">suggested:</span>{' '}
                        <span className="text-gray-200">{String(stagedPreview?.suggested_commit_message || '')}</span>
                      </div>
                    )}
                    <pre className="text-[11px] text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[420px]">
                      {String(stagedPreview?.patch || '(empty)')}
                    </pre>
                  </div>
                )}

                {repoActions && repo?.status_lines > 0 ? (
                  <div>
                    <div className="text-xs text-gray-500 mb-1">一键动作（会进入 ChangeSet 审计时间线）</div>
                    <ActionableFixes actions={repoActions} recommendations={[]} onAfterAction={refresh} />
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">当前工作区无变更，或未提供记录动作。</div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Recent ChangeSets</div>
              <div className="flex items-center gap-2">
                <Link
                  to="/diagnostics/syscalls?kind=changeset"
                  className="text-xs text-primary hover:underline"
                  title="打开 Syscalls 并筛选 kind=changeset"
                >
                  打开 Syscalls
                </Link>
                <Button
                  variant="ghost"
                  icon={<Copy size={14} />}
                  onClick={() => navigator.clipboard.writeText(`${window.location.origin}/diagnostics/syscalls?kind=changeset`)}
                />
                <Badge variant="info">{changesets?.total ?? 0}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {changesetItems.length === 0 ? (
              <div className="text-sm text-gray-500">暂无变更审计（changeset）记录</div>
            ) : (
              <Table
                columns={[
                  { key: 'created_at', title: '时间', width: 170, render: (_: any, r: any) => <span className="text-xs text-gray-300">{formatTs(r.created_at)}</span> },
                  { key: 'name', title: 'name', width: 200, render: (_: any, r: any) => <span className="text-xs text-gray-200">{r.name}</span> },
                  { key: 'status', title: 'status', width: 110, render: (_: any, r: any) => <Badge variant={statusVariant(r.status)}>{String(r.status || '-')}</Badge> },
                  {
                    key: 'tests',
                    title: 'tests',
                    width: 140,
                    render: (_: any, r: any) => {
                      const ec = r?.result?.tests?.exit_code;
                      const ms = r?.result?.tests?.duration_ms;
                      if (ec === undefined || ec === null) return <span className="text-xs text-gray-500">-</span>;
                      return (
                        <div className="flex items-center gap-2">
                          <Badge variant={Number(ec) === 0 ? 'success' : 'error'}>{String(ec)}</Badge>
                          <span className="text-xs text-gray-400">{ms != null ? `${ms}ms` : ''}</span>
                        </div>
                      );
                    },
                  },
                  {
                    key: 'staged',
                    title: 'staged',
                    width: 160,
                    render: (_: any, r: any) => {
                      const cnt = r?.result?.staged_files_count ?? r?.result?.staged?.files_changed;
                      const sha = String(r?.result?.staged_patch_sha256 || '');
                      return (
                        <span className="text-xs text-gray-400">
                          {cnt != null ? `${cnt}f` : '-'} {sha ? sha.slice(0, 8) : ''}
                        </span>
                      );
                    },
                  },
                  {
                    key: 'diff',
                    title: 'diff',
                    width: 160,
                    render: (_: any, r: any) => {
                      const full = String(r?.result?.diff_sha256 || r?.result?.template_sha256 || '');
                      const short = full ? full.slice(0, 16) : '-';
                      return (
                        <div className="flex items-center gap-1">
                          <span className="text-xs text-gray-400">{short}</span>
                          {full && (
                            <Button
                              variant="ghost"
                              icon={<Copy size={14} />}
                              onClick={(e: any) => {
                                e?.stopPropagation?.();
                                navigator.clipboard.writeText(full);
                              }}
                              title="复制 diff hash"
                            />
                          )}
                        </div>
                      );
                    },
                  },
                  {
                    key: 'target',
                    title: 'target',
                    width: 220,
                    render: (_: any, r: any) => (
                      <span className="text-xs text-gray-400">
                        {r.target_type || '-'} / {String(r.target_id || '-').slice(0, 24)}
                      </span>
                    ),
                  },
                  {
                    key: 'note',
                    title: 'note',
                    render: (_: any, r: any) => <span className="text-xs text-gray-400">{r?.args?.note || '-'}</span>,
                  },
                  {
                    key: 'approval',
                    title: 'approval',
                    width: 160,
                    render: (_: any, r: any) => (
                      <span className="text-xs text-gray-400">{r.approval_request_id ? String(r.approval_request_id).slice(0, 12) : '-'}</span>
                    ),
                  },
                ]}
                data={changesetItems.slice(0, 20)}
                rowKey={(r: any) => String(r.id)}
                onRow={(r: any) => ({
                  onClick: () => openChangesetInSyscalls(r),
                  className: 'cursor-pointer',
                })}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Strong Gate（default tenant）</div>
              <Badge variant={data?.strong_gate?.enabled ? 'warning' : 'success'}>
                {data?.strong_gate?.enabled ? 'enabled' : 'off'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-gray-500 mb-3">
              {data?.strong_gate?.enabled ? '当前 default tenant 已开启强门禁（所有工具执行需审批）' : '当前未启用强门禁'}
            </div>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto mt-3">
              {JSON.stringify(data?.strong_gate || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">诊断即修复</div>
              <Badge variant="info">actions</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <ActionableFixes actions={data?.actions} recommendations={data?.recommendations} onAfterAction={refresh} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Raw</div>
              <Badge variant="default">JSON</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {jsonText}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Doctor;
