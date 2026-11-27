/** Visible-page chrome for 小朱 — generic perception, not per-page reportPageData.

Not a full DOM dump: skips digital-human chrome, huge tables, and code editors.
Goal: answer「画面上有几个/两张一样的卡」without every screen hand-wiring list fields.
*/

const SKIP = '[data-digital-human]';

function skipped(el: Element): boolean {
  return Boolean(el.closest(SKIP));
}

function norm(s: string): string {
  return s.replace(/\s+/g, ' ').trim();
}

function buttonLabels(root: ParentNode, n = 20): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const nodes = root.querySelectorAll('button, [role="button"]');
  for (let i = 0; i < nodes.length && out.length < n; i += 1) {
    const b = nodes[i];
    if (!(b instanceof HTMLElement) || skipped(b)) continue;
    const t = norm(b.innerText || b.getAttribute('aria-label') || '');
    if (!t || t.length > 48 || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

function fieldLines(root: Element, n = 12): string[] {
  const out: string[] = [];
  const nodes = root.querySelectorAll('input, select');
  for (let i = 0; i < nodes.length && out.length < n; i += 1) {
    const el = nodes[i];
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement) || skipped(el)) continue;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (['password', 'hidden', 'file', 'checkbox', 'radio', 'submit', 'button'].includes(type)) continue;
    const name = norm(
      el.getAttribute('aria-label')
        || (el.closest('label')?.innerText || '')
        || (el.previousElementSibling instanceof HTMLElement ? el.previousElementSibling.innerText : '')
        || el.getAttribute('placeholder')
        || el.getAttribute('name')
        || '',
    );
    const value = norm('value' in el ? String(el.value || '') : '');
    if (!value || value.length > 80) continue;
    const label = name.slice(0, 24) || '字段';
    out.push(`${label}=${value.slice(0, 80)}`);
  }
  return out;
}

function headingLines(root: ParentNode, n = 10): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const nodes = root.querySelectorAll('h1, h2, h3, [role="heading"]');
  for (let i = 0; i < nodes.length && out.length < n; i += 1) {
    const el = nodes[i];
    if (!(el instanceof HTMLElement) || skipped(el)) continue;
    const t = norm(el.innerText || '');
    if (!t || t.length > 80 || seen.has(t)) continue;
    // Skip pure nav chrome
    if (el.closest('nav, aside, [role="navigation"]')) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

/** 列表/卡片区可见短文案：共 N 个、已选用、卡标题行等（通用，不绑 FDE）。 */
function listAndCardLines(root: ParentNode, n = 18): string[] {
  const out: string[] = [];
  const seen = new Set<string>();

  const push = (raw: string) => {
    const t = norm(raw);
    if (!t || t.length < 2 || t.length > 72 || seen.has(t)) return;
    // Skip long paragraphs / dense chrome
    if ((t.match(/[。；;]/g) || []).length >= 2) return;
    seen.add(t);
    out.push(t);
  };

  // Explicit count / selection markers anywhere in main
  const allTextNodes = root.querySelectorAll('span, div, p, li, article, section');
  for (let i = 0; i < allTextNodes.length && out.length < n; i += 1) {
    const el = allTextNodes[i];
    if (!(el instanceof HTMLElement) || skipped(el)) continue;
    if (el.closest('nav, aside, [role="navigation"], script, style')) continue;
    // Only leaf-ish nodes (avoid dumping whole grid)
    if (el.children.length > 4) continue;
    const t = norm(el.innerText || '');
    if (!t) continue;
    if (/共\s*\d+|已选用|已选中|默认|新建|Profile|客户/.test(t) && t.length <= 72) {
      push(t);
    }
  }

  // Grid / card children: first short line of each tile
  const tiles = root.querySelectorAll(
    '.grid > *, [class*="grid-cols"] > *, [class*="Card"], [class*="card"]',
  );
  for (let i = 0; i < tiles.length && out.length < n; i += 1) {
    const el = tiles[i];
    if (!(el instanceof HTMLElement) || skipped(el)) continue;
    if (el.closest('nav, aside')) continue;
    const line =
      norm(
        (el.querySelector('h1, h2, h3, h4, .font-medium, .font-semibold') as HTMLElement | null)
          ?.innerText || '',
      ) || norm((el.innerText || '').split('\n')[0] || '');
    if (line) push(line);
  }

  return out.slice(0, n);
}

/**
 * Capture visible chrome for consultant context.
 *
 * Args:
 *   maxLen: hard cap on returned string.
 */
export function captureVisiblePage(maxLen = 1100): string {
  if (typeof document === 'undefined') return '';
  const parts: string[] = [];
  const dialogs = Array.from(
    document.querySelectorAll('[role="dialog"], [aria-modal="true"]'),
  ).filter((el) => !skipped(el));

  for (const d of dialogs) {
    const titleEl = d.querySelector('h1, h2, h3');
    const title = titleEl instanceof HTMLElement ? norm(titleEl.innerText) : '';
    if (title) parts.push(`弹窗: ${title}`);
    const btns = buttonLabels(d, 18);
    if (btns.length) parts.push(`弹窗按钮: ${btns.join('、')}`);
    const fields = fieldLines(d);
    if (fields.length) parts.push(`弹窗字段: ${fields.join('；')}`);
  }

  if (dialogs.length === 0) {
    const main = document.querySelector('main') || document.body;
    const heads = headingLines(main, 8);
    if (heads.length) parts.push(`标题: ${heads.join(' / ')}`);
    const listish = listAndCardLines(main, 16);
    if (listish.length) parts.push(`可见条目: ${listish.join(' | ')}`);
    const btns = buttonLabels(main, 14);
    if (btns.length) parts.push(`按钮: ${btns.join('、')}`);
  }

  let text = parts.join('\n');
  if (text.length > maxLen) text = `${text.slice(0, maxLen)}…`;
  return text;
}
