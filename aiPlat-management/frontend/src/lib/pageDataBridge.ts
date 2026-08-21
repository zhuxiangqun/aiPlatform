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
type PageData = Record<string, unknown>;

declare global {
  interface Window {
    __AIPLAT_PAGE_DATA__?: Record<string, PageData>;
  }
}

function getStore(): Record<string, PageData> {
  if (!window.__AIPLAT_PAGE_DATA__) {
    window.__AIPLAT_PAGE_DATA__ = {};
  }
  return window.__AIPLAT_PAGE_DATA__;
}

/** 上报当前页面数据（覆盖同 route 的旧值）。 */
export function reportPageData(route: string, data: PageData): void {
  if (!route) return;
  getStore()[route] = { ...data };
}

/** 清理某个 route 的页面数据（页面卸载时调用，避免陈旧数据被发送）。 */
export function clearPageData(route: string): void {
  if (!route) return;
  const store = getStore();
  delete store[route];
}

/** 读取某个 route 的页面数据（FloatingDigitalHuman 发送 context 时调用）。 */
export function getPageData(route: string): PageData | undefined {
  return route ? getStore()[route] : undefined;
}

/** 页面数据转紧凑文本摘要（供后端注入 prompt，限长）。 */
export function pageDataToText(data: PageData | undefined, maxLen = 600): string {
  if (!data) return '';
  const lines: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    if (v === undefined || v === null || v === '') continue;
    const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
    if (val.length > 120) {
      lines.push(`${k}: ${val.slice(0, 120)}…`);
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
