import logging
"""
Browser Tool — Full Playwright-based implementation.

Provides browser automation capabilities for agents:
  goto, click, type, screenshot, evaluate, wait, get_text, scroll, search, extract

Uses Playwright CDP to control Chromium. Falls back gracefully if Playwright is not installed.
"""
import asyncio
import json
import os
import tempfile
import time
from base64 import b64encode
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...harness.interfaces import ToolConfig, ToolResult
from .base import BaseTool

_BROWSER = None


def _get_browser():
    global _BROWSER
    if _BROWSER is None:
        try:
            from playwright.async_api import async_playwright
            _playwright = None
            _BROWSER = _BrowserSession()
        except ImportError:
            return None
    return _BROWSER


class _BrowserSession:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._context = None

    async def _lazy_start(self, record_video_dir: str = "", headless: bool = None):
        if self._page is not None and not self._page.is_closed():
            return
        try:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            if headless is None:
                headless = os.environ.get("BROWSER_USE_HEADLESS", "true").lower() == "true"

            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            ]
            executable_path = None
            for path in chrome_paths:
                if Path(path).exists():
                    executable_path = path

            self._browser = await self._pw.chromium.launch(
                headless=headless,
                executable_path=executable_path,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--ignore-certificate-errors"]
            )
            ctx_kwargs: Dict[str, Any] = {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "ignore_https_errors": True,
            }
            if record_video_dir:
                os.makedirs(record_video_dir, exist_ok=True)
                ctx_kwargs["record_video_dir"] = record_video_dir
                ctx_kwargs["record_video_size"] = {"width": 1280, "height": 720}
            self._context = await self._browser.new_context(**ctx_kwargs)
            self._video_path = record_video_dir if record_video_dir else ""
            self._page = await self._context.new_page()
        except Exception as e:
            raise RuntimeError(f"Failed to start browser: {e}")

    async def stop(self) -> str:
        """Close browser and return video path if recording was enabled."""
        video_path = ""
        if self._context:
            try:
                await self._context.close()
                if self._video_path:
                    import glob
                    files = sorted(glob.glob(os.path.join(self._video_path, "*.webm")))
                    if files:
                        video_path = files[-1]
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            self._context = None
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        return video_path

    async def detect_form_errors(self) -> List[Dict[str, str]]:
        """Scan page for validation error messages using reliable DOM markers only."""
        await self._lazy_start()
        js = """() => {
            const errors = [];
            const seen = new Set();
            const add = (txt, tag, tp) => {
                txt = (txt || '').trim();
                if (!txt || txt.length > 200 || seen.has(txt)) return;
                seen.add(txt);
                errors.push({text: txt, tag: tag, type: tp});
            };

            // 1. Browser native :invalid inputs + validationMessage
            document.querySelectorAll('input:invalid, select:invalid, textarea:invalid').forEach(el => {
                const msg = el.validationMessage || '';
                if (msg) {
                    const lbl = el.labels?.[0]?.textContent || '';
                    add((lbl + ' ' + msg).trim(), el.tagName, 'validation');
                }
            });

            // 2. aria-invalid elements (direct text only, not descendants)
            document.querySelectorAll('[aria-invalid="true"]').forEach(el => {
                let own = '';
                for (const n of el.childNodes) {
                    if (n.nodeType === 3) own += n.textContent;
                }
                add(own.trim(), el.tagName, 'aria_invalid');
            });

            // 3. Elements with error-specific class markers (short text only)
            const errSel = [
                '.field-error', '.form-error', '.input-error', '.validation-error',
                '.ant-form-item-explain-error', '.mantine-InputWrapper-error',
            ];
            errSel.forEach(s => {
                try {
                    document.querySelectorAll(s).forEach(el => {
                        const txt = (el.textContent || '').trim();
                        if (txt.length > 2 && txt.length < 200) add(txt, el.tagName, 'error_class');
                    });
                } catch {}
            });

            return errors;
        }"""
        try:
            result = await self._page.evaluate(js)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    async def goto(self, url: str) -> Dict[str, Any]:
        await self._lazy_start()
        resp = await self._page.goto(url, wait_until="networkidle", timeout=30000)
        title = await self._page.title()
        return {"url": self._page.url, "title": title, "status": resp.status if resp else None}

    async def click(self, selector: str) -> Dict[str, Any]:
        await self._lazy_start()
        await self._page.click(selector, timeout=10000)
        title = await self._page.title()
        return {"clicked": selector, "page_title": title}

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        await self._lazy_start()
        await self._page.fill(selector, text, timeout=10000)
        return {"typed": text, "into": selector}

    async def screenshot(self) -> str:
        await self._lazy_start()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            await self._page.screenshot(path=tmp.name, full_page=True)
            return tmp.name

    async def evaluate(self, script: str) -> Any:
        await self._lazy_start()
        return await self._page.evaluate(script)

    async def get_text(self, selector: str = "body") -> str:
        await self._lazy_start()
        if selector:
            el = await self._page.query_selector(selector)
            if el:
                return await el.text_content() or ""
        return await self._page.content()

    async def scroll(self, amount: int = 500) -> Dict[str, Any]:
        await self._lazy_start()
        await self._page.evaluate(f"window.scrollBy(0, {amount})")
        return {"scrolled": amount}

    async def wait(self, ms: int = 1000) -> Dict[str, Any]:
        await self._lazy_start()
        await asyncio.sleep(ms / 1000)
        return {"waited_ms": ms}

    async def search(self, query: str, engine: str = "google") -> Dict[str, Any]:
        engines = {"google": "https://www.google.com/search?q=", "bing": "https://www.bing.com/search?q=", "ddg": "https://duckduckgo.com/?q="}
        url = engines.get(engine, engines["google"]) + query.replace(" ", "+")
        return await self.goto(url)

    async def extract(self, instruction: str) -> Dict[str, Any]:
        await self._lazy_start()
        text = await self._page.content()
        return {"html": text[:50000], "instruction": instruction, "url": self._page.url}

    # ── Shared element gathering JS with RPA-style role detection ──

    _GATHER_JS = (
        "(max, action) => {"
        "  const selectors = ["
        "    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',"
        "    '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',"
        "    '[onclick]', '[contenteditable=true]', 'summary', 'details',"
        "  ];"
        "  const elements = [];"
        "  const seen = new Set();"
        "  for (const sel of selectors) {"
        "    document.querySelectorAll(sel).forEach(el => {"
        "      if (elements.length >= max) return;"
        "      const r = el.getBoundingClientRect();"
        "      if (r.width === 0 || r.height === 0) return;"
        "      if (seen.has(el)) return;"
        "      seen.add(el);"
        "      "
        "      const tag = el.tagName.toLowerCase();"
        "      const tp = (el.type || '').toLowerCase();"
        "      const name = el.name || '';"
        "      const id = el.id || '';"
        "      const placeholder = el.placeholder || '';"
        "      const aria = (el.getAttribute('aria-label') || '').toLowerCase();"
        "      const txt = (el.textContent || '').trim().slice(0, 60).toLowerCase();"
        "      const value = (el.value || '').toLowerCase();"
        "      const className = (el.className || '').toLowerCase();"
        "      "
        "      let role = '';"
        "      if (tag === 'a') role = 'link';"
        "      else if (tag === 'input' && (tp === 'submit' || tp === 'button')) {"
        "        role = 'submit_button';"
        "      } else if (tag === 'input' || tag === 'textarea' || el.contentEditable === 'true') {"
        "        const allText = (placeholder + ' ' + name + ' ' + id + ' ' + aria + ' ' + txt + ' ' + className).toLowerCase();"
        "        if (/^(q|wd|query|keyword|search|w|k|qs)$/.test(name)) role = 'search_input';"
        "        else if (allText.includes('搜索') || allText.includes('请输入') || allText.includes('search') || allText.includes('keyword') || allText.includes('検索')) {"
        "          if (!allText.includes('submit') && !allText.includes('button') && name !== 'su') role = 'search_input';"
        "          else role = 'text_input';"
        "        } else {"
        "          role = 'text_input';"
        "        }"
        "      } else if (tag === 'button' || tag === 'select' || el.hasAttribute('role')) {"
        "        role = el.hasAttribute('role') ? el.getAttribute('role') : tag;"
        "      } else {"
        "        role = tag;"
        "      }"
        "      "
        "      let label = '';"
        "      if (tag === 'a') label = txt || el.href;"
        "      else if (tag === 'input') label = placeholder || name || value || tp;"
        "      else if (tag === 'button') label = txt || name || tp;"
        "      else if (tag === 'select') label = name || id || 'dropdown';"
        "      else if (tag === 'textarea') label = placeholder || name || 'textarea';"
        "      else label = txt;"
        "      "
        "      elements.push({"
        "        index: elements.length + 1,"
        "        tag, role,"
        "        visible_text: (label || '').slice(0, 40),"
        "        type: tp, name: (name || '').slice(0, 30), id: (id || '').slice(0, 30),"
        "        placeholder: (placeholder || '').slice(0, 30),"
        "      });"
        "    });"
        "  }"
        "  "
        "  if (action === 'list') {"
        "    return elements;"
        "  }"
        "  "
        "  return elements;"
        "}"
    )

    async def list_elements(self, max_items: int = 50) -> Dict[str, Any]:
        """Discover all interactive elements with index and role tags (RPA-style)."""
        await self._lazy_start()
        js = "(" + self._GATHER_JS + ")({}, 'list')".format(max_items)
        elements = await self._page.evaluate(js)
        return {"elements": elements, "total": len(elements), "url": self._page.url}

    async def click_index(self, index: int) -> Dict[str, Any]:
        """Click element by its index (from list_elements). Uses identical element ordering."""
        await self._lazy_start()
        js = (
            "(idx) => {"
            "  const selectors = ["
            "    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',"
            "    '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',"
            "    '[onclick]', '[contenteditable=true]', 'summary', 'details'"
            "  ];"
            "  const seen = new Set();"
            "  const elements = [];"
            "  for (const sel of selectors) {"
            "    document.querySelectorAll(sel).forEach(el => {"
            "      const r = el.getBoundingClientRect();"
            "      if (r.width === 0 || r.height === 0) return;"
            "      if (seen.has(el)) return;"
            "      seen.add(el);"
            "      elements.push(el);"
            "    });"
            "  }"
            "  const el = elements[idx - 1];"
            "  if (!el) return null;"
            "  el.scrollIntoView({behavior:'smooth',block:'center'});"
            "  el.focus();"
            "  el.click();"
            "  return {clicked: el.tagName, text: (el.textContent||'').trim().slice(0,50)};"
            "}"
        )
        result = await self._page.evaluate(f"({js})({index})")
        if result is None:
            return {"error": f"未找到元素 #{index}，请先执行 list_elements 获取最新索引", "clicked": None}
        return {"clicked": result["clicked"], "text": result.get("text", ""), "index": index}

    async def type_index(self, index: int, text: str) -> Dict[str, Any]:
        """Type text into element by index (from list_elements). Uses identical element ordering."""
        await self._lazy_start()
        js = (
            "(idx, txt) => {"
            "  const selectors = ["
            "    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',"
            "    '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',"
            "    '[onclick]', '[contenteditable=true]', 'summary', 'details'"
            "  ];"
            "  const seen = new Set();"
            "  const elements = [];"
            "  for (const sel of selectors) {"
            "    document.querySelectorAll(sel).forEach(el => {"
            "      const r = el.getBoundingClientRect();"
            "      if (r.width === 0 || r.height === 0) return;"
            "      if (seen.has(el)) return;"
            "      seen.add(el);"
            "      elements.push(el);"
            "    });"
            "  }"
            "  const el = elements[idx - 1];"
            "  if (!el) return null;"
            "  el.scrollIntoView({behavior:'smooth',block:'center'});"
            "  el.focus();"
            "  const vSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            "  vSetter.call(el, '');"
            "  el.dispatchEvent(new Event('input', {bubbles: true}));"
            "  vSetter.call(el, txt);"
            "  el.dispatchEvent(new Event('input', {bubbles: true}));"
            "  el.dispatchEvent(new Event('change', {bubbles: true}));"
            "  return {typed: el.tagName, name: el.name||el.id||''};"
            "}"
        )
        result = await self._page.evaluate(f"({js})({index}, {repr(text)})")
        if result is None:
            return {"error": f"未找到输入元素 #{index}，请先执行 list_elements 获取最新索引", "typed": None}
        return {"typed": result["typed"], "name": result.get("name", ""), "index": index, "text": text}

    async def click_target(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """RPA-style: click element by semantic target descriptor (role, text_contains, etc)."""
        await self._lazy_start()
        role = str(target.get("role") or "").strip().lower()
        text_contains = str(target.get("text_contains") or target.get("text") or "").strip().lower()
        name_match = str(target.get("name") or "").strip().lower()
        id_match = str(target.get("id") or "").strip().lower()
        placeholder = str(target.get("placeholder") or "").strip().lower()
        index_fb = int(target.get("index", 0) or 0)

        js = """(target) => {
            const selectors = [
                'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',
                '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',
                '[onclick]', '[contenteditable=true]', 'summary', 'details'
            ];
            const seen = new Set();
            const elements = [];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return;
                    if (seen.has(el)) return;
                    seen.add(el);
                    elements.push(el);
                });
            }
            const f = {
                tag: (e) => e.tagName.toLowerCase(),
                tp: (e) => (e.type || '').toLowerCase(),
                nm: (e) => (e.name || '').toLowerCase(),
                id: (e) => (e.id || '').toLowerCase(),
                ph: (e) => (e.placeholder || '').toLowerCase(),
                tx: (e) => (e.textContent || e.value || '').toLowerCase().trim().slice(0, 100),
                ar: (e) => (e.getAttribute('aria-label') || '').toLowerCase(),
            };
            const roleOf = (e) => {
                const t = f.tag(e), tp = f.tp(e), nm = f.nm(e), id = f.id(e);
                const ph = f.ph(e), tx = f.tx(e), ar = f.ar(e);
                if (t === 'a') return 'link';
                if (t === 'input' && (tp === 'submit' || tp === 'button')) return 'submit_button';
                if (t === 'input' || t === 'textarea' || e.contentEditable === 'true') {
                    const all = (ph + ' ' + nm + ' ' + id + ' ' + ar + ' ' + tx).toLowerCase();
                    if (/^(q|wd|query|keyword|search|w|k|qs)$/.test(nm)) return 'search_input';
                    if (all.includes('搜索') || all.includes('请输入') || all.includes('search') || all.includes('keyword') || all.includes('検索')) {
                        if (!all.includes('submit') && !all.includes('button') && nm !== 'su') return 'search_input';
                        return 'text_input';
                    }
                    return 'text_input';
                }
                if (t === 'button' || t === 'select' || e.hasAttribute('role'))
                    return e.hasAttribute('role') ? e.getAttribute('role') : t;
                return t;
            };
            const matches = (el) => {
                const r = roleOf(el), tx = f.tx(el), nm = f.nm(el);
                const id = f.id(el), ph = f.ph(el), ar = f.ar(el);
                if (target.id && id !== target.id) return false;
                if (target.name && nm !== target.name) return false;
                if (target.role && r !== target.role) return false;
                if (target.placeholder && !ph.includes(target.placeholder)) return false;
                if (target.text_contains) {
                    const ft = (tx + ' ' + ph + ' ' + ar + ' ' + nm).toLowerCase();
                    if (!ft.includes(target.text_contains)) return false;
                }
                return true;
            };
            let best = null;
            for (let i = 0; i < elements.length; i++) {
                if (matches(elements[i])) { best = elements[i]; break; }
            }
            if (!best && target.role === 'search_input') {
                const cs = [];
                for (const s of ['input[type=text]', 'input[type=search]', 'textarea', '[contenteditable=true]'])
                    document.querySelectorAll(s).forEach(el => { if (cs.length < 50) cs.push(el); });
                for (const el of cs) {
                    const n = f.nm(el), i = f.id(el), p = f.ph(el);
                    const a = (n + ' ' + i + ' ' + p).toLowerCase();
                    if (/^(q|wd|query|search|keyword|w|k|qs)$/.test(n)) { best = el; break; }
                    if (a.includes('搜索') || a.includes('search')) { best = el; break; }
                }
            }
            if (!best && target.role === 'submit_button') {
                for (const did of ['su', 'search-btn', 'tsf', 'btnK']) {
                    const el = document.getElementById(did);
                    if (el) { best = el; break; }
                }
                if (!best) {
                    const cs = document.querySelectorAll('input[type=submit], button[type=submit]');
                    for (const el of cs) {
                        const t = f.tx(el), n = f.nm(el), i = f.id(el);
                        const a = (t + ' ' + n + ' ' + i).toLowerCase();
                        if (a.includes('搜索') || a.includes('百度一下') || a.includes('search') || a.includes('submit'))
                        { best = el; break; }
                    }
                }
            }
            if (!best && target.index_fb > 0 && target.index_fb <= elements.length)
                best = elements[target.index_fb - 1];
            if (!best) return {found: false, total: elements.length};
            best.scrollIntoView({behavior:'smooth',block:'center'});
            best.focus();
            best.click();
            return {found: true, clicked: best.tagName, text: (best.textContent||'').trim().slice(0,50)};
        }"""
        result = await self._page.evaluate(js, {
            "role": role, "text_contains": text_contains,
            "name": name_match, "id": id_match, "placeholder": placeholder,
            "index_fb": index_fb,
        })
        if not result.get("found"):
            return {"error": f"未找到匹配元素 (total: {result.get('total', 0)})", "clicked": None}
        return {"clicked": result.get("clicked", ""), "text": result.get("text", ""), "target": target}

    async def type_target(self, target: Dict[str, Any], text: str) -> Dict[str, Any]:
        """RPA-style: type text into element by semantic target descriptor."""
        await self._lazy_start()
        role = str(target.get("role") or "").strip().lower()
        text_contains = str(target.get("text_contains") or target.get("text") or "").strip().lower()
        name_match = str(target.get("name") or "").strip().lower()
        id_match = str(target.get("id") or "").strip().lower()
        placeholder = str(target.get("placeholder") or "").strip().lower()
        index_fb = int(target.get("index", 0) or 0)

        js = """(target) => {
            const selectors = [
                'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',
                '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',
                '[onclick]', '[contenteditable=true]', 'summary', 'details'
            ];
            const seen = new Set();
            const elements = [];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return;
                    if (seen.has(el)) return;
                    seen.add(el);
                    elements.push(el);
                });
            }
            const f = {
                tag: (e) => e.tagName.toLowerCase(),
                tp: (e) => (e.type || '').toLowerCase(),
                nm: (e) => (e.name || '').toLowerCase(),
                id: (e) => (e.id || '').toLowerCase(),
                ph: (e) => (e.placeholder || '').toLowerCase(),
                tx: (e) => (e.textContent || e.value || '').toLowerCase().trim().slice(0, 100),
                ar: (e) => (e.getAttribute('aria-label') || '').toLowerCase(),
            };
            const roleOf = (e) => {
                const t = f.tag(e), tp = f.tp(e), nm = f.nm(e), id = f.id(e);
                const ph = f.ph(e), tx = f.tx(e), ar = f.ar(e);
                if (t === 'a') return 'link';
                if (t === 'input' && (tp === 'submit' || tp === 'button')) return 'submit_button';
                if (t === 'input' || t === 'textarea' || e.contentEditable === 'true') {
                    const all = (ph + ' ' + nm + ' ' + id + ' ' + ar + ' ' + tx).toLowerCase();
                    if (/^(q|wd|query|keyword|search|w|k|qs)$/.test(nm)) return 'search_input';
                    if (all.includes('搜索') || all.includes('请输入') || all.includes('search') || all.includes('keyword') || all.includes('検索')) {
                        if (!all.includes('submit') && !all.includes('button') && nm !== 'su') return 'search_input';
                        return 'text_input';
                    }
                    return 'text_input';
                }
                if (t === 'button' || t === 'select' || e.hasAttribute('role'))
                    return e.hasAttribute('role') ? e.getAttribute('role') : t;
                return t;
            };
            const matches = (el) => {
                const r = roleOf(el), tx = f.tx(el), nm = f.nm(el);
                const id = f.id(el), ph = f.ph(el), ar = f.ar(el);
                if (target.id && id !== target.id) return false;
                if (target.name && nm !== target.name) return false;
                if (target.role && r !== target.role) return false;
                if (target.placeholder && !ph.includes(target.placeholder)) return false;
                if (target.text_contains) {
                    const ft = (tx + ' ' + ph + ' ' + ar + ' ' + nm).toLowerCase();
                    if (!ft.includes(target.text_contains)) return false;
                }
                return true;
            };
            let best = null;
            for (let i = 0; i < elements.length; i++) {
                if (matches(elements[i])) { best = elements[i]; break; }
            }
            if (!best && target.role === 'search_input') {
                const cs = [];
                for (const s of ['input[type=text]', 'input[type=search]', 'textarea', '[contenteditable=true]'])
                    document.querySelectorAll(s).forEach(el => { if (cs.length < 50) cs.push(el); });
                for (const el of cs) {
                    const n = f.nm(el), i = f.id(el), p = f.ph(el);
                    const a = (n + ' ' + i + ' ' + p).toLowerCase();
                    if (/^(q|wd|query|search|keyword|w|k|qs)$/.test(n)) { best = el; break; }
                    if (a.includes('搜索') || a.includes('search')) { best = el; break; }
                }
            }
            if (!best && target.index_fb > 0 && target.index_fb <= elements.length)
                best = elements[target.index_fb - 1];
            if (!best) return {found: false, total: elements.length};
            best.scrollIntoView({behavior:'smooth',block:'center'});
            best.focus();
            const vSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            vSetter.call(best, '');
            best.dispatchEvent(new Event('input', {bubbles: true}));
            vSetter.call(best, target._text || '');
            best.dispatchEvent(new Event('input', {bubbles: true}));
            best.dispatchEvent(new Event('change', {bubbles: true}));
            return {found: true, typed: best.tagName, name: best.name||best.id||''};
        }"""
        result = await self._page.evaluate(js, {
            "role": role, "text_contains": text_contains,
            "name": name_match, "id": id_match, "placeholder": placeholder,
            "index_fb": index_fb, "_text": text,
        })
        if not result.get("found"):
            return {"error": f"未找到匹配元素 (total: {result.get('total', 0)})", "typed": None}
        return {"typed": result.get("typed", ""), "name": result.get("name", ""), "target": target, "text": text}


class BrowserTool(BaseTool):
    """Browser Automation Tool — Playwright-based browser control.

    Supports: goto, click, type, screenshot, evaluate, get_text, scroll, wait, search, extract, send_keys.

    Usage by agent: {"tool":"browser","args":{"action":"goto","url":"https://example.com"}}
    """

    SUPPORTED_ACTIONS = [
        "goto", "click", "click_index", "click_target",
        "type", "type_index", "type_target",
        "screenshot", "evaluate", "get_text", "scroll", "wait",
        "search", "extract", "send_keys", "list_elements",
    ]

    def __init__(self, navigation_timeout: int = 30000, **kwargs):
        _ = navigation_timeout
        config = ToolConfig(
            name="browser",
            description="自动化浏览器交互：导航、点击、输入、滚动、截图、搜索、提取数据。支持 RPA 风格的目标定位（click_target/type_target）。",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "操作类型", "enum": self.SUPPORTED_ACTIONS},
                    "url": {"type": "string", "description": "目标 URL"},
                    "selector": {"type": "string", "description": "CSS 选择器"},
                    "index": {"type": "integer", "description": "元素索引号"},
                    "text": {"type": "string", "description": "要输入的文本"},
                    "target": {"type": "object", "description": "RPA 目标描述：{role: 'search_input', text_contains: '搜索', name: 'q', id: 'kw'}。支持字段: role, text_contains, name, id, placeholder, index(回退索引)"},
                    "script": {"type": "string", "description": "要执行的 JavaScript"},
                    "amount": {"type": "integer", "description": "滚动像素数"},
                    "ms": {"type": "integer", "description": "等待毫秒数"},
                    "query": {"type": "string", "description": "搜索查询"},
                    "engine": {"type": "string", "description": "搜索引擎 google/bing/ddg"},
                    "instruction": {"type": "string", "description": "提取指令"},
                    "keys": {"type": "string", "description": "快捷键组合"},
                    "max_items": {"type": "integer", "description": "最大元素数"},
                },
                "required": ["action"],
            },
            metadata={"risk_level": "sensitive", "risk_weight": 20, "category": "browser"},
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        action = params.get("action", "")
        if action not in self.SUPPORTED_ACTIONS:
            return ToolResult(success=False, error=f"不支持的操作: {action}")

        start = time.time()
        session = _get_browser()
        if session is None:
            return ToolResult(
                success=False,
                error="BrowserTool requires Playwright. Install: pip install playwright && playwright install chromium",
            )

        try:
            if action == "goto":
                result = await session.goto(str(params.get("url", "about:blank")))
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已导航到 {result['url']}，页面标题：{result['title']}",
                    metadata={"action": "goto", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "click":
                sel = str(params.get("selector", ""))
                if not sel:
                    return ToolResult(success=False, error="selector 参数必填")
                result = await session.click(sel)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已点击 {sel}",
                    metadata={"action": "click", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "type":
                sel = str(params.get("selector", ""))
                text = str(params.get("text", ""))
                if not sel or not text:
                    return ToolResult(success=False, error="selector 和 text 参数必填")
                result = await session.type_text(sel, text)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已在 {sel} 中输入：{text}",
                    metadata={"action": "type", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "click_target":
                target = params.get("target")
                if not isinstance(target, dict):
                    return ToolResult(success=False, error="target 参数必填，格式：{role: 'search_input'}")
                result = await session.click_target(target)
                if "error" in result:
                    return ToolResult(success=False, error=result["error"], metadata={"action": "click_target", "target": target})
                return ToolResult(
                    success=True, output=result,
                    extracted_content=f"已点击 {result.get('clicked', 'element')} (文本: {result.get('text', '')[:40]})",
                    metadata={"action": "click_target", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "type_target":
                target = params.get("target")
                text = str(params.get("text", ""))
                if not isinstance(target, dict) or not text:
                    return ToolResult(success=False, error="target 和 text 参数必填")
                result = await session.type_target(target, text)
                if "error" in result:
                    return ToolResult(success=False, error=result["error"], metadata={"action": "type_target", "target": target})
                return ToolResult(
                    success=True, output=result,
                    extracted_content=f"已在 {result.get('name', 'element')} 中输入：{text}",
                    metadata={"action": "type_target", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "screenshot":
                path = await session.screenshot()
                return ToolResult(
                    success=True,
                    output={"path": path},
                    extracted_content=f"截图已保存到 {path}",
                    attachments=[path],
                    metadata={"action": "screenshot", "path": path},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "evaluate":
                script = str(params.get("script", ""))
                if not script:
                    return ToolResult(success=False, error="script 参数必填")
                result = await session.evaluate(script)
                return ToolResult(
                    success=True,
                    output={"result": result},
                    extracted_content=str(result)[:500],
                    metadata={"action": "evaluate"},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "get_text":
                sel = params.get("selector", "body") or "body"
                text = await session.get_text(str(sel))
                return ToolResult(
                    success=True,
                    output={"text": text[:10000]},
                    extracted_content=text[:2000],
                    metadata={"action": "get_text", "selector": sel},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "scroll":
                amount = int(params.get("amount", 500))
                result = await session.scroll(amount)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已滚动 {amount}px",
                    metadata={"action": "scroll", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "wait":
                ms = int(params.get("ms", 1000))
                result = await session.wait(ms)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已等待 {ms}ms",
                    metadata={"action": "wait"},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "search":
                query = str(params.get("query", ""))
                if not query:
                    return ToolResult(success=False, error="query 参数必填")
                engine = str(params.get("engine", "google"))
                result = await session.search(query, engine)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已在 {engine} 搜索：{query}，当前页面：{result['title']}",
                    metadata={"action": "search", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "extract":
                instruction = str(params.get("instruction", "提取页面主要内容"))
                result = await session.extract(instruction)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已提取页面内容（{len(result.get('html',''))} 字符），URL: {result.get('url','')}",
                    long_term_memory=f"页面 {result.get('url','')} 的 HTML 已提取",
                    metadata={"action": "extract", "url": result.get("url", "")},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "send_keys":
                keys = str(params.get("keys", ""))
                if not keys:
                    return ToolResult(success=False, error="keys 参数必填")
                await session._lazy_start()
                await session._page.keyboard.press(keys)
                return ToolResult(
                    success=True,
                    output={"keys": keys},
                    extracted_content=f"已按下快捷键：{keys}",
                    metadata={"action": "send_keys"},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "list_elements":
                max_items = int(params.get("max_items", 50))
                result = await session.list_elements(max_items)
                els = result.get("elements", [])
                lines = [f"[{e['index']}] {e['tag']}" + (f" type={e['type']}" if e.get('type') else "") + (f" {e['visible_text']}" if e.get('visible_text') else "") for e in els[:30]]
                summary = "\n".join(lines)
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"页面 {result['url']} 共发现 {len(els)} 个可交互元素：\n{summary}",
                    long_term_memory=f"页面 {result['url']} 的元素索引（用 index 操作）",
                    metadata={"action": "list_elements", "total": len(els)},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "click_index":
                index = int(params.get("index", 0))
                if index < 1:
                    return ToolResult(success=False, error="index 必须 >= 1，请先执行 list_elements 获取索引")
                result = await session.click_index(index)
                if result.get("error"):
                    return ToolResult(success=False, error=result["error"])
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已点击 #{index} ({result.get('text', '')})",
                    metadata={"action": "click_index", **result},
                    latency=(time.time() - start) * 1000,
                )

            elif action == "type_index":
                index = int(params.get("index", 0))
                text = str(params.get("text", ""))
                if index < 1 or not text:
                    return ToolResult(success=False, error="index 和 text 必填")
                result = await session.type_index(index, text)
                if result.get("error"):
                    return ToolResult(success=False, error=result["error"])
                return ToolResult(
                    success=True,
                    output=result,
                    extracted_content=f"已在 #{index} ({result.get('name', '')}) 中输入：{text}",
                    metadata={"action": "type_index", **result},
                    latency=(time.time() - start) * 1000,
                )

            return ToolResult(success=False, error=f"未实现: {action}")

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                extracted_content=f"浏览器操作失败：{e}",
                metadata={"action": action},
                latency=(time.time() - start) * 1000,
            )
