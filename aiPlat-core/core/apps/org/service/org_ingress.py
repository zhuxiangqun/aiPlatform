"""Phase C2 — Feishu/Lark inbound → OrgRun (single channel).

Security: signature, replay window, identity map, idempotency, confirm gate.
Business entry is only ``run_org_goal``. No customer SQL. No second channel.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_FIRST = frozenset({"feishu", "lark"})
_CONFIRM = frozenset({"确认", "confirm", "ok", "yes"})
_CANCEL = frozenset({"取消", "cancel", "no"})
_REPLAY_SEC = 300


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _state_path() -> Path:
    return _home() / "org" / "ingress_state.json"


def _identity_path() -> Path:
    override = _home() / "org" / "channel_identity.json"
    if override.is_file():
        return override
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "org_ingress"
        / "channel_identity.json"
    )


def normalize_channel(channel: str) -> str:
    c = (channel or "").strip().lower()
    if c == "lark":
        return "feishu"
    return c


def ingress_status() -> Dict[str, Any]:
    return {
        "channel": "feishu",
        "aliases": ["lark"],
        "sign_configured": bool((os.getenv("AIPLAT_FEISHU_ENCRYPT_KEY") or "").strip()),
        "verify_token_configured": bool((os.getenv("AIPLAT_FEISHU_VERIFY_TOKEN") or "").strip()),
        "confirm_required": True,
        "second_channel": False,
        "post": post_channel_allowed("feishu"),
        "inbound": [{"id": "feishu", "aliases": ["lark"], "open": True}],
        "outbound_only": [
            {
                "id": "wecom",
                "configured": bool((os.getenv("AIPLAT_WECOM_WEBHOOK") or "").strip()),
            }
        ],
        "authority_note": "C2 single-channel ingress; wecom is outbound only; not M4",
    }


def verify_lark_signature(
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
    *,
    encrypt_key: str,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Feishu: sha256(timestamp + nonce + encrypt_key + body). Replay window 300s."""
    ts_raw = (timestamp or "").strip()
    nonce_s = (nonce or "").strip()
    sig = (signature or "").strip().lower()
    key = (encrypt_key or "").strip()
    if not key:
        return {"ok": False, "reason": "encrypt_key_missing"}
    if not ts_raw or not nonce_s or not sig:
        return {"ok": False, "reason": "missing_signature_headers"}
    try:
        ts = int(ts_raw)
    except ValueError:
        return {"ok": False, "reason": "bad_timestamp"}
    clock = time.time() if now is None else now
    if abs(clock - ts) > _REPLAY_SEC:
        return {"ok": False, "reason": "replay_window"}
    material = (ts_raw + nonce_s + key).encode("utf-8") + (body or b"")
    digest = hashlib.sha256(material).hexdigest()
    if digest != sig:
        return {"ok": False, "reason": "bad_signature"}
    if _nonce_seen(nonce_s, ts):
        return {"ok": False, "reason": "nonce_replay"}
    _remember_nonce(nonce_s, ts)
    return {"ok": True, "reason": "ok"}


def _load_state() -> Dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"nonces": {}, "idempotency": {}, "pending": {}, "sessions": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("ingress state unreadable", exc_info=True)
        return {"nonces": {}, "idempotency": {}, "pending": {}, "sessions": {}}
    for k in ("nonces", "idempotency", "pending", "sessions"):
        if not isinstance(data.get(k), dict):
            data[k] = {}
    return data


def _save_state(data: Dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _nonce_seen(nonce: str, ts: int) -> bool:
    st = _load_state()
    return nonce in (st.get("nonces") or {})


def _remember_nonce(nonce: str, ts: int) -> None:
    st = _load_state()
    nonces = st.setdefault("nonces", {})
    cutoff = int(time.time()) - _REPLAY_SEC
    stale = [k for k, v in nonces.items() if int(v or 0) < cutoff]
    for k in stale:
        nonces.pop(k, None)
    nonces[nonce] = ts
    _save_state(st)


def post_channel_allowed(channel: str) -> Dict[str, Any]:
    """C3: DigitalPost channel + validity gate (C2 callers keep this name)."""
    from core.apps.org.service.org_post import evaluate_post_gate

    return evaluate_post_gate(channel)


def resolve_actor(channel: str, user_id: str) -> Dict[str, Any]:
    ch = normalize_channel(channel)
    uid = (user_id or "").strip()
    path = _identity_path()
    mapping: Dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) or {}
            block = raw.get(ch) if isinstance(raw.get(ch), dict) else {}
            mapping = block if isinstance(block, dict) else {}
        except Exception:
            logger.warning("channel identity load failed", exc_info=True)
    hit = mapping.get(uid) if uid else None
    if not isinstance(hit, dict) or not hit.get("tenant_id") or not hit.get("actor_id"):
        return {
            "ok": False,
            "status": "identity_unmapped",
            "channel": ch,
            "user_id": uid,
        }
    return {
        "ok": True,
        "status": "ok",
        "channel": ch,
        "user_id": uid,
        "tenant_id": str(hit.get("tenant_id")),
        "actor_id": str(hit.get("actor_id")),
    }


def _intent(text: str, action: str) -> str:
    act = (action or "").strip().lower()
    if act in ("confirm", "cancel"):
        return act
    t = (text or "").strip().lower()
    if t in _CANCEL:
        return "cancel"
    if t in _CONFIRM:
        return "confirm"
    return "message"


def build_dispatch_evidence(domain_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
    """C0-shaped evidence: Object/Action/Interface/Skill/PolicyGate on one trace."""
    from core.apps.org.service.org_interface import get_interface_spec

    pack = get_interface_spec(domain_id)
    spec = pack.get("spec") or {}
    steps = run.get("steps") or run.get("plan") or []
    hits = 0
    for s in steps if isinstance(steps, list) else []:
        if isinstance(s, dict) and s.get("step") == "locate":
            hits = int(s.get("hit_count") or 0)
    run_id = str(run.get("run_id") or "")
    return {
        "trace_id": run_id,
        "object": {"source": "locate", "hit_count": hits, "domain_id": domain_id},
        "action": {
            "ids": list(spec.get("bound_action_ids") or [])[:6],
            "executed_via": "org_run_goal",
        },
        "interface": {
            "interface_ref": spec.get("interface_ref"),
            "enabled": bool(spec.get("enabled")),
            "adapter": spec.get("adapter"),
        },
        "skill": {"id": "org_run", "steps": ["locate", "fetch", "triage_gate"]},
        "policy_gate": {
            "hitl": run.get("status") == "needs_hitl" or True,
            "run_status": run.get("status"),
            "dry_actions": True,
        },
    }


def process_channel_message(
    *,
    channel: str,
    message_id: str,
    chat_id: str,
    user_id: str,
    text: str = "",
    action: str = "",
    domain_id: str = "it-ops",
) -> Dict[str, Any]:
    """Verified message → confirm gate → org_run_goal. Idempotent on channel+message_id."""
    ch = normalize_channel(channel)
    if ch not in ("feishu",):
        return _receipt("channel_not_allowed", "仅飞书入站已开放", channel=ch)
    post = post_channel_allowed(ch)
    if not post.get("ok"):
        return _receipt(
            str(post.get("status") or "post_channel_denied"),
            "试点岗位未允许该渠道，已拒绝",
            channel=ch,
            chat_id=chat_id,
            post_id=post.get("post_id"),
        )
    actor = resolve_actor(ch, user_id)
    if not actor.get("ok"):
        return _receipt(
            "identity_unmapped",
            "渠道用户未映射到平台身份，已拒绝",
            channel=ch,
            chat_id=chat_id,
        )

    mid = (message_id or "").strip()
    idem_key = f"{ch}:{mid}" if mid else ""
    st = _load_state()
    if idem_key and idem_key in st["idempotency"]:
        prev = dict(st["idempotency"][idem_key])
        prev["idempotent"] = True
        return prev

    intent = _intent(text, action)
    sess_key = f"{ch}:{chat_id or user_id}"
    if intent == "cancel":
        st["pending"].pop(sess_key, None)
        _save_state(st)
        out = _receipt("cancelled", "已取消，未创建 OrgRun", channel=ch, chat_id=chat_id)
        if idem_key:
            st = _load_state()
            st["idempotency"][idem_key] = out
            _save_state(st)
        return out

    if intent != "confirm":
        st["pending"][sess_key] = {
            "user_id": user_id,
            "text": (text or "")[:500],
            "ts": int(time.time()),
        }
        _save_state(st)
        out = _receipt(
            "needs_confirm",
            "回复「确认」启动组织任务，或「取消」。确认前不会创建 Run。",
            channel=ch,
            chat_id=chat_id,
            card={"actions": ["confirm", "cancel"]},
        )
        if idem_key:
            st = _load_state()
            st["idempotency"][idem_key] = out
            _save_state(st)
        return out

    from core.apps.org.service.org_runtime import run_org_goal

    run = run_org_goal(
        goal_id=str(post.get("org_goal_id") or ""),
        domain_id=str(post.get("domain_id") or domain_id),
        dry_actions=True,
        week_label="ingress",
        usage_channel=ch,
        usage_tenant=str(actor.get("tenant_id") or ""),
        usage_actor=str(actor.get("actor_id") or ""),
    )
    evidence = build_dispatch_evidence(domain_id, run if isinstance(run, dict) else {})
    run_id = str((run or {}).get("run_id") or "")
    st = _load_state()
    st["pending"].pop(sess_key, None)
    if run_id:
        st["sessions"][sess_key] = run_id
    status = "ok" if run_id else str((run or {}).get("status") or "run_failed")
    receipt = (
        f"OrgRun {run_id} → {(run or {}).get('status')}"
        if run_id
        else f"未能创建 Run：{(run or {}).get('status')}"
    )
    out = _receipt(
        status if run_id else "run_failed",
        receipt,
        channel=ch,
        chat_id=chat_id,
        run_id=run_id,
        trace_id=evidence.get("trace_id") or run_id,
        tenant_id=actor.get("tenant_id"),
        actor_id=actor.get("actor_id"),
        post_id=post.get("post_id"),
        dispatch=evidence,
        session_key=sess_key,
    )
    if idem_key:
        st["idempotency"][idem_key] = {k: v for k, v in out.items() if k != "dispatch"}
        st["idempotency"][idem_key]["dispatch"] = evidence
    _save_state(st)
    return out


def ingest_feishu_event(
    payload: Dict[str, Any],
    *,
    headers: Optional[Dict[str, str]] = None,
    raw_body: bytes = b"",
) -> Dict[str, Any]:
    """HTTP entry: URL challenge, signature, then process_channel_message."""
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    body = payload if isinstance(payload, dict) else {}

    if body.get("encrypt"):
        return _receipt(
            "encrypted_payload_unsupported",
            "加密事件体尚未解密；请使用明文回调 + 签名",
            http_status=400,
        )

    if str(body.get("type") or "") == "url_verification" or str(
        (body.get("header") or {}).get("event_type") or ""
    ) == "url_verification":
        token = str(body.get("token") or "")
        expected = (os.getenv("AIPLAT_FEISHU_VERIFY_TOKEN") or "").strip()
        if expected and token != expected:
            return _receipt("bad_verify_token", "验证 token 不匹配", http_status=401)
        return {"status": "ok", "challenge": body.get("challenge") or ""}

    key = (os.getenv("AIPLAT_FEISHU_ENCRYPT_KEY") or "").strip()
    if not key:
        return _receipt(
            "ingress_unconfigured",
            "未配置 AIPLAT_FEISHU_ENCRYPT_KEY，拒绝未签名入站",
            http_status=503,
        )
    checked = verify_lark_signature(
        headers.get("x-lark-request-timestamp", ""),
        headers.get("x-lark-request-nonce", ""),
        raw_body,
        headers.get("x-lark-signature", ""),
        encrypt_key=key,
    )
    if not checked.get("ok"):
        return _receipt(
            str(checked.get("reason") or "bad_signature"),
            "签名或重放校验失败",
            http_status=401,
        )

    event = body.get("event") if isinstance(body.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    action = ""
    text = ""
    if isinstance(event.get("action"), dict):
        action = str((event.get("action") or {}).get("value") or (event.get("action") or {}).get("tag") or "")
    content = message.get("content") or ""
    try:
        parsed = json.loads(content) if isinstance(content, str) and content.startswith("{") else {}
        text = str((parsed or {}).get("text") or content or "")
    except Exception:
        text = str(content or "")
    user_id = str((sender.get("sender_id") or {}).get("open_id") or sender.get("open_id") or "")
    return process_channel_message(
        channel="feishu",
        message_id=str(message.get("message_id") or body.get("uuid") or ""),
        chat_id=str(message.get("chat_id") or ""),
        user_id=user_id,
        text=text,
        action=action,
    )


def _event_allowlist_paths() -> List[Path]:
    seed = Path(__file__).resolve().parents[4] / "workspace_seeds" / "org" / "event_preview.yaml"
    return [seed, _home() / "org" / "event_preview.yaml"]


def load_event_allowlist() -> List[str]:
    """Event types allowed to start a sandbox preview. Not a channel list."""
    found: List[str] = []
    for path in _event_allowlist_paths():
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.warning("event allowlist unreadable: %s", path, exc_info=True)
            continue
        for item in (raw.get("events") or []) if isinstance(raw, dict) else []:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("event_type") or "").strip()
            else:
                name = ""
            if name and name not in found:
                found.append(name)
    return found


def list_event_previews(limit: int = 5) -> Dict[str, Any]:
    root = _home() / "org" / "event_previews"
    items: List[Dict[str, Any]] = []
    if root.is_dir():
        files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[: max(1, min(int(limit or 5), 20))]:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(raw, dict):
                raw["live_started"] = False
                raw["wrote_live_yaml"] = False
                items.append(raw)
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "live_started": False,
        "wrote_live_yaml": False,
        "second_channel": False,
        "m4_claim_allowed": False,
    }


def start_event_preview(
    *,
    role: str,
    domain_id: str,
    event_type: str,
) -> Dict[str, Any]:
    """Whitelist event → one dry OrgRun. No live IO, no channel push."""
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "live_started": False}
    if role_n not in ("admin", "operator"):
        return {"ok": False, "reason": "preview_forbidden", "live_started": False}
    kind = (event_type or "").strip()
    allowed = load_event_allowlist()
    if kind not in allowed:
        return {
            "ok": False,
            "reason": "event_not_allowed",
            "event_type": kind,
            "live_started": False,
            "wrote_live_yaml": False,
        }
    did = (domain_id or "").strip() or "it-ops"
    if len(did) > 64 or "/" in did or "\\" in did:
        return {"ok": False, "reason": "domain_invalid", "live_started": False}

    from core.apps.org.service.org_runtime import run_org_goal

    try:
        run = run_org_goal("", domain_id=did, dry_actions=True, week_label="event_preview")
    except Exception:
        logger.warning("event preview dry run failed", exc_info=True)
        run = {"status": "run_error"}
    if not isinstance(run, dict):
        run = {"status": "run_error"}

    rec = {
        "preview_id": f"prev-{uuid.uuid4().hex[:10]}",
        "event_type": kind,
        "domain_id": did,
        "run_id": str(run.get("run_id") or ""),
        "run_status": str(run.get("status") or ""),
        "hitl_status": "pending",
        "live_started": False,
        "wrote_live_yaml": False,
        "notified_channel": False,
        "second_channel": False,
        "m4_claim_allowed": False,
        "authority_note": "白名单事件只做沙箱预演。待人批。不进 live，不推渠道。",
    }
    dest = _home() / "org" / "event_previews" / f"{rec['preview_id']}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, **rec}


def _receipt(status: str, text: str, **extra: Any) -> Dict[str, Any]:
    out = {
        "status": status,
        "receipt_text": text,
        "channel": "feishu",
        "execution_mode": "inline_ack",
    }
    out.update(extra)
    return out
