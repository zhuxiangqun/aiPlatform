"""Config-driven multi-step E2E flow (business path without vision).

Step kinds are generic: goto / login / click / fill / expect_url / recon.
No product role names or artifact keys — callers supply the graph.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_ARROW_SPLIT = re.compile(r"\s*(?:→|->|=>|然后|再|接着)\s*")
_ALLOWED = frozenset({"goto", "login", "click", "fill", "expect_url", "recon"})


def normalize_step(raw: Any, *, index: int = 1) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action") or raw.get("type") or raw.get("kind") or "").strip().lower()
    if not action:
        if raw.get("url"):
            action = "goto"
        elif raw.get("target") or raw.get("name") or raw.get("text"):
            action = "click"
    if action not in _ALLOWED:
        return None
    step: Dict[str, Any] = {
        "id": str(raw.get("id") or f"step_{index}"),
        "action": action,
    }
    for key in (
        "url",
        "path",
        "target",
        "name",
        "text",
        "role",
        "value",
        "username",
        "password",
        "expect_url",
        "expect",
    ):
        val = raw.get(key)
        if val not in (None, ""):
            step[key] = val
    return step


def parse_flow(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build ordered steps from ``flow`` / ``steps`` / task text heuristics."""
    raw = None
    for key in ("flow", "steps", "e2e_flow"):
        if isinstance(params.get(key), (list, dict, str)):
            raw = params.get(key)
            break
    out: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for i, item in enumerate(raw, start=1):
            step = normalize_step(item, index=i)
            if step:
                out.append(step)
        if out:
            return out
    if isinstance(raw, dict) and "steps" in raw:
        return parse_flow({"steps": raw.get("steps")})

    text = " ".join(
        str(params.get(k) or "")
        for k in ("prompt", "input", "task", "user_task", "query", "instruction")
    )
    if isinstance(raw, str) and raw.strip():
        text = f"{raw} {text}".strip()

    urls = [_clean_url(m.group(0)) for m in _URL_RE.finditer(text)]
    urls = [u for u in urls if u]
    base = str(params.get("url") or params.get("base_url") or (urls[0] if urls else "")).strip()
    steps: List[Dict[str, Any]] = []
    if base:
        steps.append({"id": "step_1", "action": "goto", "url": base})

    user = str(params.get("username") or params.get("user") or "").strip()
    password = str(params.get("password") or params.get("pass") or "").strip()
    accounts = params.get("accounts")
    if isinstance(accounts, dict):
        user = user or str(accounts.get("username") or "").strip()
        password = password or str(accounts.get("password") or "").strip()

    if user or password or re.search(r"登录|登陆|login|sign\s*in", text, re.I):
        login_url = str(params.get("login_url") or "").strip()
        if login_url and "://" not in login_url and base:
            login_url = urljoin(base if "://" in base else f"https://{base}", login_url)
        step: Dict[str, Any] = {
            "id": f"step_{len(steps) + 1}",
            "action": "login",
            "username": user,
            "password": password,
        }
        if login_url:
            step["url"] = login_url
        extra = (login_url or "").rstrip("/")
        if not (base and extra and extra == base.rstrip("/")):
            if login_url and (not base or login_url.rstrip("/") != base.rstrip("/")):
                steps.append({"id": f"step_{len(steps) + 1}", "action": "goto", "url": login_url})
                step["id"] = f"step_{len(steps) + 1}"
        steps.append(step)

    for chunk in _ARROW_SPLIT.split(text):
        chunk = _URL_RE.sub(" ", chunk).strip()
        if not chunk or re.fullmatch(r"(?:登录|登陆|login|sign\s*in)(?:后|了)?", chunk, re.I):
            continue
        for m in re.finditer(
            r"(?:点击|单击|进入|选择)\s*[「\"'【\[]?([^」\"'】\]\s，。；;]{1,40})",
            chunk,
        ):
            target = m.group(1).strip().strip("「」\"'")
            if not target or re.search(r"登录|登陆|login|密码|password", target, re.I):
                continue
            steps.append(
                {
                    "id": f"step_{len(steps) + 1}",
                    "action": "click",
                    "target": target,
                    "name": target,
                }
            )
    return steps


def _clean_url(url: str) -> str:
    return str(url or "").strip().rstrip(").,;，。")


def _locator_line(el: Dict[str, Any], verb: str = "expect") -> Optional[str]:
    testid = str(el.get("testid") or "").strip()
    role = str(el.get("role") or "").strip()
    tag = str(el.get("tag") or "").strip().lower()
    name = ""
    for key in ("visible_text", "aria_label", "name", "placeholder"):
        name = str(el.get(key) or "").strip()
        if name:
            break
    pw_role = role
    if role == "submit_button":
        pw_role = "button"
    elif tag == "a":
        pw_role = "link"
    elif tag == "button":
        pw_role = "button"
    if "textbox" in role or role in ("text_input", "search_input"):
        pw_role = "textbox"

    if verb == "expect":
        if testid:
            return f"  await expect(page.getByTestId({testid!r})).toBeVisible();"
        if pw_role and name:
            return f"  await expect(page.getByRole({pw_role!r}, {{ name: {name!r} }})).toBeVisible();"
        if pw_role == "textbox" and name:
            return f"  await expect(page.getByRole('textbox', {{ name: {name!r} }})).toBeVisible();"
        return None
    if verb == "click":
        if testid:
            return f"  await page.getByTestId({testid!r}).click();"
        if pw_role and name:
            return f"  await page.getByRole({pw_role!r}, {{ name: {name!r} }}).click();"
        return None
    if verb == "fill":
        value = str(el.get("_fill_value") or "")
        if testid:
            return f"  await page.getByTestId({testid!r}).fill({value!r});"
        if pw_role and name:
            return f"  await page.getByRole({pw_role!r}, {{ name: {name!r} }}).fill({value!r});"
        if name:
            return f"  await page.getByRole('textbox', {{ name: {name!r} }}).fill({value!r});"
        return None
    return None


def find_element(
    elements: List[Dict[str, Any]],
    *,
    target: str = "",
    role: str = "",
    password: bool = False,
) -> Optional[Dict[str, Any]]:
    rows = [e for e in (elements or []) if isinstance(e, dict)]
    want = str(target or "").casefold()
    want_role = str(role or "").casefold()

    if password:
        for e in rows:
            if str(e.get("type") or "").lower() == "password":
                return e
        for e in rows:
            blob = " ".join(
                str(e.get(k) or "")
                for k in ("name", "placeholder", "aria_label", "visible_text")
            ).casefold()
            if "password" in blob or "密码" in blob:
                return e
        return None

    def _blob(e: Dict[str, Any]) -> str:
        return " ".join(
            str(e.get(k) or "")
            for k in ("visible_text", "aria_label", "name", "testid", "placeholder")
        ).casefold()

    def _role_match(e: Dict[str, Any], want_r: str) -> bool:
        er = str(e.get("role") or "").casefold()
        if want_r == "button":
            return er in ("button", "submit_button")
        if want_r == "text_input":
            return er in ("text_input", "search_input")
        return er == want_r

    if want_role:
        for e in rows:
            if str(e.get("type") or "").lower() == "password" and not password:
                continue
            if not _role_match(e, want_role):
                continue
            if want and want not in _blob(e):
                continue
            return e

    if want:
        for e in rows:
            if str(e.get("type") or "").lower() == "password" and not password:
                continue
            if want in _blob(e):
                return e
    return None


def login_controls(elements: List[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Username, password, and submit taken from one list_elements snapshot."""
    user = find_element(elements, role="text_input")
    password = find_element(elements, password=True)
    submit = (
        find_element(elements, role="submit_button")
        or find_element(elements, target="登录", role="button")
        or find_element(elements, target="login", role="button")
        or find_element(elements, target="sign in", role="button")
    )
    return {"user": user, "password": password, "submit": submit}


def semantic_hook(el: Optional[Dict[str, Any]]) -> str:
    """testid or accessible name required before a control can be written into a spec."""
    if not isinstance(el, dict):
        return ""
    for key in ("testid", "visible_text", "aria_label", "name", "placeholder"):
        value = str(el.get(key) or "").strip()
        if value:
            return value
    return ""


def login_gap(step: Dict[str, Any], elements: List[Dict[str, Any]]) -> Optional[str]:
    """Why this login step cannot be grounded. None when the snapshot is enough."""
    needs_user = bool(str(step.get("username") or "").strip())
    needs_pass = bool(str(step.get("password") or "").strip())
    if not needs_user and not needs_pass:
        return "login step missing username/password"
    controls = login_controls(elements)
    missing: List[str] = []
    if needs_user and not controls.get("user"):
        missing.append("username field")
    if needs_user and not semantic_hook(controls.get("user")):
        missing.append("username semantic name")
    if needs_pass and not controls.get("password"):
        missing.append("password field")
    if needs_pass and not semantic_hook(controls.get("password")):
        missing.append("password semantic name")
    if (needs_user or needs_pass) and not controls.get("submit"):
        missing.append("submit")
    if (needs_user or needs_pass) and not semantic_hook(controls.get("submit")):
        missing.append("submit semantic name")
    if missing:
        return "login controls not in list_elements: " + ", ".join(missing)
    return None


def scaffold_flow_spec(
    steps: List[Dict[str, Any]],
    recon_by_step: Dict[str, Dict[str, Any]],
    title: str = "e2e business flow",
) -> str:
    """Emit one Playwright test chaining semantic actions from per-step recon."""
    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"// flow recon steps={len(steps)}",
        f"test({title!r}, async ({{ page }}) => {{",
    ]
    if not steps:
        lines.append("  // empty flow")
        lines.append("});")
        lines.append("")
        return "\n".join(lines)

    for step in steps:
        sid = str(step.get("id") or "")
        action = str(step.get("action") or "")
        recon = recon_by_step.get(sid) or {}
        elements = list(recon.get("action_elements") or recon.get("elements") or [])
        page_url = str(recon.get("url_before") or recon.get("url") or step.get("url") or "")
        lines.append(f"  // {sid} {action} list_elements n={len(elements)}")

        if action == "goto":
            url = str(step.get("url") or page_url or "")
            lines.append(f"  await page.goto({url!r});")
            el = elements[0] if elements else None
            if isinstance(el, dict):
                line = _locator_line(el, "expect")
                if line:
                    lines.append(line)
            continue

        if action == "login":
            if step.get("url") and str(step.get("url")) != page_url:
                lines.append(f"  await page.goto({str(step.get('url'))!r});")
            gap = login_gap(step, elements)
            if gap:
                lines.append(f"  // MISSING_SNAPSHOT_TARGET {gap}")
                continue
            controls = login_controls(elements)
            user_el = controls.get("user")
            pass_el = controls.get("password")
            submit = controls.get("submit")
            if user_el:
                filled = dict(user_el)
                filled["_fill_value"] = str(step.get("username") or "")
                line = _locator_line(filled, "fill")
                if line:
                    lines.append(line)
            if pass_el:
                filled = dict(pass_el)
                filled["_fill_value"] = str(step.get("password") or "")
                line = _locator_line(filled, "fill")
                if line:
                    lines.append(line)
            if submit:
                line = _locator_line(submit, "click")
                if line:
                    lines.append(line)
            continue

        if action == "click":
            target = str(step.get("target") or step.get("name") or step.get("text") or "")
            role = str(step.get("role") or "")
            el = find_element(elements, target=target, role=role)
            if el and semantic_hook(el):
                line = _locator_line(el, "click")
                if line:
                    lines.append(line)
                    continue
            if el and not semantic_hook(el):
                lines.append(f"  // MISSING_SNAPSHOT_TARGET {target} semantic name")
            else:
                lines.append(f"  // MISSING_SNAPSHOT_TARGET {target} click")
            continue

        if action == "fill":
            target = str(step.get("target") or step.get("name") or "")
            role = str(step.get("role") or "text_input")
            el = find_element(elements, target=target, role=role)
            if el and semantic_hook(el):
                filled = dict(el)
                filled["_fill_value"] = str(step.get("value") or "")
                line = _locator_line(filled, "fill")
                if line:
                    lines.append(line)
                    continue
            if el and not semantic_hook(el):
                lines.append(f"  // MISSING_SNAPSHOT_TARGET {target} semantic name")
            else:
                lines.append(f"  // MISSING_SNAPSHOT_TARGET {target} fill")
            continue

        if action == "expect_url":
            frag = str(step.get("expect_url") or step.get("expect") or "")
            if frag:
                lines.append(f"  await expect(page).toHaveURL(/{re.escape(frag)}/);")
            continue

        if action == "recon":
            el = elements[0] if elements else None
            if isinstance(el, dict):
                line = _locator_line(el, "expect")
                if line:
                    lines.append(line)

    lines.append("});")
    lines.append("")
    return "\n".join(lines)
