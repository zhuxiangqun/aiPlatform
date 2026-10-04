/** Banner must match backend FAIL_CONSTRAINT_BANNER in execution_quality_review.py */
export const FAIL_CONSTRAINT_BANNER = '[质量门禁失败点 — 本轮必须遵守，勿重复上次错误]';

const TASK_SEP = '——以下为原任务，须完整作答——';

/** Reject copyable lone-endpoint shapes — models echo them as the whole product. */
function looksLikeEndpointExample(text: string): boolean {
  const tl = String(text || '')
    .toLowerCase()
    .replace(/\s+/g, '');
  if (tl.includes('"method"') && tl.includes('"path"')) return true;
  if (tl.includes('method=post') && tl.includes('path=/api')) return true;
  if (tl.includes("{'method'") || tl.includes('{"method"')) return true;
  if (tl.includes('/api/tickets') && (tl.includes('request') || tl.includes('response'))) return true;
  return false;
}

/**
 * Compact fail-point overlay — keep short so local LLMs do not stall / echo bait.
 * Must stay aligned with backend ``build_fail_constraint_overlay``.
 */
export function buildFailConstraintOverlay(
  issues: Array<{ code?: string; severity?: string; message?: string; suggestion?: string }> | null | undefined,
): string {
  const lines: string[] = [FAIL_CONSTRAINT_BANNER];
  let n = 0;
  const codesSeen: string[] = [];
  const msgs: string[] = [];
  for (const issue of issues || []) {
    const sev = String(issue.severity || '').toLowerCase();
    if (sev && sev !== 'error' && sev !== 'warning') continue;
    const msg = String(issue.message || '').trim();
    if (!msg) continue;
    const code = String(issue.code || '').trim();
    if (code === 'empty_output' || code === 'runtime_timeout' || code === 'runtime_failed') continue;
    n += 1;
    msgs.push(msg);
    if (code && !codesSeen.includes(code)) codesSeen.push(code);
    const short = msg.length <= 80 ? msg : `${msg.slice(0, 77)}…`;
    lines.push(code ? `- [${code}] ${short}` : `- ${short}`);
    if (n >= 6) break;
  }
  if (n === 0) return '';
  const joined = msgs.join(' ');
  const archCodes = new Set([
    'architecture_sections_thin',
    'public_cloud_photo_storage',
    'invented_third_party_api',
    'architecture_template_echo',
  ]);
  const isArch = codesSeen.some((c) => archCodes.has(c)) || joined.includes('完整架构');
  const loneApiPrev =
    joined.includes('单个 API') || (joined.includes('端点对象') && joined.includes('完整架构'));
  if (loneApiPrev) {
    lines.splice(1, 0, '【严禁复读】根对象须是完整架构 JSON，禁止只交单个 API 端点。');
  }
  // Architect-only keys — never inject onto FE/BE coding agent reruns.
  if (isArch) {
    lines.push(
      '【必含键】title、context/assumptions、components、data_flow、api_contracts(≥3)、security、rollout_and_risks(含 W1–W6)。api_contracts 只是字段之一。',
    );
  }
  if (
    codesSeen.includes('architecture_sections_thin') &&
    (issues || []).some((i) => String(i.message || '').includes('API'))
  ) {
    lines.push('【API】每项 method/path/request对象/response对象；覆盖上报·审批·派修·看板；禁空壳。');
  }
  if (isArch && msgs.some((m) => m.includes('按周') || m.includes('W1') || m.includes('分期'))) {
    lines.push('【分期】rollout_and_risks 写 W1–W6 可交付切片 + 风险，勿只写「一个车间」。');
  }
  if (codesSeen.includes('invented_third_party_api')) {
    lines.push('【钉钉】tech=通知通道（钉钉·待确认）；禁止 SDK / 假装已有审批派修接口。');
  }
  if (codesSeen.includes('undeclared_api_schema_assumption')) {
    lines.push(
      '【契约】types/apiClient 只用输入 api_contracts 已写明的字段；额外字段须在该 FILE 内标 ASSUMPTION/临时假设。',
    );
  }
  if (
    codesSeen.some((c) =>
      [
        'frontend_module_incomplete',
        'frontend_flow_pages_incomplete',
        'missing_auth_todo',
        'undeclared_api_schema_assumption',
        'language_mismatch',
        'dangling_local_import',
      ].includes(c),
    )
  ) {
    lines.push('【交付】按原任务 ## FILE 清单交切片；禁止 Vite/package.json；页面禁止裸 fetch。');
  }
  lines.push('以上优先于模板；禁止公有云/编造接口绕过。');
  // silence unused helper in compact mode (still used by callers that pass suggestion)
  void looksLikeEndpointExample;
  return lines.join('\n');
}

/** Strip a previously injected fail-constraint block so re-reruns do not stack. */
export function stripFailConstraintOverlay(input: string): string {
  const base = String(input || '');
  if (!base.includes(FAIL_CONSTRAINT_BANNER)) return base;
  const sep = base.indexOf(TASK_SEP);
  if (sep >= 0) {
    return base.slice(sep + TASK_SEP.length).trim();
  }
  // Fallback: drop from banner to end of first blank-line-separated block after banner
  const idx = base.indexOf(FAIL_CONSTRAINT_BANNER);
  if (idx < 0) return base;
  const after = base.slice(idx);
  const m = after.match(/\n\n(?![-•【])/);
  if (m && m.index != null) {
    return (base.slice(0, idx) + after.slice(m.index + 2)).trim();
  }
  return base.replace(FAIL_CONSTRAINT_BANNER, '').trim();
}

/**
 * Prepend quality-fail constraints so the user task remains the trailing instruction
 * (models often echo a trailing JSON example as the whole answer).
 */
export function appendFailConstraintOverlay(
  input: string,
  overlay: string | null | undefined,
): string {
  const ov = String(overlay || '').trim();
  if (!ov) return input;
  const stripped = stripFailConstraintOverlay(String(input || ''));
  const trimmed = stripped.trim();
  if (!trimmed) return ov;
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const key =
        typeof parsed.message === 'string'
          ? 'message'
          : typeof parsed.user_requirement === 'string'
            ? 'user_requirement'
            : typeof parsed.query === 'string'
              ? 'query'
              : typeof parsed.text === 'string'
                ? 'text'
                : 'message';
      const prev = typeof parsed[key] === 'string' ? stripFailConstraintOverlay(String(parsed[key])) : '';
      parsed[key] = prev.trim()
        ? `${ov}\n\n${TASK_SEP}\n\n${prev.trim()}`
        : ov;
      return JSON.stringify(parsed, null, 2);
    }
  } catch {
    /* plain text */
  }
  return `${ov}\n\n${TASK_SEP}\n\n${trimmed}`;
}
