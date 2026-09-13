#!/usr/bin/env python3
"""存量 AGENT.md / SKILL.md conformance 修复（本地 AIPLAT_HOME/apps）。

修复策略（最小改动）：
  1. 去掉 ```markdown / ```yaml 围栏与残留语言行（markdown/yaml/json）
  2. Skill：旧 input:/output: 列表 → input_schema:/output_schema:
  3. Skill：补齐 version/status/triggers/effects/completion_criterion
  4. Skill：把缺失的 trigger 短语追加进 description（路由命中一致）
  5. Agent：补 ## SOP / ## 反模式（若缺失）

用法：
  python3 scripts/repair_factory_conformance.py --dry-run
  python3 scripts/repair_factory_conformance.py --apply
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _load_gc():
    path = _repo_root() / "aiPlat-platform" / "builder" / "generated_conformance.py"
    spec = importlib.util.spec_from_file_location("gc_repair", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strip_fences(text: str) -> Tuple[str, List[str]]:
    actions: List[str] = []
    t = text.replace("\r\n", "\n")
    # Full fenced block
    m = re.match(r"^```(?:markdown|yaml|yml|json)?\s*\n([\s\S]*?)\n```\s*$", t.strip())
    if m:
        t = m.group(1)
        actions.append("unwrap_fence")
    # Leading language tag residue (``` stripped but language left)
    while True:
        first = t.split("\n", 1)[0].strip().lower()
        if first in ("markdown", "yaml", "yml", "json", "```", "```markdown", "```yaml", "```json"):
            t = t.split("\n", 1)[1] if "\n" in t else ""
            actions.append(f"drop_leading:{first}")
            continue
        if t.startswith("```"):
            # drop opening fence line
            t = t.split("\n", 1)[1] if "\n" in t else ""
            actions.append("drop_opening_fence")
            continue
        break
    # Trailing fence
    stripped = t.rstrip()
    if stripped.endswith("```"):
        t = stripped[: -3].rstrip() + "\n"
        actions.append("drop_trailing_fence")
    # Leading blank lines before ---
    if not t.lstrip().startswith("---") and "\n---\n" in t:
        # keep as-is; strip leading blanks only
        t2 = t.lstrip("\n")
        if t2 != t:
            t = t2
            actions.append("lstrip_newlines")
    elif t.startswith("\n"):
        t = t.lstrip("\n")
        actions.append("lstrip_newlines")
    return t, actions


def _flatten_broken_description_lists(raw: str) -> str:
    """Collapse illegal nested '- key: val' under description into a single line.

    LLM-generated SKILL.md often embeds bullet lists inside unquoted description,
    which breaks YAML. Convert those continuation lines into '; key=val' text.
    """
    lines = raw.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)description:\s*(.*)$", line)
        if not m:
            out.append(line)
            i += 1
            continue
        indent, rest = m.group(1), m.group(2)
        # Collect following deeper-indented bullet lines that look like nested maps
        bits = [rest] if rest.strip() else []
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                break
            # nested under description (more spaces) starting with "- "
            if len(nxt) - len(nxt.lstrip(" ")) > len(indent) and nxt.lstrip().startswith("- "):
                bits.append(nxt.strip().lstrip("- ").strip())
                j += 1
                continue
            break
        flat = "；".join(b for b in bits if b)
        # Quote to keep ':' safe
        out.append(f'{indent}description: "{flat.replace(chr(34), chr(39))}"')
        i = j
    return "\n".join(out)


def _rebuild_skill_from_text(text: str, body: str) -> Dict[str, Any]:
    """Last-resort: extract name/description/execution_type via regex."""
    name_m = re.search(r"(?m)^name:\s*(\S+)\s*$", text)
    desc_m = re.search(r"(?m)^description:\s*(.+)$", text)
    exec_m = re.search(r"(?m)^execution_type:\s*(\S+)\s*$", text)
    name = name_m.group(1) if name_m else "skill"
    desc = (desc_m.group(1).strip().strip('"').strip("'") if desc_m else name)
    return {
        "name": name,
        "description": desc,
        "execution_type": (exec_m.group(1) if exec_m else "prompt"),
    }


def _split_fm(text: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
    """Return (raw_fm_block, parsed_dict, body)."""
    if not text.startswith("---"):
        return None, None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, None, text
    raw = text[3:end]
    body = text[end + 4 :]  # after \n---
    if body.startswith("\n"):
        body = body[1:]
    parsed: Optional[Dict[str, Any]] = None
    if yaml is not None:
        for candidate in (raw, _flatten_broken_description_lists(raw)):
            try:
                obj = yaml.safe_load(candidate)
                if isinstance(obj, dict):
                    parsed = obj
                    break
            except Exception:
                continue
    return raw, parsed, body


def _dump_fm(data: Dict[str, Any]) -> str:
    if yaml is None:
        raise RuntimeError("PyYAML required for repair_factory_conformance")
    dumped = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    return f"---\n{dumped}\n---\n"


def _list_io_to_schema(items: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        entry: Dict[str, Any] = {
            "type": it.get("type") or "string",
            "required": bool(it.get("required", False)),
            "description": it.get("description") or name,
        }
        out[name] = entry
    return out


def _ensure_skill_fields(data: Dict[str, Any], actions: List[str]) -> None:
    name = str(data.get("name") or "skill")
    # migrate input/output lists
    if "input_schema" not in data and "input" in data:
        data["input_schema"] = _list_io_to_schema(data.pop("input"))
        actions.append("migrate_input_to_input_schema")
    if "output_schema" not in data and "output" in data:
        data["output_schema"] = _list_io_to_schema(data.pop("output"))
        actions.append("migrate_output_to_output_schema")

    if not isinstance(data.get("input_schema"), dict) or not data["input_schema"]:
        data["input_schema"] = {
            "query": {
                "type": "string",
                "required": True,
                "description": "用户请求或任务描述",
            }
        }
        actions.append("default_input_schema")
    else:
        # ensure each field has type/required/description substrings
        for k, v in list(data["input_schema"].items()):
            if not isinstance(v, dict):
                data["input_schema"][k] = {
                    "type": "string",
                    "required": False,
                    "description": str(v),
                }
                actions.append(f"normalize_input_schema:{k}")
                continue
            v.setdefault("type", "string")
            v.setdefault("required", False)
            v.setdefault("description", k)

    if not isinstance(data.get("output_schema"), dict) or not data["output_schema"]:
        data["output_schema"] = {
            "result": {
                "type": "object",
                "required": True,
                "description": "技能执行结果",
            }
        }
        actions.append("default_output_schema")
    else:
        for k, v in list(data["output_schema"].items()):
            if not isinstance(v, dict):
                data["output_schema"][k] = {
                    "type": "string",
                    "required": False,
                    "description": str(v),
                }
                actions.append(f"normalize_output_schema:{k}")
                continue
            v.setdefault("type", "string")
            v.setdefault("required", False)
            v.setdefault("description", k)

    if "version:" not in str(data.get("version", "")) and not data.get("version"):
        data["version"] = "1.0.0"
        actions.append("default_version")
    if data.get("status") != "enabled":
        data["status"] = "enabled"
        actions.append("default_status")

    if not isinstance(data.get("triggers"), list) or not data["triggers"]:
        data["triggers"] = [name.replace("_", " "), f"执行{name}"]
        actions.append("default_triggers")

    if not data.get("effects"):
        data["effects"] = [
            {
                "type": "read",
                "resources": ["filesystem:~/.aiplat/apps"],
                "idempotent": True,
                "rollback_available": False,
            }
        ]
        actions.append("default_effects")

    if not data.get("completion_criterion"):
        data["completion_criterion"] = (
            f"- {name} 产出符合 output_schema\n"
            "- 失败时返回可读错误且不中断会话"
        )
        actions.append("default_completion_criterion")

    # description + triggers consistency
    desc = data.get("description")
    if not isinstance(desc, str) or not desc.strip():
        desc = f"{name} 技能"
        data["description"] = desc
        actions.append("default_description")
    missing = [t for t in data["triggers"] if isinstance(t, str) and t not in desc]
    if missing:
        # Keep description readable: append trigger phrases once
        suffix = "；触发：" + "、".join(missing)
        data["description"] = desc.rstrip() + suffix
        actions.append(f"append_triggers_to_description:{len(missing)}")


def _ensure_agent_body(body: str, actions: List[str]) -> str:
    b = body or ""
    if "## SOP" not in b:
        b = b.rstrip() + "\n\n## SOP\n\n1. 接收任务并选择技能\n2. 执行并校验输出\n3. 返回结果或可读错误\n"
        actions.append("add_sop_section")
    if "## 反模式" not in b:
        b = b.rstrip() + "\n\n## 反模式\n\n- 跳过输入校验直接调用下游\n- 无失败归因地吞掉错误\n"
        actions.append("add_antipattern_section")
    return b


def repair_one(path: Path, kind: str, *, apply: bool, validate) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    before = validate(str(path), kind)
    text, actions = _strip_fences(raw)

    fm_raw, data, body = _split_fm(text)
    if kind == "skill":
        if data is None:
            # Cannot parse — leave fence-stripped text only
            new_text = text if text.startswith("---") else f"---\nname: unknown\n---\n{text}"
            actions.append("unparsed_skill_passthrough")
        else:
            _ensure_skill_fields(data, actions)
            new_text = _dump_fm(data) + (body or "")
            if not body.strip():
                new_text = new_text.rstrip() + "\n\n## 执行要点\n\n按 input_schema 执行并返回 output_schema。\n"
                actions.append("add_minimal_skill_body")
    else:
        if data is None:
            new_text = text if text.startswith("---") else f"---\nname: unknown\n---\n{text}"
            actions.append("unparsed_agent_passthrough")
        else:
            # agent required display_name / agent_type already usually present
            if not data.get("display_name"):
                data["display_name"] = str(data.get("name") or path.parent.name)
                actions.append("default_display_name")
            if not data.get("agent_type"):
                data["agent_type"] = "react"
                actions.append("default_agent_type")
            body2 = _ensure_agent_body(body, actions)
            new_text = _dump_fm(data) + body2

    changed = new_text != raw
    # Validate repaired text in-memory
    after = validate.__self__.validate_text(new_text, kind) if hasattr(validate, "__self__") else None
    # validate_file always reads disk — use validate_text from module
    return {
        "path": str(path),
        "kind": kind,
        "actions": actions,
        "changed": changed,
        "violations_before": before,
        "text": new_text,
        "raw": raw,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair factory AGENT.md/SKILL.md conformance")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--apps-root", default="", help="Override apps root")
    args = ap.parse_args()

    if yaml is None:
        print("ERROR: PyYAML required")
        return 2

    apps_root = Path(args.apps_root) if args.apps_root else (_aiplat_home() / "apps")
    gc = _load_gc()
    validate_file = gc.validate_file
    validate_text = gc.validate_text

    rows: List[Dict[str, Any]] = []
    for path in sorted(apps_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "AGENT.md":
            kind = "agent"
        elif path.name == "SKILL.md":
            kind = "skill"
        else:
            continue
        before = validate_file(str(path), kind)
        if not before:
            continue  # already green — skip

        raw = path.read_text(encoding="utf-8")
        text, actions = _strip_fences(raw)
        _fm, data, body = _split_fm(text)

        if kind == "skill":
            if data is None:
                data = _rebuild_skill_from_text(text, body)
                actions.append("rebuild_skill_from_regex")
            _ensure_skill_fields(data, actions)
            new_text = _dump_fm(data) + (body or "")
            if not (body or "").strip():
                new_text += "\n## 执行要点\n\n按 input_schema 执行并返回 output_schema。\n"
                actions.append("add_minimal_skill_body")
        else:
            if data is None:
                # agent: try flatten then rebuild minimal
                name_m = re.search(r"(?m)^name:\s*(\S+)\s*$", text)
                data = {
                    "name": name_m.group(1) if name_m else path.parent.name,
                    "display_name": path.parent.name,
                    "agent_type": "react",
                }
                actions.append("rebuild_agent_minimal")
            if not data.get("display_name"):
                data["display_name"] = str(data.get("name") or path.parent.name)
                actions.append("default_display_name")
            if not data.get("agent_type"):
                data["agent_type"] = "react"
                actions.append("default_agent_type")
            body2 = _ensure_agent_body(body, actions)
            new_text = _dump_fm(data) + body2

        after = validate_text(new_text, kind)
        status = "unchanged"
        if new_text != raw:
            status = "would_write" if not args.apply else "written"
            if args.apply:
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():
                    bak.write_text(raw, encoding="utf-8")
                path.write_text(new_text, encoding="utf-8")

        rows.append({
            "path": str(path),
            "kind": kind,
            "status": status,
            "actions": actions,
            "before_n": len(before),
            "after_n": len(after),
            "ok_after": len(after) == 0,
            "after": after[:3],
        })

    written = sum(1 for r in rows if r["status"] == "written")
    would = sum(1 for r in rows if r["status"] == "would_write")
    ok = sum(1 for r in rows if r["ok_after"])
    print("=== repair_factory_conformance ===")
    print(f"apps_root={apps_root}")
    print(f"failed_in={len(rows)} written={written} would_write={would} ok_after={ok}")
    for r in rows:
        print("---")
        print(r["path"])
        print(f"  status={r['status']} kind={r['kind']} before={r['before_n']} after={r['after_n']} ok={r['ok_after']}")
        print(f"  actions={r['actions'][:8]}")
        if r["after"]:
            print(f"  remaining={r['after']}")

    if args.apply:
        remaining = [r for r in rows if not r["ok_after"]]
        return 1 if remaining else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
