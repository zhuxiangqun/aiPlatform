import { useEffect, useMemo, useRef, useState } from 'react';
import { approvalsApi, onboardingApi } from '../../services';
import { Badge } from '../ui';

export type DoctorAction = {
  method: string;
  api_url: string;
  body_example?: Record<string, any>;
};

const labelForActionKey = (key: string) => {
  if (key === 'toggle_strong_gate') return '解除强门禁';
  if (key === 'enable_autosmoke') return '开启 autosmoke';
  if (key === 'migrate_secrets') return '迁移明文密钥';
  return `执行：${key}`;
};

type Props = {
  actions?: Record<string, DoctorAction>;
  recommendations?: any[];
  onAfterAction?: () => Promise<void> | void;
};

export const ActionableFixes: React.FC<Props> = ({ actions, recommendations, onAfterAction }) => {
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, { approval_id: string; action: DoctorAction }>>({});
  const pollInFlight = useRef<Record<string, boolean>>({});

  const run = async (k: string, a: DoctorAction, override?: { approval_request_id?: string }) => {
    const apiUrl = String(a?.api_url || '');
    const method = String(a?.method || 'POST').toUpperCase();
    if (method !== 'POST') {
      setMsg((p) => ({ ...(p || {}), [k]: `不支持的 method：${method}` }));
      return;
    }
    setRunning((p) => ({ ...(p || {}), [k]: true }));
    setMsg((p) => ({ ...(p || {}), [k]: '' }));
    try {
      const body = { ...(a?.body_example || {}) };
      if (override?.approval_request_id) body.approval_request_id = override.approval_request_id;

      let res: any = null;
      // allowlist only
      if (apiUrl === '/api/onboarding/strong-gate') res = await onboardingApi.setStrongGate(body);
      else if (apiUrl === '/api/onboarding/autosmoke') res = await onboardingApi.setAutosmoke(body);
      else if (apiUrl === '/api/onboarding/secrets/migrate') res = await onboardingApi.migrateSecrets(body);
      else {
        setMsg((p) => ({ ...(p || {}), [k]: `未在白名单内的 api_url：${apiUrl}` }));
        return;
      }

      if (res?.status === 'approval_required' && res?.approval_request_id) {
        const rid = String(res.approval_request_id);
        setPending((p) => ({ ...(p || {}), [k]: { approval_id: rid, action: a } }));
        setMsg((p) => ({ ...(p || {}), [k]: `等待审批中：${rid}` }));
      } else {
        setPending((p) => {
          const next = { ...(p || {}) };
          delete next[k];
          return next;
        });
        setMsg((p) => ({ ...(p || {}), [k]: `已执行：${JSON.stringify(res)}` }));
        await onAfterAction?.();
      }
    } catch (e: any) {
      setMsg((p) => ({ ...(p || {}), [k]: e?.message || String(e) }));
    } finally {
      setRunning((p) => ({ ...(p || {}), [k]: false }));
    }
  };

  // Poll approvals and auto-retry
  useEffect(() => {
    const keys = Object.keys(pending || {});
    if (keys.length === 0) return;
    const createdAt = Date.now();
    const timer = window.setInterval(async () => {
      for (const k of Object.keys(pending || {})) {
        const item = pending[k];
        if (!item?.approval_id) continue;
        if (pollInFlight.current[k]) continue;
        if (Date.now() - createdAt > 10 * 60 * 1000) {
          setMsg((p) => ({ ...(p || {}), [k]: '轮询超时（已停止）' }));
          continue;
        }
        pollInFlight.current[k] = true;
        try {
          const detail = await approvalsApi.get(String(item.approval_id));
          const st = String(detail?.status || 'pending');
          if (st === 'approved' || st === 'auto_approved') {
            setMsg((p) => ({ ...(p || {}), [k]: '已批准，正在自动重试…' }));
            await run(k, item.action, { approval_request_id: item.approval_id });
            setPending((p) => {
              const next = { ...(p || {}) };
              delete next[k];
              return next;
            });
          } else if (st === 'rejected' || st === 'cancelled' || st === 'expired') {
            setMsg((p) => ({ ...(p || {}), [k]: `审批未通过：${st}` }));
            setPending((p) => {
              const next = { ...(p || {}) };
              delete next[k];
              return next;
            });
          } else {
            setMsg((p) => ({ ...(p || {}), [k]: `等待审批中：${st}` }));
          }
        } catch (e) {
          console.error(e);
        } finally {
          pollInFlight.current[k] = false;
        }
      }
    }, 2500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  const actionEntries = useMemo(() => Object.entries(actions || {}), [actions]);

  return (
    <div className="space-y-3">
      <div className="text-sm font-semibold text-gray-200">Quick Fix Actions（白名单）</div>

      {actionEntries.length === 0 ? (
        <div className="text-sm text-gray-500">暂无可执行动作</div>
      ) : (
        <div className="space-y-2">
          {actionEntries.map(([k, a]) => (
            <div key={`global:${k}`} className="border border-dark-border rounded-lg p-3 bg-dark-hover">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-gray-200">
                  <code className="text-xs">{k}</code>
                  <div className="text-xs text-gray-500 mt-1">{a.api_url}</div>
                </div>
                <button
                  onClick={() => run(`global:${k}`, a)}
                  disabled={!!running[`global:${k}`]}
                  className="px-3 py-2 rounded-lg bg-primary text-white hover:opacity-90 disabled:opacity-60 transition-colors text-sm"
                >
                  {running[`global:${k}`] ? '执行中…' : labelForActionKey(k)}
                </button>
              </div>
              {msg[`global:${k}`] && <div className="mt-2 text-xs text-gray-400">{msg[`global:${k}`]}</div>}
              <pre className="text-xs text-gray-300 mt-2">{JSON.stringify(a.body_example || {}, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}

      <div className="text-sm font-semibold text-gray-200 mt-4">Recommendations</div>
      {(recommendations || []).length === 0 ? (
        <div className="text-sm text-gray-500">暂无建议</div>
      ) : (
        <div className="space-y-2">
          {(recommendations || []).map((r: any, idx: number) => {
            const code = String(r?.code || idx);
            const severity = String(r?.severity || 'info');
            const recActions = (r?.actions || {}) as Record<string, DoctorAction>;
            return (
              <div key={`${code}-${idx}`} className="border border-dark-border rounded-lg p-3 bg-dark-hover">
                <div className="text-sm text-gray-200">
                  <Badge variant={severity === 'error' ? 'error' : severity === 'warn' ? 'warning' : 'info'}>{severity}</Badge>{' '}
                  <code className="text-xs">{code}</code>
                </div>
                <div className="text-sm text-gray-500 mt-1">{String(r?.message || '')}</div>
                {Object.keys(recActions || {}).length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {Object.entries(recActions).map(([k, a]) => (
                      <button
                        key={`rec:${idx}:${k}`}
                        onClick={() => run(`rec:${idx}:${k}`, a)}
                        disabled={!!running[`rec:${idx}:${k}`]}
                        className="px-3 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 disabled:opacity-60 transition-colors text-xs"
                      >
                        {running[`rec:${idx}:${k}`] ? '执行中…' : labelForActionKey(k)}
                      </button>
                    ))}
                  </div>
                )}
                {Object.keys(recActions || {}).map((k) => {
                  const key = `rec:${idx}:${k}`;
                  return msg[key] ? (
                    <div key={`${key}:msg`} className="mt-2 text-xs text-gray-400">
                      {msg[key]}
                    </div>
                  ) : null;
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

