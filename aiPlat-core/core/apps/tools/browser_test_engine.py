"""
BrowserTestEngine — 全功能自动化浏览器测试引擎

职责：
  - 多账号登录管理
  - 页面 BFS 深度递归遍历
  - RPA 风格元素定位与操作生成
  - 截图 + 视频录制
  - 测试报告输出

不经过 LLM，确定性执行。通过 workspace Agent + Skill 触发。
"""
from __future__ import annotations
import logging

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from .browser import _BrowserSession


# ── Data Types ──

@dataclass
class Account:
    username: str
    password: str
    label: str = ""

@dataclass
class TestConfig:
    base_url: str = "https://8.216.36.35"
    login_url: str = ""
    accounts: List[Account] = field(default_factory=list)
    routes: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    include_patterns: List[str] = field(default_factory=list)
    max_recursion_depth: int = 3
    allow_writes: bool = False
    allow_delete: bool = False
    action_timeout_ms: int = 15000
    page_load_timeout_ms: int = 30000
    screenshot_dir: str = ""
    video_enabled: bool = True
    headless: bool = False
    # Safety limits (Plan C: anti-infinite-loop)
    max_total_pages: int = 50
    max_total_actions: int = 500
    max_test_duration_ms: int = 1200000  # 20 minutes

@dataclass
class ActionResult:
    step_id: int
    page_url: str
    depth: int
    element_index: int
    element_role: str
    element_text: str
    action: str
    action_input: Dict[str, Any]
    action_output: Optional[Dict[str, Any]] = None
    result: str = "pending"  # passed | failed | skipped
    error: Optional[str] = None
    duration_ms: float = 0
    screenshot_before: str = ""
    screenshot_after: str = ""
    timestamp: str = ""

@dataclass
class PageResult:
    url: str
    depth: int
    loaded: bool = False
    screenshot: str = ""
    elements_found: int = 0
    actions: List[ActionResult] = field(default_factory=list)
    modals_detected: int = 0

@dataclass
class TestReport:
    started_at: str = ""
    finished_at: str = ""
    total_pages: int = 0
    total_actions: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: float = 0
    pages: List[PageResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Session Manager ──

class SessionManager:
    """多账号登录管理 + cookie/session 复用"""

    def __init__(self, session: _BrowserSession, config: TestConfig):
        self._session = session
        self._config = config
        self._accounts = config.accounts
        self._current_idx = -1
        self._logged_in = False

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    async def ensure_login(self) -> bool:
        if self._logged_in:
            return True
        if not self._accounts:
            self._logged_in = True
            return True
        if not self._config.login_url:
            self._logged_in = True
            return True
        login_url = urljoin(self._config.base_url, self._config.login_url)

        for i, account in enumerate(self._accounts):
            try:
                await self._session.goto(login_url)
                await self._session.wait(2000)

                els = (await self._session.list_elements(100)).get("elements", [])

                username_input = None
                password_input = None
                submit_btn = None

                for el in els:
                    role = el.get("role", "")
                    tp = el.get("type", "")
                    if role == "text_input":
                        if tp == "password":
                            password_input = el
                        elif not username_input:
                            username_input = el
                    elif role == "submit_button":
                        submit_btn = el

                if username_input:
                    await self._session.type_index(username_input["index"], account.username)
                if password_input:
                    await self._session.type_index(password_input["index"], account.password)
                if submit_btn:
                    await self._session.click_index(submit_btn["index"])

                await self._session.wait(3000)

                cur_url = getattr(self._session._page, "url", "") if self._session._page else ""
                if login_url not in cur_url:
                    self._current_idx = i
                    self._logged_in = True
                    return True
            except Exception:
                continue

        return False

    async def switch_account(self) -> bool:
        self._logged_in = False
        self._current_idx = min(self._current_idx + 1, len(self._accounts) - 1)
        return await self.ensure_login()

    def current_account(self) -> Optional[Account]:
        if 0 <= self._current_idx < len(self._accounts):
            return self._accounts[self._current_idx]
        return None


# ── Action Generator ──

class ActionGenerator:
    """根据元素 role 生成操作步骤。写操作受 allow_writes/allow_delete 控制"""

    SKIP_TEXT = ["删除", "移除", "清空", "销毁", "卸载", "delete", "remove", "destroy"]

    def __init__(self, allow_writes: bool = False, allow_delete: bool = False):
        self._allow_writes = allow_writes
        self._allow_delete = allow_delete

    @staticmethod
    def _smart_text(el: Dict[str, Any]) -> str:
        ph = (el.get("placeholder") or "").strip().lower()
        name = (el.get("name") or el.get("visible_text") or "").strip().lower()
        label = (el.get("label") or "").strip().lower()
        tp = (el.get("type") or "").strip().lower()
        combined = f"{ph} {name} {label} {tp}"

        # Email — Japanese sites often use メールアドレス / Eメール
        if tp == "email" or "email" in combined or "mail" in combined or "メール" in combined or "Ｅメール" in combined:
            return "test@example.com"

        # Password
        if tp == "password" or "password" in combined or "パスワード" in combined:
            return "Test1234!"

        # Phone — Japanese format with hyphens
        if tp == "tel" or "phone" in combined or "電話" in combined or "携帯" in combined or "電話番号" in combined or "でんわ" in combined:
            return "090-1234-5678"

        # Company / organization (must be before name checks: 企業名 has 名 in it)
        if "企業" in combined or "会社" in combined or "company" in combined or "法人" in combined or "組織" in combined or "団体" in combined:
            return "テスト株式会社"

        # Full name (family+given combined) — must be before single name checks
        if "氏名" in combined or "氏 名" in combined or "氏　名" in combined or "fullname" in combined or "full_name" in combined:
            return "山田 太郎"

        # Family name / surname
        if "姓" in combined or "苗字" in combined or "family" in combined or "surname" in combined or "last_name" in combined or "lastname" in combined:
            return "山田"

        # Given name / first name (must be after company check: 会社名 != firstname)
        if "名" in combined or "名前" in combined or "given" in combined or "first_name" in combined or "firstname" in combined:
            return "太郎"

        # Generic username / nickname
        if "username" in combined or "ユーザー名" in combined or "nickname" in combined or "ニックネーム" in combined:
            return "testuser"

        # Postal code — Japanese 〒 format
        if "郵便" in combined or "〒" in combined or "postal" in combined or "zip" in combined or "zipcode" in combined or "post_code" in combined:
            return "123-4567"

        # Address
        if "住所" in combined or "address" in combined or "所在地" in combined:
            return "東京都新宿区西新宿2-8-1"

        # Birthday / date
        if "生年月日" in combined or "誕生日" in combined or "birthday" in combined or "birth" in combined or "生年" in combined:
            return "1990-01-01"

        # Age / number
        if tp == "number" or "年" in combined or "歳" in combined or "age" in combined or "年齢" in combined:
            return "30"

        # URL / homepage
        if "url" in combined or "https://" in combined or "ホームページ" in combined or "website" in combined or "hp" in combined:
            return "https://example.com"

        # Interview code / access code
        if "xxxx" in combined or "面接" in combined or "コード" in combined or "code" in combined or "番号" in combined:
            return "1234-5678"

        # Department
        if "部署" in combined or "department" in combined or "所属" in combined:
            return "開発部"

        # Job title / position
        if "役職" in combined or "title" in combined or "職種" in combined or "position" in combined:
            return "エンジニア"

        # Generic text catch-all
        return "test"

    def should_skip(self, element: Dict[str, Any]) -> Tuple[bool, str]:
        text = (element.get("visible_text") or element.get("name") or "").lower()
        for kw in self.SKIP_TEXT:
            if kw.lower() in text:
                if not self._allow_delete:
                    return True, f"危险操作已跳过: {kw}"
        return False, ""

    def generate(self, elements: List[Dict[str, Any]], skip_links: bool = False) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for el in elements:
            role = el.get("role", "")
            tag = el.get("tag", "")
            if skip_links and role == "link":
                continue
            skip, reason = self.should_skip(el)
            if skip:
                actions.append({"skip": True, "reason": reason, "element": el})
                continue

            action = self._role_to_action(role, tag, el)
            if action:
                action["element"] = el
                actions.append(action)
        # Sort: type/select actions before clicks, so forms are filled before submit
        actions.sort(key=lambda a: 0 if a.get("action") in ("type_target",) else 1)
        return actions

    def _role_to_action(self, role: str, tag: str, el: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        idx = el.get("index")
        text = el.get("visible_text", "")
        name = el.get("name", "")
        ph = el.get("placeholder", "")
        tp = (el.get("type") or "").lower()

        if role == "link":
            return {"action": "click_target", "target": {"role": "link", "text_contains": text[:20]}}

        if role == "search_input":
            ts = str(int(time.time()))[-6:]
            return {"action": "type_target", "target": {"role": "search_input"}, "text": f"test_{ts}"}

        if role == "submit_button":
            return {"action": "click_target", "target": {"role": "submit_button"}}

        if role == "text_input":
            if tp == "radio" or tp == "checkbox":
                return {"action": "click_target", "target": {"role": "text_input", "name": name, "placeholder": ph}}
            return {"action": "type_target", "target": {"role": "text_input", "name": name, "placeholder": ph}, "text": self._smart_text(el)}

        if role == "button":
            return {"action": "click_target", "target": {"role": "button", "text_contains": text[:20]}}

        if role in ("checkbox",):
            return {"action": "click_target", "target": {"role": "checkbox", "text_contains": text[:20]}}

        if role in ("select",):
            return {"action": "click_target", "target": {"role": "select", "text_contains": text[:20]}}

        if role == "textarea":
            return {"action": "type_target", "target": {"role": "textarea"}, "text": "test content"}

        return None


# ── Page Discoverer ──

class PageDiscoverer:
    """页面 BFS 遍历 + 弹窗递归检测"""

    def __init__(self, session: _BrowserSession, config: TestConfig):
        self._session = session
        self._config = config
        self._visited: Set[str] = set()

    def normalize_url(self, url: str) -> str:
        base = url.split("?")[0]
        if "#" in base:
            parts = base.split("#", 1)
            return f"{parts[0].rstrip('/')}#{parts[1]}"
        return base.rstrip("/")

    async def discover(self, url: str) -> PageResult:
        norm = self.normalize_url(url)
        result = PageResult(url=norm, depth=0)

        try:
            await self._session.goto(norm)
            await self._session.wait(2000)
            result.loaded = True

            sc_path = await self._take_screenshot(norm, "loaded")
            result.screenshot = sc_path

            els_data = await self._session.list_elements(100)
            elements = els_data.get("elements", [])
            result.elements_found = len(elements)
        except Exception as e:
            result.loaded = False
            result.actions.append(ActionResult(
                step_id=0, page_url=norm, depth=0, element_index=0,
                element_role="", element_text="", action="goto",
                action_input={"url": norm}, result="failed",
                error=str(e),
            ))
        return result

    async def detect_modal(self) -> Optional[Dict[str, Any]]:
        try:
            js = """(() => {
                const modals = document.querySelectorAll('[role=dialog], .modal, .ant-modal, .el-dialog, .MuiDialog-root, [data-modal]');
                for (const m of modals) {
                    const r = m.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && getComputedStyle(m).display !== 'none') {
                        const closeBtn = m.querySelector('[aria-label=Close], .close, .ant-modal-close, [data-close]');
                        return {
                            found: true,
                            visible: true,
                            hasCloseButton: closeBtn !== null,
                            tag: m.tagName,
                            className: m.className.slice(0, 50),
                            id: m.id
                        };
                    }
                }
                return {found: false};
            })()"""
            result = await self._session.evaluate(js)
            if isinstance(result, dict) and result.get("found"):
                return result
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return None

    async def close_modal(self) -> bool:
        try:
            js = """(() => {
                const closeBtn = document.querySelector('[aria-label=Close], .ant-modal-close, .modal .close, [data-close]');
                if (closeBtn) { closeBtn.click(); return {method: 'close_button'}; }
                const cancelBtn = document.querySelector('.ant-modal-footer button:not(.ant-btn-primary), .modal-footer .cancel, [data-cancel]');
                if (cancelBtn) { cancelBtn.click(); return {method: 'cancel_button'}; }
                return {method: 'none'};
            })()"""
            result = await self._session.evaluate(js)
            await self._session.wait(500)
            return isinstance(result, dict) and result.get("method") != "none"
        except Exception:
            return False

    async def get_current_url(self) -> str:
        try:
            return self._session._page.url if self._session._page else ""
        except Exception:
            return ""

    def is_new_page(self, previous_url: str) -> bool:
        current = self.normalize_url(self.get_current_url())
        previous = self.normalize_url(previous_url)
        return current != previous

    async def _take_screenshot(self, url: str, label: str) -> str:
        screenshot_dir = self._config.screenshot_dir or tempfile.mkdtemp(prefix="browser_test_")
        os.makedirs(screenshot_dir, exist_ok=True)
        safe_name = url.replace("/", "_").replace(":", "_").replace("?", "_")[:60]
        ts = int(time.time() * 1000)
        path = os.path.join(screenshot_dir, f"{safe_name}_{label}_{ts}.png")
        try:
            await self._session.screenshot(path)
            return path
        except Exception:
            return ""


# ── Action Executor ──

class ActionExecutor:
    """单步操作执行 + 截图对比 + 错误处理"""

    def __init__(self, session: _BrowserSession, config: TestConfig):
        self._session = session
        self._config = config
        self._step_counter = 0

    async def execute(self, action: Dict[str, Any], page_url: str, depth: int) -> ActionResult:
        self._step_counter += 1
        step_id = self._step_counter
        el = action.get("element", {})

        result = ActionResult(
            step_id=step_id,
            page_url=page_url,
            depth=depth,
            element_index=el.get("index", 0),
            element_role=el.get("role", ""),
            element_text=el.get("visible_text", "") or el.get("name", ""),
            action=action.get("action", ""),
            action_input={k: v for k, v in action.items() if k not in ("element", "skip", "reason")},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if action.get("skip"):
            result.result = "skipped"
            result.error = action.get("reason", "skipped")
            return result

        try:
            result.screenshot_before = await self._capture(page_url, f"step{step_id}_before")

            start = time.time()
            output = await self._execute_action(action)
            result.duration_ms = (time.time() - start) * 1000

            await self._session.wait(500)
            result.screenshot_after = await self._capture(page_url, f"step{step_id}_after")
            result.action_output = output
            result.result = "passed"

            # Detect form validation errors after action
            if action.get("action") in ("click_target", "click_index", "type_target", "type_index"):
                try:
                    form_errors = await self._session.detect_form_errors()
                    if form_errors:
                        result.result = "failed"
                        err_texts = [e.get("text", "")[:80] for e in form_errors[:3]]
                        result.error = " | ".join(err_texts)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        except Exception as e:
            result.result = "failed"
            result.error = str(e)[:500]
            result.duration_ms = (time.time() - start) * 1000 if 'start' in dir() else 0

        return result

    async def _execute_action(self, action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        act = action["action"]
        if act == "click_target":
            target = action.get("target", {})
            r = await self._session.click_target(target)
            return r if "error" not in r else None
        elif act == "type_target":
            target = action.get("target", {})
            text = action.get("text", "test")
            r = await self._session.type_target(target, text)
            return r if "error" not in r else None
        elif act == "click_index":
            r = await self._session.click_index(action.get("index", 1))
            return r if "error" not in r else None
        elif act == "type_index":
            r = await self._session.type_index(action.get("index", 1), action.get("text", "test"))
            return r if "error" not in r else None
        else:
            return {"note": f"action '{act}' not yet implemented"}

    async def _capture(self, url: str, label: str) -> str:
        sc_dir = self._config.screenshot_dir or tempfile.mkdtemp(prefix="btest_")
        os.makedirs(sc_dir, exist_ok=True)
        safe = url.replace("/", "_").replace(":", "_")[:50]
        path = os.path.join(sc_dir, f"{safe}_{label}_{int(time.time()*1000)}.png")
        try:
            await self._session.screenshot(path)
            return path
        except Exception:
            return ""


# ── Test Engine ──

class BrowserTestEngine:
    """全功能浏览器自动化测试引擎"""

    def __init__(self, config: TestConfig):
        self._config = config
        self._session: Optional[_BrowserSession] = None
        self._session_mgr: Optional[SessionManager] = None
        self._discoverer: Optional[PageDiscoverer] = None
        self._executor: Optional[ActionExecutor] = None
        self._report = TestReport()
        self._stop_requested = False
        self._progress_callback: Optional[callable] = None

    def on_progress(self, callback: callable):
        self._progress_callback = callback

    def stop(self):
        self._stop_requested = True

    async def run(self) -> TestReport:
        self._report.started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.time()

        self._session = _BrowserSession()
        try:
            video_dir = ""
            if self._config.video_enabled:
                video_dir = self._config.screenshot_dir or os.path.join(
                    os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "videos",
                    f"test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                )
                os.makedirs(video_dir, exist_ok=True)
            await self._session._lazy_start(
                record_video_dir=video_dir,
                headless=self._config.headless,
            )
        except Exception as e:
            self._report.errors.append(f"Browser init failed: {e}")
            return self._report

        self._session_mgr = SessionManager(self._session, self._config)
        self._discoverer = PageDiscoverer(self._session, self._config)
        self._executor = ActionExecutor(self._session, self._config)
        generator = ActionGenerator(
            allow_writes=self._config.allow_writes,
            allow_delete=self._config.allow_delete,
        )

        if not await self._session_mgr.ensure_login():
            self._report.errors.append("Login failed with all accounts")
            return self._report

        routes = self._config.routes or self._default_routes()
        self._notify_progress("started", {"total_routes": len(routes)})

        visited = set()
        content_fingerprints = set()  # anti-loop: dedup by element content
        queue: List[Tuple[str, int]] = [(r, 0) for r in routes]

        while queue and not self._stop_requested:
            url, depth = queue.pop(0)
            norm = self._discoverer.normalize_url(urljoin(self._config.base_url, url))
            if norm in visited:
                continue
            if self._should_skip_url(norm, auto_expand=(depth > 0)):
                self._notify_progress("page_skip", {"url": norm, "reason": "url_filtered"})
                continue
            visited.add(norm)

            self._notify_progress("page_start", {"url": norm, "depth": depth, "remaining": len(queue)})

            page_result = await self._discoverer.discover(norm)
            page_result.depth = depth
            self._report.total_pages += 1

            if not page_result.loaded:
                self._report.pages.append(page_result)
                self._notify_progress("page_fail", {"url": norm, "reason": "load_failed"})
                continue

            elements = (await self._session.list_elements(100)).get("elements", [])
            is_fp_page = norm and "#/__page_fp_" in norm
            actions = generator.generate(elements, skip_links=is_fp_page)

            for action in actions:
                if self._stop_requested:
                    break
                ar = await self._executor.execute(action, norm, depth)
                page_result.actions.append(ar)
                self._report.total_actions += 1
                if ar.result == "passed":
                    self._report.passed += 1
                elif ar.result == "failed":
                    self._report.failed += 1
                else:
                    self._report.skipped += 1
                self._notify_progress("action_done", {
                    "url": norm, "step": ar.step_id, "result": ar.result,
                    "action": ar.action, "role": ar.element_role,
                })

                # Safety limit checks
                limit_reason = ""
                if self._report.total_pages >= self._config.max_total_pages:
                    limit_reason = f"max pages ({self._config.max_total_pages})"
                if self._report.total_actions >= self._config.max_total_actions:
                    limit_reason = f"max actions ({self._config.max_total_actions})"
                elapsed = (time.time() - t0) * 1000
                if elapsed >= self._config.max_test_duration_ms:
                    limit_reason = f"max duration ({self._config.max_test_duration_ms/1000:.0f}s)"
                if limit_reason:
                    self._report.errors.append(f"Safety limit reached: {limit_reason}")
                    self._stop_requested = True
                    break
                # After each action, detect navigation for recursion
                if ar.result == "passed" and ar.action == "click_target":
                    page_changed = False
                    nav_kind = ""
                    new_hash = ""
                    try:
                        new_url = self._session._page.url if self._session._page else ""
                        cur_hash = await self._session.evaluate("window.location.hash")
                        old_hash = "#" + norm.split("#")[1] if "#" in norm else ""
                        cur_hash = str(cur_hash or "").strip()
                        old_hash = str(old_hash).strip()

                        # Check hash change (for HashRouter: #/careers → #/enterprise)
                        if cur_hash and cur_hash != old_hash:
                            page_changed = True
                            new_hash = cur_hash
                            nav_kind = "hash_change"
                        # Check URL change (for BrowserRouter: /overview → /alerts)
                        elif new_url and self._discoverer.normalize_url(new_url) != norm:
                            page_changed = True
                            path = new_url.replace(self._config.base_url.rstrip("/"), "")
                            new_hash = path if path else "/"
                            nav_kind = "url_change"
                        # Check element change (for AJAX form steps without URL change)
                        if not page_changed:
                            try:
                                await self._session.wait(300)
                                new_els = (await self._session.list_elements(20)).get("elements", [])
                                if new_els:
                                    new_fp = self._compute_fingerprint(new_els)
                                    old_fp = self._compute_fingerprint(elements)
                                    if new_fp != old_fp and new_fp not in content_fingerprints:
                                        page_changed = True
                                        new_hash = f"#/__page_fp_{new_fp}"
                                        elements = new_els  # update for subsequent comparisons
                                        content_fingerprints.add(new_fp)
                                        nav_kind = "element_change"
                            except Exception as e:
                                logging.debug(str(e), exc_info=True)
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)

                    if page_changed and new_hash:
                        # Element-change pages (AJAX form steps): process inline, don't queue
                        if nav_kind == "element_change":
                            # AJAX form steps: detect recursively (up to 10 steps)
                            fp_depth = depth
                            fp_navigated = False
                            for _fp_step in range(10):
                                fp_url = f"{norm}#fp_{len(content_fingerprints)}"
                                fp_result = PageResult(url=fp_url, depth=fp_depth + 1)
                                fp_result.elements_found = len(elements)
                                self._report.total_pages += 1
                                fp_actions = generator.generate(elements, skip_links=True)
                                fp_changed = False
                                for fp_a in fp_actions:
                                    if self._stop_requested:
                                        break
                                    far = await self._executor.execute(fp_a, fp_url, fp_depth + 1)
                                    fp_result.actions.append(far)
                                    self._report.total_actions += 1
                                    if far.result == "passed":
                                        self._report.passed += 1
                                    elif far.result == "failed":
                                        self._report.failed += 1
                                    else:
                                        self._report.skipped += 1
                                    if far.result == "passed" and far.action == "click_target":
                                        # Detect hash/URL navigation
                                        try:
                                            cur_h = await self._session.evaluate("window.location.hash")
                                            cur_h = str(cur_h or "").strip()
                                            old_h = "#" + norm.split("#")[1] if "#" in norm else ""
                                            if cur_h and cur_h != old_h:
                                                fp_navigated = True
                                                if (fp_depth + 1) <= self._config.max_recursion_depth:
                                                    nf = f"{self._config.base_url}{cur_h}"
                                                    nn = self._discoverer.normalize_url(nf)
                                                    if nn not in visited:
                                                        queue.append((cur_h, fp_depth + 1))
                                                break
                                            nu = self._session._page.url if self._session._page else ""
                                            if nu and self._discoverer.normalize_url(nu) != norm:
                                                fp_navigated = True
                                                if (fp_depth + 1) <= self._config.max_recursion_depth:
                                                    pth = nu.replace(self._config.base_url.rstrip("/"), "")
                                                    nh = pth if pth else "/"
                                                    nn = self._discoverer.normalize_url(nu)
                                                    if nn not in visited:
                                                        queue.append((nh, fp_depth + 1))
                                                break
                                        except Exception as e:
                                            logging.debug(str(e), exc_info=True)
                                        # Detect element change for recursive form steps
                                        try:
                                            await self._session.wait(300)
                                            new_els = (await self._session.list_elements(20)).get("elements", [])
                                            if new_els:
                                                new_fp = self._compute_fingerprint(new_els)
                                                old_fp = self._compute_fingerprint(elements)
                                                if new_fp != old_fp and new_fp not in content_fingerprints:
                                                    elements = new_els
                                                    content_fingerprints.add(new_fp)
                                                    fp_changed = True
                                                    break
                                        except Exception as e:
                                            logging.debug(str(e), exc_info=True)
                                self._report.pages.append(fp_result)
                                self._notify_progress("nav_enqueue", {
                                    "from": norm, "to": fp_url,
                                    "depth": fp_depth + 1, "kind": nav_kind,
                                })
                                if fp_navigated or not fp_changed:
                                    break
                                fp_depth += 1
                            # Navigate back to original page for remaining actions
                            try:
                                await self._session.goto(norm)
                                await self._session.wait(2000)
                            except Exception as e:
                                logging.debug(str(e), exc_info=True)
                            continue

                        # Hash/URL-change pages: queue for BFS
                        if (depth + 1) <= self._config.max_recursion_depth:
                            cur_full = f"{self._config.base_url}{new_hash}"
                            cur_norm = self._discoverer.normalize_url(cur_full)
                            if cur_norm not in visited:
                                queue.append((new_hash, depth + 1))
                                self._notify_progress("nav_enqueue", {
                                    "from": norm, "to": cur_norm,
                                    "depth": depth + 1, "kind": nav_kind,
                                })
                            else:
                                self._notify_progress("nav_skip", {
                                    "from": norm, "to": cur_norm,
                                    "reason": "already_visited",
                                })
                        else:
                            self._notify_progress("nav_skip", {
                                "from": norm, "to": new_hash,
                                "reason": "depth_exceeded",
                                "depth": depth + 1,
                                "max": self._config.max_recursion_depth,
                            })
                        # Navigate back to continue testing remaining elements
                        try:
                            await self._session.goto(norm)
                            await self._session.wait(2000)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)

            self._report.pages.append(page_result)

            if depth < self._config.max_recursion_depth:
                has_modal = await self._discoverer.detect_modal()
                while has_modal and not self._stop_requested:
                    page_result.modals_detected += 1
                    modal_norm = f"{norm}__modal_{page_result.modals_detected}"
                    if modal_norm not in visited:
                        visited.add(modal_norm)
                        modal_result = PageResult(url=modal_norm, depth=depth + 1)
                        self._report.total_pages += 1
                        el_data = await self._session.list_elements(100)
                        modal_elements = el_data.get("elements", [])
                        modal_actions = generator.generate(modal_elements)
                        self._report.total_actions += len(modal_actions)
                        for m_action in modal_actions:
                            if self._stop_requested:
                                break
                            mr = await self._executor.execute(m_action, modal_norm, depth + 1)
                            modal_result.actions.append(mr)
                            if mr.result == "passed":
                                self._report.passed += 1
                            elif mr.result == "failed":
                                self._report.failed += 1
                            else:
                                self._report.skipped += 1
                            self._notify_progress("action_done", {
                                "url": modal_norm, "step": mr.step_id, "result": mr.result,
                                "action": mr.action, "role": mr.element_role,
                            })
                        self._report.pages.append(modal_result)
                    await self._discoverer.close_modal()
                    await self._session.wait(500)
                    has_modal = await self._discoverer.detect_modal()

        self._report.finished_at = datetime.now(timezone.utc).isoformat()
        self._report.total_duration_ms = (time.time() - t0) * 1000

        try:
            video_path = await self._session.stop()
            if video_path:
                self._report.metadata = self._report.metadata or {}
                self._report.metadata["video_path"] = video_path
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        self._notify_progress("finished", {"report": self._report_summary()})

        return self._report

    def _report_summary(self) -> Dict[str, Any]:
        return {
            "total_pages": self._report.total_pages,
            "total_actions": self._report.total_actions,
            "passed": self._report.passed,
            "failed": self._report.failed,
            "skipped": self._report.skipped,
            "duration_ms": self._report.total_duration_ms,
            "errors": len(self._report.errors),
        }

    def _notify_progress(self, event: str, data: Dict[str, Any]):
        if self._progress_callback:
            try:
                self._progress_callback(event, data)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    def _should_skip_url(self, url: str, auto_expand: bool = False) -> bool:
        import re
        if self._config.include_patterns:
            if not any(re.search(p, url) for p in self._config.include_patterns):
                if auto_expand:
                    return False
                return True
        for p in self._config.exclude_patterns:
            if re.search(p, url):
                return True
        return False

    @staticmethod
    def _compute_fingerprint(elements: List[Dict[str, Any]]) -> str:
        """Compute content fingerprint from first N elements' roles + text for dedup."""
        if not elements:
            return "empty"
        signatures = []
        for e in elements[:5]:
            signatures.append(f"{e.get('role','')}:{e.get('visible_text','')[:20]}")
        return "|".join(signatures)

    @staticmethod
    def _default_routes() -> List[str]:
        return [
            "/",
            "/overview",
            "/onboarding",
            "/diagnostics",
            "/infra/nodes",
            "/infra/models",
            "/infra/services",
            "/infra/scheduler",
            "/infra/storage",
            "/infra/network",
            "/infra/monitoring",
            "/core/agents",
            "/core/skills",
            "/core/tools",
            "/core/plugins",
            "/core/mcp",
            "/core/workflows",
            "/core/resources",
            "/core/variables",
            "/core/credentials",
            "/core/memory",
            "/core/prompts",
            "/core/jobs",
            "/core/agent-insight",
            "/workspace/agents",
            "/workspace/skills",
            "/workspace/skills-lint",
            "/workspace/marketplace",
            "/workspace/packages",
            "/workspace/mcp",
            "/platform/gateway",
            "/platform/auth",
            "/platform/tenant",
            "/platform/kb",
            "/app/channels",
            "/app/sessions",
            "/app/builder",
            "/app/builder/projects",
        ]


# ── Global Engine Registry (shared by router and integration.py for stop support) ──

import threading

_active_engine: Optional[object] = None
_engine_lock = threading.Lock()


def register_engine(engine):
    global _active_engine
    with _engine_lock:
        _active_engine = engine


def unregister_engine():
    global _active_engine
    with _engine_lock:
        _active_engine = None


def get_active_engine():
    with _engine_lock:
        return _active_engine
