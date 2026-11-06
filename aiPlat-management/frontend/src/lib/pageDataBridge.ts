/**
 * PageDataBridge — 页面 → 数字人的实时数据桥（P2-4）。
 *
 * 数字人默认只知道"当前页面叫什么"（route/label）。要让它在各画面回答
 * "当前页面上是什么状态/数值"（如诊断得分、告警数、某表单值），页面需要
 * 主动上报结构化数据。本模块提供零侵入的全局上报通道：
 *
 *   - reportPageData(route, data)   页面在数据变化时调用（useEffect 即可）
 *   - clearPageData(route)          页面卸载时清理（可选，防陈旧数据）
 *   - getPageData(route)            数字人组件读取，随 context 发送给后端
 *
 * 数据形态：普通 JSON（扁平 key-value 或嵌套对象），会被摘要后注入 LLM
 * prompt（限长），所以请上报"关键状态/数值/当前选中项"，不要塞完整列表。
 *
 * 用法示例（某页面组件内）：
 *   useEffect(() => {
 *     reportPageData('/diagnostics', {
 *       health: 'PASS',
 *       score: 92,
 *       activeAlerts: 3,
 *       selectedTab: '架构合规',
 *     });
 *     return () => clearPageData('/diagnostics');
 *   }, [health, score, activeAlerts]);
 */
import { captureVisiblePage } from './captureVisiblePage';

type PageData = Record<string, unknown>;

declare global {
  interface Window {
    __AIPLAT_PAGE_DATA__?: Record<string, PageData>;
  }
}

const _listeners = new Set<() => void>();

function getStore(): Record<string, PageData> {
  if (!window.__AIPLAT_PAGE_DATA__) {
    window.__AIPLAT_PAGE_DATA__ = {};
  }
  return window.__AIPLAT_PAGE_DATA__;
}

function _notify(): void {
  _listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      /* ignore */
    }
  });
}

const _LIVE_AUDIT_ID_KEYS = new Set([
  'skillId',
  'skillName',
  'agentId',
  'agentName',
  'toolId',
  'toolName',
  'mcpId',
  'mcpName',
  'auditSummary',
]);

function _isLiveAuditKey(key: string): boolean {
  return key.startsWith('issue') || _LIVE_AUDIT_ID_KEYS.has(key);
}

/** 上报页面数据；保留同 route 上未在本次 payload 出现的审核实况键（issueN / skillId 等）。 */
export function reportPageData(route: string, data: PageData): void {
  if (!route) return;
  const prev = getStore()[route] || {};
  const preserved: PageData = {};
  for (const [k, v] of Object.entries(prev)) {
    if (_isLiveAuditKey(k) && !(k in data)) preserved[k] = v;
  }
  getStore()[route] = { ...preserved, ...data };
  _notify();
}

/** 合并补丁到当前 route（审核弹窗用，不冲掉列表 glossary）。 */
export function patchPageData(route: string, patch: PageData): void {
  if (!route) return;
  const prev = getStore()[route] || {};
  getStore()[route] = { ...prev, ...patch };
  _notify();
}

/** 清理某个 route 的页面数据（页面卸载时调用，避免陈旧数据被发送）。 */
export function clearPageData(route: string): void {
  if (!route) return;
  const store = getStore();
  delete store[route];
  _notify();
}

/** 去掉审核实况字段，保留 guideGlossary 等列表页上报。 */
export function clearAssetAuditPageFields(route: string): void {
  if (!route) return;
  const prev = getStore()[route];
  if (!prev) return;
  const next: PageData = {};
  for (const [k, v] of Object.entries(prev)) {
    if (!_isLiveAuditKey(k)) next[k] = v;
  }
  getStore()[route] = next;
  _notify();
}

export type AssetAuditPageKind = 'skill' | 'agent' | 'tool' | 'mcp';

/** 把 AI 审核结果写成 issue0… + *Id，供 use_page_only_brief / 小朱解读。 */
export function reportAssetAuditToPage(input: {
  route: string;
  kind: AssetAuditPageKind;
  id: string;
  name?: string;
  result: {
    issues?: AuditIssueLike[];
    summary?: {
      errors?: number;
      warnings?: number;
      info?: number;
      total?: number;
      health?: string;
    };
  } | null;
}): void {
  const { route, kind, id, name, result } = input;
  if (!route || !id) return;

  clearAssetAuditPageFields(route);

  const cleaned: PageData = {};
  if (kind === 'skill') {
    cleaned.skillId = id;
    if (name) cleaned.skillName = name;
  } else if (kind === 'agent') {
    cleaned.agentId = id;
    if (name) cleaned.agentName = name;
  } else if (kind === 'tool') {
    cleaned.toolId = id;
    if (name) cleaned.toolName = name;
  } else {
    cleaned.mcpId = id;
    if (name) cleaned.mcpName = name;
  }

  if (result) {
    const s = result.summary;
    if (s) {
      cleaned.auditSummary = `errors=${s.errors ?? 0},warnings=${s.warnings ?? 0},info=${s.info ?? 0},total=${s.total ?? 0},health=${s.health ?? ''}`;
    }
    (result.issues || []).slice(0, 8).forEach((iss, i) => {
      cleaned[`issue${i}`] = formatAuditIssueForPage(iss);
    });
  }

  patchPageData(route, cleaned);
}

/** Subscribe to page-data changes (digital human re-sends context). */
export function subscribePageData(listener: () => void): () => void {
  _listeners.add(listener);
  return () => {
    _listeners.delete(listener);
  };
}

/** 读取某个 route 的页面数据（FloatingDigitalHuman 发送 context 时调用）。 */
export function getPageData(route: string): PageData | undefined {
  return route ? getStore()[route] : undefined;
}

type AuditIssueLike = {
  severity?: string;
  category?: string;
  message?: string;
  suggestion?: string;
  create_brief?: { must_have?: string };
};

function clipFact(text: string, max: number): string {
  const t = text.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max);
  const sp = Math.max(cut.lastIndexOf('。'), cut.lastIndexOf('；'), cut.lastIndexOf(' '));
  return `${sp > max * 0.55 ? cut.slice(0, sp) : cut}…`;
}

/** Prefer UI suggestion over truncated English engine message. */
export function formatAuditIssueForPage(issue: AuditIssueLike): string {
  const head = `${issue.severity || 'info'}/${issue.category || 'issue'}`;
  const suggestion = (issue.suggestion || '').trim();
  const must = (issue.create_brief?.must_have || '').trim();
  if (suggestion) {
    return clipFact(`${head}: ${suggestion}${must ? `；应具备:${must}` : ''}`, 320);
  }
  return clipFact(`${head}: ${issue.message || ''}`, 280);
}

/** 页面数据转紧凑文本摘要（供后端注入 prompt，限长）。 */
export function pageDataToText(data: PageData | undefined, maxLen = 1400): string {
  if (!data) return '';
  const lines: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    if (v === undefined || v === null || v === '') continue;
    const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
    // issue*/guide* allow longer facts (e.g. Eval tab catalog for 小朱).
    const cap = k.startsWith('issue') || k.startsWith('guide') ? 900 : 120;
    if (val.length > cap) {
      lines.push(`${k}: ${val.slice(0, cap)}…`);
    } else {
      lines.push(`${k}: ${val}`);
    }
  }
  if (lines.length === 0) return '';
  let text = lines.join('；');
  if (text.length > maxLen) {
    text = text.slice(0, maxLen) + '…';
  }
  return text;
}

export function mergeConsultantPageText(
  reported: string,
  snapshot: string,
  maxLen = 2000,
): string {
  const text = [reported, snapshot].filter((s) => Boolean(s && s.trim())).join('\n');
  if (text.length > maxLen) return `${text.slice(0, maxLen)}…`;
  return text;
}

/** Structured reportPageData + visible chrome (dialog/title/buttons). */
export function consultantPagePayload(route: string, maxLen = 2000): string {
  const data = getPageData(route);
  const hasEditorFacts = Boolean(
    data && (data.issue0 || data.skillId || data.toolId || data.mcpId || data.agentId),
  );
  const hasGuidePack = Boolean(
    data && (data.guideCatalog || data.guideGlossary || data.issueGuide),
  );
  const reportedBudget = hasEditorFacts || hasGuidePack ? 1800 : 800;
  return mergeConsultantPageText(
    pageDataToText(data, reportedBudget),
    hasEditorFacts ? '' : captureVisiblePage(hasGuidePack ? 500 : 1100),
    Math.max(maxLen, hasGuidePack ? 2400 : maxLen),
  );
}
