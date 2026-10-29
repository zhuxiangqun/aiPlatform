"""e2e_test handler — recon / scaffold / validate / run (fail-closed).

Keeps norms in SKILL.md + references/; this module makes the ring executable
instead of prompt-only simulation.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _load_sibling(module_stem: str, *attrs: str):
    """Absolute import, with a sibling fallback for spec_from_file_location loads."""
    try:
        mod = __import__(
            f"core.engine.skills.e2e_test.{module_stem}",
            fromlist=list(attrs),
        )
        return tuple(getattr(mod, a) for a in attrs)
    except Exception:
        import importlib.util

        path = Path(__file__).resolve().parent / f"{module_stem}.py"
        spec = importlib.util.spec_from_file_location(f"e2e_test_{module_stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return tuple(getattr(mod, a) for a in attrs)


validate_e2e_deliverable, validate_report, locator_change_grounded = _load_sibling(
    "validate",
    "validate_e2e_deliverable",
    "validate_report",
    "locator_change_grounded",
)
parse_flow, scaffold_flow_spec, find_element, login_controls, login_gap = _load_sibling(
    "flow",
    "parse_flow",
    "scaffold_flow_spec",
    "find_element",
    "login_controls",
    "login_gap",
)


def _pick_text(el: Dict[str, Any]) -> str:
    for key in ("visible_text", "aria_label", "testid", "name", "placeholder"):
        v = str(el.get(key) or "").strip()
        if v:
            return v[:40]
    return ""


def _role_for_playwright(el: Dict[str, Any]) -> Optional[str]:
    role = str(el.get("role") or "").strip().lower()
    tag = str(el.get("tag") or "").strip().lower()
    mapping = {
        "link": "link",
        "button": "button",
        "submit_button": "button",
        "tab": "tab",
        "menuitem": "menuitem",
        "search_input": None,
        "text_input": None,
    }
    if role in mapping:
        return mapping[role]
    if tag in ("a", "button"):
        return "link" if tag == "a" else "button"
    return None


def scaffold_spec_from_recon(url: str, elements: List[Dict[str, Any]]) -> str:
    """Deterministic smoke spec from list_elements (semantic locators only)."""
    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"// recon: list_elements n={len(elements)} url={url}",
        "test('e2e recon smoke', async ({ page }) => {",
        f"  await page.goto({url!r});",
    ]
    used = 0
    for el in elements:
        if used >= 8:
            break
        name = _pick_text(el)
        testid = str(el.get("testid") or "").strip()
        pw_role = _role_for_playwright(el)
        if testid:
            lines.append(f"  await expect(page.getByTestId({testid!r})).toBeVisible();")
            used += 1
            continue
        if pw_role and name:
            lines.append(
                f"  await expect(page.getByRole({pw_role!r}, {{ name: {name!r} }})).toBeVisible();"
            )
            used += 1
            continue
        if name and str(el.get("tag") or "").lower() in ("input", "textarea"):
            lines.append(
                f"  await expect(page.getByRole('textbox', {{ name: {name!r} }})).toBeVisible();"
            )
            used += 1
    if used == 0:
        lines.append("  await expect(page).toHaveURL(/.+/);")
    lines.append("});")
    lines.append("")
    return "\n".join(lines)


def _slug_from_url(url: str) -> str:
    host = urlparse(url).netloc or "site"
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", host).strip("_")[:40] or "site"


async def _snapshot(session: Any, *, max_items: int = 40) -> Dict[str, Any]:
    shot = await session.screenshot()
    listed = await session.list_elements(max_items)
    elements = listed.get("elements") or []
    page = getattr(session, "_page", None)
    url = str(getattr(page, "url", "") or listed.get("url") or "")
    return {
        "url": url,
        "elements": elements,
        "elements_found": len(elements) if isinstance(elements, list) else 0,
        "screenshot": shot,
        "__e2e_recon__": True,
    }


async def _recon(url: str, *, max_items: int = 40) -> Dict[str, Any]:
    from core.apps.tools.browser import _BrowserSession

    session = _BrowserSession()
    try:
        await session._lazy_start(headless=True)
        await session.goto(url)
        return await _snapshot(session, max_items=max_items)
    finally:
        try:
            await session.stop()
        except Exception:
            logger.debug("browser session stop failed", exc_info=True)


async def _run_flow_live(steps: List[Dict[str, Any]], *, max_items: int = 40) -> Dict[str, Any]:
    """Execute flow steps with one browser session; recon after each step."""
    if not steps:
        return {"error": "empty flow", "recon_by_step": {}}

    from core.apps.tools.browser import _BrowserSession

    session = _BrowserSession()
    recon_by_step: Dict[str, Dict[str, Any]] = {}
    try:
        await session._lazy_start(headless=True)
        for step in steps:
            sid = str(step.get("id") or "")
            action = str(step.get("action") or "")
            step_url = str(step.get("url") or "").strip()
            if action in ("goto", "login", "recon") and step_url:
                await session.goto(step_url)
            snap = await _snapshot(session, max_items=max_items)
            elements = list(snap.get("elements") or [])
            before_url = str(snap.get("url") or "")

            if action == "login":
                gap = login_gap(step, elements)
                if gap:
                    return {
                        "error": f"{sid}: {gap}",
                        "recon_by_step": recon_by_step,
                        "refused_rebind": True,
                    }
                controls = login_controls(elements)
                user_el = controls.get("user")
                pass_el = controls.get("password")
                submit = controls.get("submit")
                recon_by_step[sid] = {
                    **snap,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                if user_el:
                    await session.type_index(int(user_el["index"]), str(step.get("username") or ""))
                if pass_el:
                    await session.type_index(int(pass_el["index"]), str(step.get("password") or ""))
                if submit:
                    await session.click_index(int(submit["index"]))
                await session.wait(800)
                after = await _snapshot(session, max_items=max_items)
                after_els = list(after.get("elements") or [])
                still_password = any(
                    str(e.get("type") or "").lower() == "password" for e in after_els
                )
                after_url = str(after.get("url") or "")
                if still_password and after_url.rstrip("/") == before_url.rstrip("/"):
                    return {
                        "error": f"{sid}: login stayed on the form",
                        "recon_by_step": recon_by_step,
                        "refused_rebind": True,
                    }
                recon_by_step[sid] = {
                    **after,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                continue

            if action == "click":
                target = str(step.get("target") or step.get("name") or step.get("text") or "")
                role = str(step.get("role") or "")
                el = find_element(elements, target=target, role=role)
                if not el:
                    return {
                        "error": f"{sid}: click target not in list_elements — refuse inventing locator",
                        "recon_by_step": recon_by_step,
                        "refused_rebind": True,
                    }
                recon_by_step[sid] = {
                    **snap,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                await session.click_index(int(el["index"]))
                await session.wait(500)
                after = await _snapshot(session, max_items=max_items)
                recon_by_step[sid] = {
                    **after,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                continue

            if action == "fill":
                target = str(step.get("target") or step.get("name") or "")
                role = str(step.get("role") or "text_input")
                el = find_element(elements, target=target, role=role)
                if not el:
                    return {
                        "error": f"{sid}: fill target not in list_elements",
                        "recon_by_step": recon_by_step,
                        "refused_rebind": True,
                    }
                recon_by_step[sid] = {
                    **snap,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                await session.type_index(int(el["index"]), str(step.get("value") or ""))
                after = await _snapshot(session, max_items=max_items)
                recon_by_step[sid] = {
                    **after,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                continue

            if action == "expect_url":
                expect = str(step.get("expect_url") or step.get("expect") or "")
                cur = before_url
                path = urlparse(cur).path or "/"
                if expect and expect not in cur and expect not in path:
                    return {
                        "error": f"{sid}: expect_url {expect} not matched by {cur}",
                        "recon_by_step": recon_by_step,
                    }
                recon_by_step[sid] = {
                    **snap,
                    "action_elements": elements,
                    "url_before": before_url,
                }
                continue

            recon_by_step[sid] = {
                **snap,
                "action_elements": elements,
                "url_before": before_url,
            }

        spec = scaffold_flow_spec(steps, recon_by_step)
        return {
            "result": "ok",
            "steps": steps,
            "recon_by_step": recon_by_step,
            "spec": spec,
            "__e2e_recon__": True,
        }
    finally:
        try:
            await session.stop()
        except Exception:
            logger.debug("flow browser stop failed", exc_info=True)


def _run_playwright(cwd: str, *, timeout_s: int = 180) -> Dict[str, Any]:
    root = Path(cwd).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": f"run cwd not a directory: {root}"}
    cmd = ("npx", "playwright", "test", "--reporter=list")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(30, int(timeout_s)),
        )
    except FileNotFoundError:
        return {"ok": False, "error": "npx not found — install Node.js to run Playwright"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"playwright timed out after {timeout_s}s"}
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    err = "" if proc.returncode == 0 else (out[-8000:] or "playwright test failed")
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": out[-8000:],
        "error": err,
    }


def _write_spec(workdir: Path, url: str, spec: str) -> Path:
    tests = workdir / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    path = tests / f"{_slug_from_url(url)}.spec.ts"
    path.write_text(spec, encoding="utf-8")
    cfg = workdir / "playwright.config.ts"
    if not cfg.is_file():
        cfg.write_text(
            "import { defineConfig } from '@playwright/test';\n"
            "export default defineConfig({ testDir: './tests', timeout: 30000 });\n",
            encoding="utf-8",
        )
    return path


_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_URL_KEYS = ("url", "base_url", "target_url", "page_url", "login_url")
_PROMPT_KEYS = ("prompt", "input", "task", "user_task", "query", "instruction")


def _first_http_url(value: Any) -> str:
    if isinstance(value, str):
        m = _URL_RE.search(value)
        if m:
            return m.group(0).rstrip(").,;，。")
        return ""
    if isinstance(value, dict):
        for key in _URL_KEYS:
            found = _first_http_url(value.get(key))
            if found:
                return found
        for item in value.values():
            found = _first_http_url(item)
            if found:
                return found
    return ""


def resolve_e2e_url(params: Dict[str, Any]) -> str:
    """URL from an explicit field, the task text, or any other param string.

    Pipeline handlers receive artifact keys, not always ``url``. Spec text is
    scanned last so a sample URL inside code does not beat the user task.
    """
    for key in _URL_KEYS:
        found = _first_http_url(params.get(key))
        if found:
            return found
    for key in _PROMPT_KEYS:
        found = _first_http_url(params.get(key))
        if found:
            return found
    for key, value in params.items():
        if key in ("code", "markdown", "output", "text"):
            continue
        found = _first_http_url(value)
        if found:
            return found
    for key in ("text", "markdown", "code", "output"):
        found = _first_http_url(params.get(key))
        if found:
            return found
    return ""


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handler entry.

    Modes via ``action`` / ``mode``:
      - validate / recon / heal / run — see SKILL.md
      - flow: multi-step recon (goto/login/click/fill/expect_url) → one Playwright flow spec
      - auto (default): flow when steps present, else single-page recon scaffold
    """
    if not isinstance(params, dict):
        params = {}
    action = str(params.get("action") or params.get("mode") or "auto").strip().lower()
    url = resolve_e2e_url(params)
    text = str(
        params.get("code")
        or params.get("markdown")
        or params.get("output")
        or params.get("text")
        or ""
    )
    workdir = str(params.get("workdir") or params.get("cwd") or params.get("project_dir") or "")
    run_tests = bool(params.get("run_tests") or params.get("run") or action == "run")
    write_files = bool(params.get("write_files", True))
    max_items = int(params.get("max_items") or 40)
    flow_steps = parse_flow(params)
    use_flow = action == "flow" or (
        action == "auto"
        and len(flow_steps) > 0
        and any(str(s.get("action")) in ("login", "click", "fill") for s in flow_steps)
    )

    if action == "heal":
        elements = list(params.get("elements") or [])
        new_expr = str(params.get("new") or params.get("new_locator") or "").strip()
        old_expr = str(params.get("old") or params.get("old_locator") or "").strip()
        basis = str(params.get("basis") or "list_elements snapshot matches new locator")
        grounded = locator_change_grounded(new_expr, elements)
        if grounded:
            return {"error": grounded, "refused_rebind": True}
        receipt = (
            f"## 定位变更回执\n- 文件: {params.get('file') or 'tests/page.spec.ts'}\n"
            f"- 旧: {old_expr or '(未提供)'}\n"
            f"- 新: {new_expr}\n"
            f"- 依据: {basis}\n"
            f"- 截图: 本轮 list_elements 已执行\n"
        )
        body = (
            f"{receipt}\n"
            f"## 侦察 list_elements\n"
            f"- elements_found: {len(elements)}\n"
            f"import {{ test, expect }} from '@playwright/test';\n"
            f"{new_expr}\n"
        )
        reason = validate_e2e_deliverable(body, require_recon=True)
        if reason:
            return {"error": reason, "refused_rebind": True, "markdown": body}
        return {"result": "ok", "markdown": body, "receipt": receipt}

    if action == "validate":
        report = validate_report(text or "(empty)", require_recon=bool(params.get("require_recon", True)))
        if not report.get("ok"):
            return {"error": report.get("error"), "markdown": text}
        return {"result": "ok", "markdown": text}

    if action == "recon":
        if not url:
            return {"error": "recon requires url", "markdown": ""}
        try:
            recon = await _recon(url, max_items=max_items)
        except Exception as e:
            return {"error": f"recon failed: {e}", "markdown": ""}
        md = _recon_markdown(recon)
        return {"result": "ok", "markdown": md, "recon": recon, "__e2e_recon__": True}

    if action == "run":
        if not workdir:
            return {"error": "run requires workdir/cwd", "markdown": ""}
        ran = _run_playwright(workdir, timeout_s=int(params.get("timeout_s") or 180))
        if not ran.get("ok"):
            return {
                "error": ran.get("error") or "playwright failed",
                "markdown": ran.get("output") or "",
            }
        return {"result": "ok", "markdown": ran.get("output") or "playwright ok", "run": ran}

    if use_flow or action == "flow":
        if not flow_steps:
            return {
                "error": "flow requires steps (flow/steps) or a task with URL + actions",
                "markdown": "",
            }
        if not any(str(s.get("url") or "") for s in flow_steps) and not any(
            str(s.get("action")) == "goto" for s in flow_steps
        ):
            if url:
                flow_steps = [{"id": "step_0", "action": "goto", "url": url}, *flow_steps]
            else:
                return {"error": "flow requires at least one goto url", "markdown": ""}
        try:
            live = await _run_flow_live(flow_steps, max_items=max_items)
        except Exception as e:
            return {"error": f"flow failed: {e}", "markdown": "", "steps": flow_steps}
        if live.get("error"):
            return {
                "error": live.get("error"),
                "refused_rebind": live.get("refused_rebind"),
                "markdown": str(live.get("error")),
                "steps": flow_steps,
                "recon_by_step": live.get("recon_by_step") or {},
            }
        spec = str(live.get("spec") or "")
        recon_by_step = live.get("recon_by_step") or {}
        if "MISSING_SNAPSHOT_TARGET" in spec:
            return {
                "error": "flow click/fill target not in list_elements — refuse inventing locator",
                "refused_rebind": True,
                "markdown": spec,
                "steps": flow_steps,
                "recon_by_step": recon_by_step,
            }
        parts = ["## 业务流程侦察"]
        for step in flow_steps:
            sid = str(step.get("id") or "")
            snap = recon_by_step.get(sid) or {}
            parts.append(f"### {sid} `{step.get('action')}`")
            parts.append(_recon_markdown(snap) if snap else "")
        parts.append(f"## FILE: tests/{_slug_from_url(url or 'flow')}_flow.spec.ts")
        parts.append(spec)
        markdown = "\n".join(parts)
        written: List[str] = []
        if write_files and workdir:
            root = Path(workdir).expanduser().resolve()
            tests_dir = root / "tests"
            tests_dir.mkdir(parents=True, exist_ok=True)
            flow_path = tests_dir / f"{_slug_from_url(url or 'flow')}_flow.spec.ts"
            flow_path.write_text(spec, encoding="utf-8")
            written.append(str(flow_path))
            cfg = root / "playwright.config.ts"
            if not cfg.is_file():
                cfg.write_text(
                    "import { defineConfig } from '@playwright/test';\n"
                    "export default defineConfig({ testDir: './tests', timeout: 30000 });\n",
                    encoding="utf-8",
                )
                written.append(str(cfg))
        reason = validate_e2e_deliverable(markdown, require_recon=True)
        if reason:
            return {"error": reason, "markdown": markdown, "written": written, "steps": flow_steps}
        run_meta = None
        summary = "skipped"
        if run_tests and workdir:
            run_meta = _run_playwright(workdir, timeout_s=int(params.get("timeout_s") or 180))
            summary = "ok" if run_meta.get("ok") else "failed"
            if not run_meta.get("ok"):
                return {
                    "error": run_meta.get("error") or "playwright failed",
                    "markdown": markdown + "\n\n## Playwright 结果\n" + str(run_meta.get("output") or ""),
                    "written": written,
                    "steps": flow_steps,
                    "run": run_meta,
                }
        files = ", ".join(written) if written else "(未落盘 — 见 ## FILE)"
        markdown = (
            f"E2E Flow 生成完成\n- 步骤: {len(flow_steps)}\n"
            f"- 测试文件: {files}\n"
            f"- 侦察: 每步 list_elements\n- 定位变更回执: 无\n- 跑测: {summary}\n\n"
            + markdown
        )
        return {
            "result": "ok",
            "markdown": markdown,
            "written": written,
            "steps": flow_steps,
            "recon_by_step": recon_by_step,
            "run": run_meta,
            "__e2e_recon__": True,
        }

    # single-page recon scaffold (auto default)
    if not url and not text:
        return {
            "error": "e2e_test requires url (recon/scaffold) and/or code/markdown (validate)",
            "markdown": "",
        }
    if text and not url:
        report = validate_report(text, require_recon=True)
        if not report.get("ok"):
            return {"error": report.get("error"), "markdown": text}
        return {"result": "ok", "markdown": text}

    try:
        recon = await _recon(url, max_items=max_items)
    except Exception as e:
        return {"error": f"recon failed: {e}", "markdown": ""}
    elements = list(recon.get("elements") or [])
    spec = scaffold_spec_from_recon(url, elements)
    md_recon = _recon_markdown(recon)
    markdown = f"{md_recon}\n\n## FILE: tests/{_slug_from_url(url)}.spec.ts\n{spec}"
    written = []
    if write_files and workdir:
        path = _write_spec(Path(workdir).expanduser().resolve(), url, spec)
        written.append(str(path))
    reason = validate_e2e_deliverable(markdown, require_recon=True)
    if reason:
        return {"error": reason, "markdown": markdown, "recon": recon, "written": written}
    run_meta = None
    summary = "skipped"
    if run_tests and workdir:
        run_meta = _run_playwright(workdir, timeout_s=int(params.get("timeout_s") or 180))
        summary = "ok" if run_meta.get("ok") else "failed"
        if not run_meta.get("ok"):
            return {
                "error": run_meta.get("error") or "playwright failed",
                "markdown": markdown[:4000] + "\n\n## Playwright 结果\n" + str(run_meta.get("output") or ""),
                "recon": recon,
                "written": written,
                "run": run_meta,
            }
    n = recon.get("elements_found") or len(elements)
    files = ", ".join(written) if written else f"tests/{_slug_from_url(url)}.spec.ts"
    markdown = (
        f"E2E Test Suite 生成完成\n- 测试文件: {files}\n"
        f"- 侦察: 已 list_elements（n={n}）\n- 定位变更回执: 无\n- 跑测: {summary}\n\n"
        + markdown
    )
    return {
        "result": "ok",
        "markdown": markdown,
        "recon": recon,
        "written": written,
        "run": run_meta,
        "__e2e_recon__": True,
    }


def _recon_markdown(recon: Dict[str, Any]) -> str:
    els = recon.get("elements") or []
    lines = [
        "## 侦察 list_elements",
        f"- url: {recon.get('url') or ''}",
        f"- elements_found: {recon.get('elements_found', len(els))}",
        "- __e2e_recon__: true",
        "",
    ]
    for e in els[:40]:
        if not isinstance(e, dict):
            continue
        bits = [f"[{e.get('index')}] {e.get('tag') or ''}"]
        bits.append(f"role={e.get('role') or '-'}")
        if e.get("visible_text"):
            bits.append(f"text={e.get('visible_text')}")
        if e.get("aria_label"):
            bits.append(f"aria={e.get('aria_label')}")
        if e.get("testid"):
            bits.append(f"testid={e.get('testid')}")
        lines.append("- " + " ".join(str(b) for b in bits))
    return "\n".join(lines)
