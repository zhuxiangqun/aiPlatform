import { toast } from '../components/ui';

export type GateErrorEnvelope = {
  code?: string;
  message?: string;
  change_id?: string;
  approval_request_id?: string;
  links?: Record<string, any>;
  next_actions?: Array<Record<string, any>>;
  detail?: any;
};

export const extractGateEnvelope = (e: any): GateErrorEnvelope | null => {
  const d = e?.detail ?? e?.payload?.detail;
  if (!d || typeof d !== 'object') return null;
  if (!('code' in d) && !('change_id' in d) && !('approval_request_id' in d)) return null;
  return d as GateErrorEnvelope;
};

export const toastGateError = (e: any, fallbackTitle: string) => {
  const env = extractGateEnvelope(e);
  if (!env) {
    toast.error(fallbackTitle, e?.message || String(e));
    return;
  }
  const code = String(env.code || 'error');
  const msg = String(env.message || e?.message || '请求被门禁拦截');
  const parts: string[] = [code];
  if (env.change_id) parts.push(`change_id=${env.change_id}`);
  if (env.approval_request_id) parts.push(`approval=${env.approval_request_id}`);
  toast.error(fallbackTitle, `${msg}（${parts.join(' / ')}）`);
};

