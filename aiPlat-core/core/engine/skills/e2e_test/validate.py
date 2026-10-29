"""Pure validators for e2e_test deliverables (no Playwright / browser IO)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_FORBIDDEN = (
    (re.compile(r"waitForTimeout\s*\(", re.I), "forbidden waitForTimeout"),
    (re.compile(r"page\.waitForTimeout\s*\(", re.I), "forbidden page.waitForTimeout"),
    (re.compile(r"\bxpath\s*[:=]", re.I), "forbidden xpath locator"),
    (re.compile(r"page\.\$\s*\(\s*['\"]//", re.I), "forbidden xpath via page.$"),
    (re.compile(r"locator\s*\(\s*['\"]//", re.I), "forbidden xpath via locator"),
    (
        re.compile(
            r"(?:page\.(?:click|fill|locator)|locator)\s*\(\s*['\"][^'\"]*\.[A-Za-z_][\w-]*",
            re.I,
        ),
        "forbidden CSS class selector in generated locator",
    ),
    (re.compile(r"click_index|type_index", re.I), "click_index/type_index must not appear in specs"),
)

_SEMANTIC = re.compile(
    r"getByRole\s*\(|getByLabel\s*\(|getByText\s*\(|getByTestId\s*\(",
    re.I,
)
_SPEC_HINT = re.compile(r"\.spec\.(ts|js|tsx|jsx)\b|@playwright/test", re.I)
_RECON_HINT = re.compile(
    r"list_elements|侦察|__e2e_recon__|elements_found|visible_text|data-testid",
    re.I,
)
_RECEIPT_HDR = re.compile(r"定位变更回执")
_RECEIPT_FIELDS = ("旧", "新", "依据")


def validate_e2e_deliverable(text: str, *, require_recon: bool = True) -> Optional[str]:
    """Return veto reason, or None when deliverable passes the e2e contract."""
    body = str(text or "").strip()
    if not body:
        return "e2e_test deliverable is empty — recon + spec required before DONE"

    violations: List[str] = []
    for pat, msg in _FORBIDDEN:
        if pat.search(body):
            violations.append(msg)

    looks_like_spec = bool(_SPEC_HINT.search(body)) or (
        "getByRole" in body or "getByTestId" in body
    )
    if looks_like_spec and not _SEMANTIC.search(body):
        violations.append("Playwright output must use getByRole/Label/Text/TestId")

    if require_recon and looks_like_spec and not _RECON_HINT.search(body):
        violations.append("missing list_elements / recon evidence before locators")

    if _RECEIPT_HDR.search(body):
        for field in _RECEIPT_FIELDS:
            if not re.search(f"{field}\\s*[:：]", body):
                violations.append(f"locator-change receipt missing field `{field}`")
    elif re.search(r"自愈|改定位|rebind|locator.?change", body, re.I) and looks_like_spec:
        violations.append("locator changes require ## 定位变更回执 (旧/新/依据)")

    if not violations:
        return None
    return "e2e_test contract: " + "; ".join(violations)


def validate_report(text: str, *, require_recon: bool = True) -> Dict[str, Any]:
    reason = validate_e2e_deliverable(text, require_recon=require_recon)
    return {"ok": reason is None, "error": reason, "require_recon": require_recon}


def locator_change_grounded(
    new_expr: str, elements: List[Dict[str, Any]]
) -> Optional[str]:
    """Refuse a replacement locator that is not in the current list_elements snapshot."""
    expr = str(new_expr or "").strip()
    if not expr:
        return "new locator empty"
    banned = validate_e2e_deliverable(
        "list_elements\nimport { test, expect } from '@playwright/test';\n" + expr,
        require_recon=True,
    )
    if banned and "forbidden" in banned:
        return banned

    rows = [e for e in (elements or []) if isinstance(e, dict)]

    def _blob(e: Dict[str, Any]) -> str:
        return " ".join(
            str(e.get(k) or "")
            for k in ("visible_text", "aria_label", "name", "placeholder", "testid")
        ).casefold()

    tid = re.search(r"getByTestId\s*\(\s*['\"]([^'\"]+)['\"]", expr)
    if tid:
        want = tid.group(1)
        if any(str(e.get("testid") or "") == want for e in rows):
            return None
        return "testid not in list_elements snapshot — refuse rebind"

    role_name = re.search(
        r"getByRole\s*\(\s*['\"]([^'\"]+)['\"][\s\S]*?name\s*:\s*['\"]([^'\"]+)['\"]",
        expr,
    )
    if role_name:
        role = role_name.group(1).casefold()
        name = role_name.group(2).casefold()
        for e in rows:
            erole = str(e.get("role") or "").casefold()
            tag = str(e.get("tag") or "").casefold()
            role_ok = (
                role == erole
                or (role == "button" and erole in ("button", "submit_button"))
                or (role == "link" and (erole == "link" or tag == "a"))
                or (role == "textbox" and erole in ("text_input", "search_input"))
            )
            if role_ok and name and name in _blob(e):
                return None
        return "role/name not in list_elements snapshot — refuse rebind"

    labeled = re.search(r"getBy(?:Label|Text)\s*\(\s*['\"]([^'\"]+)['\"]", expr)
    if labeled:
        name = labeled.group(1).casefold()
        if any(name in _blob(e) for e in rows):
            return None
        return "label/text not in list_elements snapshot — refuse rebind"

    return "new locator is not a snapshot-grounded getByRole/Label/Text/TestId"
