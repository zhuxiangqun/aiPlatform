/** Visible-page chrome for 小朱. Not a full DOM dump (skips big tables and source editors). */

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
    const h1 = main.querySelector('h1');
    const heading = h1 instanceof HTMLElement ? norm(h1.innerText) : '';
    if (heading) parts.push(`标题: ${heading}`);
    const btns = buttonLabels(main, 16);
    if (btns.length) parts.push(`按钮: ${btns.join('、')}`);
  }

  let text = parts.join('\n');
  if (text.length > maxLen) text = `${text.slice(0, maxLen)}…`;
  return text;
}
