import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Eye, RefreshCw, XCircle, ExternalLink, Play } from 'lucide-react';

import { approvalsApi, type ApprovalRequestSummary } from '../../../../services';
import { Badge, Button, Card, CardContent, CardHeader, Modal, Table, toast } from '../../../../components/ui';
import { toastGateError } from '../../../../utils/governanceError';

const Approvals: React.FC = () => {
  const [items, setItems] = useState<ApprovalRequestSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<any>(null);

  const fetchPending = async () => {
    setLoading(true);
    try {
      const res = await approvalsApi.listPending({ limit: 200, offset: 0 });
      setItems(res.items || []);
    } catch (e: any) {
      toastGateError(e, '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  const openDetail = async (requestId: string) => {
    try {
      const d = await approvalsApi.get(requestId);
      setDetail(d);
      setDetailOpen(true);
    } catch (e: any) {
      toastGateError(e, '加载失败');
    }
  };

  const approve = async (requestId: string) => {
    try {
      await approvalsApi.approve(requestId, 'admin', '');
      // For config publish/rollback, auto-replay after approval (product-level flow)
      try {
        const d = await approvalsApi.get(requestId);
        if (String(d?.operation || '') === 'config:publish' || String(d?.operation || '') === 'config:rollback') {
          await approvalsApi.replay(requestId, {});
          toast.success('已批准并执行（replay）');
        } else {
          toast.success('已批准');
        }
      } catch {
        toast.success('已批准');
      }
      fetchPending();
    } catch (e: any) {
      toastGateError(e, '批准失败');
    }
  };

  const reject = async (requestId: string) => {
    try {
      await approvalsApi.reject(requestId, 'admin', '');
      toast.success('已拒绝');
      fetchPending();
    } catch (e: any) {
      toastGateError(e, '拒绝失败');
    }
  };

  const columns = useMemo(
    () => [
      {
        title: 'request_id',
        dataIndex: 'request_id',
        key: 'request_id',
        render: (v: string) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '').slice(0, 12)}</code>,
      },
      {
        title: 'change_id',
        key: 'change_id',
        render: (_: any, r: ApprovalRequestSummary) => {
          const cid = (r as any).change_id;
          if (!cid) return <span className="text-xs text-gray-500">-</span>;
          return (
            <Link to={`/diagnostics/change-control/${encodeURIComponent(String(cid))}`} className="text-xs underline text-gray-300 hover:text-white">
              {String(cid)}
            </Link>
          );
        },
      },
      { title: 'operation', dataIndex: 'operation', key: 'operation' },
      {
        title: 'config',
        key: 'config',
        render: (_: any, r: ApprovalRequestSummary) => {
          const meta = (r as any)?.metadata || {};
          const opctx = (meta as any)?.operation_context || {};
          if (String(r.operation) !== 'config:publish') return <span className="text-xs text-gray-500">-</span>;
          return (
            <div className="text-xs text-gray-300">
              <div>
                <code>{String(opctx.asset_type || '-') }</code> · <code>{String(opctx.scope || '-') }</code> · <code>{String(opctx.channel || '-') }</code>
              </div>
              <div className="text-gray-500">tenant={String(opctx.tenant_id || meta.tenant_id || '-')}</div>
            </div>
          );
        },
      },
      {
        title: 'expires_at',
        key: 'expires_at',
        render: (_: any, r: ApprovalRequestSummary) => {
          const v: any = (r as any)?.expires_at;
          if (!v) return <span className="text-xs text-gray-500">-</span>;
          const ms = Date.parse(String(v));
          if (!Number.isFinite(ms)) return <span className="text-xs text-gray-500">{String(v)}</span>;
          const remain = ms - Date.now();
          const mins = Math.floor(remain / 60000);
          const warn = remain > 0 && remain < 60 * 60 * 1000;
          const expired = remain <= 0;
          return (
            <span className={`text-xs ${expired ? 'text-red-400' : warn ? 'text-yellow-400' : 'text-gray-300'}`}>
              {String(v).replace('T', ' ').slice(0, 19)}
              {remain > 0 ? `（剩余 ${mins}m）` : '（已过期）'}
            </span>
          );
        },
      },
      {
        title: 'status',
        dataIndex: 'status',
        key: 'status',
        render: (v: string) => <Badge variant={v === 'pending' ? 'warning' : 'default'}>{v}</Badge>,
      },
      {
        title: 'candidate',
        key: 'candidate',
        render: (_: any, r: ApprovalRequestSummary) => {
          const meta = r.metadata || {};
          const cid = (meta as any).candidate_id;
          return cid ? <code className="text-xs">{String(cid)}</code> : '-';
        },
      },
      {
        title: 'actions',
        key: 'actions',
        render: (_: any, r: ApprovalRequestSummary) => (
          <div className="flex items-center gap-2">
            <Button variant="ghost" icon={<Eye size={14} />} onClick={() => openDetail(r.request_id)}>
              查看
            </Button>
            {(r as any)?.change_id ? (
              <Link to={`/diagnostics/change-control/${encodeURIComponent(String((r as any).change_id))}`}>
                <Button variant="ghost">变更</Button>
              </Link>
            ) : null}
            <Button variant="secondary" icon={<CheckCircle2 size={14} />} onClick={() => approve(r.request_id)}>
              批准
            </Button>
            <Button variant="secondary" icon={<XCircle size={14} />} onClick={() => reject(r.request_id)}>
              拒绝
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Approvals</h1>
          <div className="text-sm text-gray-500 mt-1">审批中心（复用 core /api/core/approvals API）</div>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchPending} loading={loading}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">Pending Requests</div>
        </CardHeader>
        <CardContent>
          <Table columns={columns as any} data={items} rowKey={(r: any) => String(r.request_id)} />
        </CardContent>
      </Card>

      <Modal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detail?.request_id ? `Approval: ${detail.request_id}` : 'Approval'}
        width={920}
        footer={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-2">
              {detail?.change_id ? (
                <Link to={`/diagnostics/change-control/${encodeURIComponent(String(detail.change_id))}`}>
                  <Button variant="secondary" icon={<ExternalLink size={14} />}>
                    打开变更
                  </Button>
                </Link>
              ) : null}
              {detail?.request_id ? (
                <Link to={`/diagnostics/audit?request_id=${encodeURIComponent(String(detail.request_id))}`}>
                  <Button variant="secondary" icon={<ExternalLink size={14} />}>
                    打开审计
                  </Button>
                </Link>
              ) : null}
            </div>
            <Button onClick={() => setDetailOpen(false)}>关闭</Button>
          </div>
        }
      >
        {detail?.change_id ? (
          <div className="text-xs text-gray-400 mb-2">
            change_id:{' '}
            <Link
              to={`/diagnostics/change-control/${encodeURIComponent(String(detail.change_id))}`}
              className="underline text-gray-300 hover:text-white"
            >
              {String(detail.change_id)}
            </Link>
          </div>
        ) : null}
        {String(detail?.operation || '') === 'config:publish' || String(detail?.operation || '') === 'config:rollback' ? (
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-200">配置发布审批</div>
            </CardHeader>
            <CardContent>
              {(() => {
                const meta = detail?.metadata || {};
                const opctx = (meta as any)?.operation_context || {};
                const tenant = String(opctx.tenant_id || meta.tenant_id || 'default');
                const scope = String(opctx.scope || 'workspace');
                const channel = String(opctx.channel || 'stable');
                const asset = String(opctx.asset_type || '');
                const toVersion = String(opctx.version || '');
                const toVersion2 = String(opctx.to_version || '');
                const fromVersion = String(opctx.from_version || '');
                const summary = opctx.assessment_summary;
                const expiresAt = detail?.expires_at;
                return (
                  <div className="space-y-2 text-sm text-gray-300">
                    <div>
                      asset=<code>{asset}</code> scope=<code>{scope}</code> channel=<code>{channel}</code> tenant=<code>{tenant}</code>
                    </div>
                    {fromVersion ? (
                      <div>
                        from_version=<code>{fromVersion}</code>
                      </div>
                    ) : null}
                    {toVersion ? (
                      <div>
                        to_version=<code>{toVersion}</code>
                      </div>
                    ) : null}
                    {!toVersion && toVersion2 ? (
                      <div>
                        to_version=<code>{toVersion2}</code>
                      </div>
                    ) : null}
                    {expiresAt ? (
                      <div>
                        expires_at=<code>{String(expiresAt)}</code>
                      </div>
                    ) : null}
                    {summary ? (
                      <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">{String(summary)}</pre>
                    ) : null}
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        icon={<ExternalLink size={14} />}
                        onClick={() => {
                          const url = `/core/skills-rollouts?tenant_id=${encodeURIComponent(tenant)}&scope=${encodeURIComponent(scope)}&channel=${encodeURIComponent(channel)}&asset_type=${encodeURIComponent(asset)}`;
                          window.location.href = url;
                        }}
                      >
                        打开灰度发布页定位
                      </Button>
                      {detail?.request_id ? (
                        <Button
                          variant="secondary"
                          icon={<Play size={14} />}
                          onClick={async () => {
                            try {
                              await approvalsApi.replay(String(detail.request_id), {});
                              toast.success('已重放执行');
                              setDetailOpen(false);
                              fetchPending();
                            } catch (e: any) {
                              toastGateError(e, '重放失败');
                            }
                          }}
                        >
                          重放（执行发布）
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {(() => {
              const meta = detail?.metadata || {};
              const plan = (meta as any)?.system_run_plan || null;
              const opctx = (meta as any)?.operation_context || {};
              const policyReason = String((plan as any)?.args?._policy_reason || opctx?._policy_reason || '');
              const codingProfile = String((plan as any)?.args?._coding_policy_profile || (plan as any)?.args?.coding_policy_profile || '');
              const missingKeys = (plan as any)?.args?._missing_change_contract_keys;
              const repoFiles = (plan as any)?.args?._repo_status_files;
              const repoCount = (plan as any)?.args?._repo_status_count;
              const outOfContract = (plan as any)?.args?._out_of_contract_files;
              const declaredFiles = (plan as any)?.args?._declared_changed_files;
              const declaredUnrelated = (plan as any)?.args?._declared_unrelated_changes;
              if (!plan) return null;
              return (
                <Card>
                  <CardHeader>
                    <div className="text-sm font-semibold text-gray-200">执行计划</div>
                    <div className="text-xs text-gray-500">system_run_plan（审批时用于解释“将要执行什么”）</div>
                  </CardHeader>
                  <CardContent>
                    <div className="text-sm text-gray-300 space-y-2">
                      <div>
                        type=<code>{String((plan as any)?.type || '-')}</code>{' '}
                        {(plan as any)?.tool ? (
                          <>
                            tool=<code>{String((plan as any)?.tool || '-')}</code>
                          </>
                        ) : null}
                        {(plan as any)?.skill ? (
                          <>
                            skill=<code>{String((plan as any)?.skill || '-')}</code>
                          </>
                        ) : null}
                      </div>
                      {String((plan as any)?.tool || '') === 'repo' && (repoCount != null || Array.isArray(repoFiles)) ? (
                        <div className="text-xs text-gray-400">
                          repo_status_count=<code>{String(repoCount ?? '-')}</code>
                          {Array.isArray(repoFiles) && repoFiles.length > 0 ? (
                            <div className="mt-1">
                              <div className="text-xs text-gray-500 mb-1">repo_status_files（Top）</div>
                              <div className="text-xs text-gray-300 break-words">{repoFiles.slice(0, 12).join(' · ')}</div>
                            </div>
                          ) : null}
                          {declaredUnrelated === false && Array.isArray(declaredFiles) && declaredFiles.length > 0 ? (
                            <div className="mt-2">
                              <div className="text-xs text-gray-500 mb-1">declared_changed_files（Top）</div>
                              <div className="text-xs text-gray-300 break-words">{declaredFiles.slice(0, 12).join(' · ')}</div>
                            </div>
                          ) : null}
                          {Array.isArray(outOfContract) && outOfContract.length > 0 ? (
                            <div className="mt-2 text-xs text-yellow-300">
                              超出声明变更范围：<code>{outOfContract.slice(0, 12).join(',')}</code>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {codingProfile ? (
                        <div className="text-xs text-gray-400">
                          coding_policy_profile=<code>{codingProfile}</code>
                        </div>
                      ) : null}
                      {policyReason ? (
                        <div className="text-xs text-yellow-300">
                          policy_reason=<code>{policyReason}</code>
                        </div>
                      ) : null}
                      {Array.isArray(missingKeys) && missingKeys.length > 0 ? (
                        <div className="text-xs text-yellow-300">
                          缺少输出契约字段：<code>{missingKeys.join(',')}</code>（建议先在 Skills/Lint 中应用 fix_add_change_contract）
                        </div>
                      ) : null}
                      <details>
                        <summary className="text-xs text-gray-500 cursor-pointer">查看 args</summary>
                        <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto max-h-[260px]">
                          {JSON.stringify((plan as any)?.args || {}, null, 2)}
                        </pre>
                      </details>
                    </div>
                  </CardContent>
                </Card>
              );
            })()}

            <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(detail || {}, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Approvals;
