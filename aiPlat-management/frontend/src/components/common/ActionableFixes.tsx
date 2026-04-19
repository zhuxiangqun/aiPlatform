import { useEffect, useMemo, useRef, useState } from 'react';
import { approvalsApi, onboardingApi } from '../../services';
import { Badge } from '../ui';

export type DoctorAction = {
  action_type?: string;
  method: string;
  api_url: string;
  input_schema?: any;
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
  const [formValues, setFormValues] = useState<Record<string, any>>({});

  const _schemaProps = (a: DoctorAction) => (a?.input_schema && typeof a.input_schema === 'object' ? a.input_schema.properties || {} : {});
  const _schemaReq = (a: DoctorAction) =>
    Array.isArray(a?.input_schema?.required) ? (a.input_schema.required as string[]) : [];

  const isSensitive = (spec: any) => !!(spec && spec['x-ui'] && spec['x-ui'].sensitive);
  const placeholderOf = (spec: any) => (spec && spec['x-ui'] ? spec['x-ui'].placeholder : undefined);
  const multilineOf = (spec: any) => !!(spec && spec['x-ui'] && spec['x-ui'].multiline);

  const redactForDisplay = (vals: Record<string, any>, a: DoctorAction) => {
    const props = _schemaProps(a);
    const out: Record<string, any> = { ...(vals || {}) };
    for (const [k, spec] of Object.entries<any>(props)) {
      if (isSensitive(spec) && out[k]) out[k] = '***';
    }
    return out;
  };

  const coerceAndValidate = (vals: Record<string, any>, a: DoctorAction): { ok: boolean; body?: any; err?: string } => {
    const schema = a?.input_schema;
    if (!schema || typeof schema !== 'object') return { ok: true, body: vals };
    const props = _schemaProps(a);
    const required = _schemaReq(a);
    const out: Record<string, any> = {};

    for (const [k, spec] of Object.entries<any>(props)) {
      let v = vals?.[k];
      const t = String(spec?.type || 'string');

      // Normalize empty string
      if (typeof v === 'string' && v.trim() === '') v = '';

      if (t === 'boolean') {
        out[k] = !!v;
      } else if (t === 'integer') {
        if (v === '' || v == null) {
          // omit if not required
        } else {
          const n = typeof v === 'number' ? v : parseInt(String(v), 10);
          if (Number.isNaN(n)) return { ok: false, err: `${k} 必须是整数` };
          out[k] = n;
        }
      } else if (t === 'number') {
        if (v === '' || v == null) {
          // omit if not required
        } else {
          const n = typeof v === 'number' ? v : parseFloat(String(v));
          if (Number.isNaN(n)) return { ok: false, err: `${k} 必须是数字` };
          out[k] = n;
        }
      } else {
        // string (default)
        if (v === '' || v == null) {
          // omit if not required
        } else {
          out[k] = String(v);
        }
      }
    }

    for (const reqKey of required) {
      if (!(reqKey in out)) return { ok: false, err: `缺少必填字段：${reqKey}` };
    }
    return { ok: true, body: out };
  };

  const initValues = (a: DoctorAction) => {
    const schema = a?.input_schema;
    const props = schema?.properties || {};
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries<any>(props)) {
      if (v && Object.prototype.hasOwnProperty.call(v, 'default')) out[k] = (v as any).default;
    }
    // fallback to example
    return { ...(a?.body_example || {}), ...out };
  };

  const ensureFormKey = (key: string, a: DoctorAction) => {
    setFormValues((prev) => {
      if (prev && Object.prototype.hasOwnProperty.call(prev, key)) return prev;
      return { ...(prev || {}), [key]: initValues(a) };
    });
  };

  const run = async (k: string, a: DoctorAction, override?: { approval_request_id?: string }) => {
    const apiUrl = String(a?.api_url || '');
    const actionType = String(a?.action_type || '');
    const method = String(a?.method || 'POST').toUpperCase();
    if (method !== 'POST') {
      setMsg((p) => ({ ...(p || {}), [k]: `不支持的 method：${method}` }));
      return;
    }
    setRunning((p) => ({ ...(p || {}), [k]: true }));
    setMsg((p) => ({ ...(p || {}), [k]: '' }));
    try {
      const raw = { ...(formValues?.[k] || a?.body_example || {}) };
      const cv = coerceAndValidate(raw, a);
      if (!cv.ok) {
        setMsg((p) => ({ ...(p || {}), [k]: cv.err || '参数不合法' }));
        return;
      }
      const body = { ...(cv.body || {}) };
      if (override?.approval_request_id) body.approval_request_id = override.approval_request_id;

      let res: any = null;
      // allowlist only (prefer action_type, fallback to api_url)
      if (actionType === 'onboarding.strong_gate' || apiUrl === '/api/onboarding/strong-gate') {
        res = await onboardingApi.setStrongGate(body);
      } else if (actionType === 'onboarding.autosmoke' || apiUrl === '/api/onboarding/autosmoke') {
        res = await onboardingApi.setAutosmoke(body);
      } else if (actionType === 'onboarding.secrets_migrate' || apiUrl === '/api/onboarding/secrets/migrate') {
        res = await onboardingApi.migrateSecrets(body);
      } else {
        setMsg((p) => ({ ...(p || {}), [k]: `未在白名单内的 action：${actionType || apiUrl}` }));
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
  const recActionEntries = useMemo(() => {
    const out: Array<{ key: string; actionKey: string; action: DoctorAction; recIdx: number; code: string; severity: string; message: string }> = [];
    (recommendations || []).forEach((r: any, idx: number) => {
      const code = String(r?.code || idx);
      const severity = String(r?.severity || 'info');
      const message = String(r?.message || '');
      const recActions = (r?.actions || {}) as Record<string, DoctorAction>;
      Object.entries(recActions || {}).forEach(([k, a]) => {
        out.push({ key: `rec:${idx}:${k}`, actionKey: k, action: a, recIdx: idx, code, severity, message });
      });
    });
    return out;
  }, [recommendations]);

  useEffect(() => {
    // Initialize forms for actions we render.
    for (const [k, a] of actionEntries) ensureFormKey(`global:${k}`, a);
    for (const ra of recActionEntries) ensureFormKey(ra.key, ra.action);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionEntries.length, recActionEntries.length]);

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
              {a?.input_schema?.properties ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                  {Object.entries<any>(a.input_schema.properties || {}).map(([pk, spec]) => {
                    const fullKey = `global:${k}`;
                    const v = formValues?.[fullKey]?.[pk];
                    const t = String(spec?.type || 'string');
                    if (t === 'boolean') {
                      return (
                        <label key={pk} className="flex items-center gap-2 text-xs text-gray-300">
                          <input
                            type="checkbox"
                            checked={!!v}
                            onChange={(e) =>
                              setFormValues((p) => ({ ...(p || {}), [fullKey]: { ...(p?.[fullKey] || {}), [pk]: e.target.checked } }))
                            }
                          />
                          <span>
                            {pk}
                            {spec?.description ? <span className="text-gray-500">（{String(spec.description)}）</span> : null}
                          </span>
                        </label>
                      );
                    }
                    const ph = placeholderOf(spec);
                    const sensitive = isSensitive(spec);
                    const multiline = multilineOf(spec);
                    return (
                      <div key={pk}>
                        <div className="text-xs text-gray-500 mb-1">{pk}</div>
                        {spec?.description ? <div className="text-xs text-gray-600 mb-1">{String(spec.description)}</div> : null}
                        {multiline ? (
                          <textarea
                            value={v ?? ''}
                            placeholder={ph}
                            onChange={(e) =>
                              setFormValues((p) => ({ ...(p || {}), [fullKey]: { ...(p?.[fullKey] || {}), [pk]: e.target.value } }))
                            }
                            className="w-full px-3 py-2 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-xs"
                            rows={3}
                          />
                        ) : (
                          <input
                            type={t === 'integer' || t === 'number' ? 'number' : sensitive ? 'password' : 'text'}
                            value={v ?? ''}
                            placeholder={ph}
                            onChange={(e) =>
                              setFormValues((p) => ({ ...(p || {}), [fullKey]: { ...(p?.[fullKey] || {}), [pk]: e.target.value } }))
                            }
                            className="w-full px-3 py-2 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-xs"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <pre className="text-xs text-gray-300 mt-2">{JSON.stringify(a.body_example || {}, null, 2)}</pre>
              )}
              <pre className="text-xs text-gray-300 mt-2">
                {JSON.stringify(redactForDisplay(formValues?.[`global:${k}`] || a.body_example || {}, a), null, 2)}
              </pre>
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
                {Object.entries(recActions || {}).map(([k, a]) => {
                  const fullKey = `rec:${idx}:${k}`;
                  if (!a?.input_schema?.properties) return null;
                  return (
                    <div key={`${fullKey}:form`} className="mt-2">
                      <div className="text-xs text-gray-500 mb-1">参数</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {Object.entries<any>(a.input_schema.properties || {}).map(([pk, spec]) => {
                          const v = formValues?.[fullKey]?.[pk];
                          const t = String(spec?.type || 'string');
                          if (t === 'boolean') {
                            return (
                              <label key={pk} className="flex items-center gap-2 text-xs text-gray-300">
                                <input
                                  type="checkbox"
                                  checked={!!v}
                                  onChange={(e) =>
                                    setFormValues((p) => ({ ...(p || {}), [fullKey]: { ...(p?.[fullKey] || {}), [pk]: e.target.checked } }))
                                  }
                                />
                                <span>
                                  {pk}
                                  {spec?.description ? <span className="text-gray-500">（{String(spec.description)}）</span> : null}
                                </span>
                              </label>
                            );
                          }
                          const ph = placeholderOf(spec);
                          const sensitive = isSensitive(spec);
                          const multiline = multilineOf(spec);
                          return (
                            <div key={pk}>
                              <div className="text-xs text-gray-500 mb-1">{pk}</div>
                              {spec?.description ? <div className="text-xs text-gray-600 mb-1">{String(spec.description)}</div> : null}
                              {multiline ? (
                                <textarea
                                  value={v ?? ''}
                                  placeholder={ph}
                                  onChange={(e) =>
                                    setFormValues((p) => ({ ...(p || {}), [fullKey]: { ...(p?.[fullKey] || {}), [pk]: e.target.value } }))
                                  }
                                  className="w-full px-3 py-2 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-xs"
                                  rows={3}
                                />
                              ) : (
                                <input
                                  type={t === 'integer' || t === 'number' ? 'number' : sensitive ? 'password' : 'text'}
                                  value={v ?? ''}
                                  placeholder={ph}
                                  onChange={(e) =>
                                    setFormValues((p) => ({ ...(p || {}), [fullKey]: { ...(p?.[fullKey] || {}), [pk]: e.target.value } }))
                                  }
                                  className="w-full px-3 py-2 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-xs"
                                />
                              )}
                            </div>
                          );
                        })}
                      </div>
                      <pre className="text-xs text-gray-300 mt-2">{JSON.stringify(redactForDisplay(formValues?.[fullKey] || a.body_example || {}, a), null, 2)}</pre>
                    </div>
                  );
                })}
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
