"""experience_feedback.py — L2 经验回写链路（gotchas 登记 → 两次验证 → 升级）。

HarnessEval × SBA 落地（docs/research/sba-harnesseval-执行评测双闭环.md §5.5）：
评测失败不再止于"扣分"，而是按 ratchet 哲学沉淀为可升级的经验：

  register_failure(登记) ──▶ pending
      │                           │ record_verification(success) ×2（独立案例）
      ▼                           ▼
  confidence<0.7 拒绝          promoted（低风险自动 / 高风险 require_review 待人工确认）
      │
      └── record_verification(fail) ×2 ──▶ rejected

设计要点（对应 §5.5 实施边界）：
- 记录失败是安全的（gotchas = 可逆日志）：register 永远不失败（仅低置信度拒收）；
- 改写知识是不安全的：升级只生成 promote_draft 规则草案文本，不自动改写 SKILL.md/AGENT.md；
- 两次独立验证：同 case_id 重复验证不计数（防刷），连续 2 次失败判定经验无效（rejected）；
- 兜底门槛：MIN_CONFIDENCE=0.7（低于只提示不登记）；risk=high 升级需人工确认（require_review）。

用法（Python）:
    from governance.experience_feedback import register_failure, record_verification, status
    register_failure("rag-groundedness-missing-source", "RAG 回答缺失检索来源", source="evidence_tree", confidence=0.9)

用法（CLI）:
    python3 aiPlat-platform/governance/experience_feedback/experience_feedback.py \
        --register --rule <rule_id> --content "<描述>" [--source x] [--confidence 0.9] [--risk low|high]
    python3 .../experience_feedback.py --verify --rule <rule_id> --case <case_id> --outcome success|fail
    python3 .../experience_feedback.py --status [--rule <rule_id>]
    python3 .../experience_feedback.py --promote --rule <rule_id> [--confirm]   # 高风险需 --confirm

存储：JSON 文件（环境变量 AIPLAT_EXPERIENCE_FILE 指定；默认 $AIPLAT_HOME/experience_feedback.json）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

MIN_CONFIDENCE = 0.7      # 低于此置信度的失败只提示、不登记（§5.5.3 兜底①）
PROMOTE_THRESHOLD = 2     # 两次独立验证成功才固化（SBA 原则 14）
FAIL_LIMIT = 2            # 连续 2 次验证失败 → 经验无效（rejected）

STATUS_PENDING = "pending"
STATUS_PROMOTED = "promoted"
STATUS_REJECTED = "rejected"

VALID_RISKS = ("low", "high")


def _default_path() -> str:
    """默认存储路径：AIPLAT_EXPERIENCE_FILE > $AIPLAT_HOME/experience_feedback.json > ~/.aiplat/..."""
    env = os.environ.get("AIPLAT_EXPERIENCE_FILE")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    return os.path.join(home, "experience_feedback.json")


@dataclass
class Experience:
    """一条经验（gotcha）。id 唯一；rule_id 为同类失败的聚合键。"""
    rule_id: str
    content: str
    source: str = "manual"
    confidence: float = 1.0
    risk: str = "low"
    id: str = field(default_factory=lambda: f"exp-{int(time.time()*1000)}")
    status: str = STATUS_PENDING
    verify_count: int = 0
    verify_events: List[Dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    promoted_at: Optional[str] = None
    promote_draft: Optional[str] = None
    require_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExperienceStore:
    """JSON 文件持久化的经验注册表。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_path()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, records: List[Dict[str, Any]]) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ── 状态机 ──
    def register_failure(self, rule_id: str, content: str, source: str = "manual",
                         confidence: float = 1.0, risk: str = "low") -> Dict[str, Any]:
        """登记失败经验 → pending。置信度低于门槛拒绝；同 rule_id 已存在则合并证据。"""
        if risk not in VALID_RISKS:
            risk = "low"
        if confidence < MIN_CONFIDENCE:
            return {"registered": False, "reason": "confidence_below_threshold",
                    "threshold": MIN_CONFIDENCE, "confidence": confidence}

        records = self._load()
        existing = next((r for r in records if r.get("rule_id") == rule_id
                         and r.get("status") == STATUS_PENDING), None)
        if existing:
            # 同源失败再次出现：合并证据（source 去重追加）
            sources = existing.get("sources") or [existing.get("source")]
            if source not in sources:
                sources.append(source)
            existing["sources"] = sources
            existing["occurrences"] = existing.get("occurrences", 1) + 1
            existing["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save(records)
            return {"registered": True, "id": existing["id"], "merged": True,
                    "occurrences": existing["occurrences"]}

        exp = Experience(rule_id=rule_id, content=content, source=source,
                         confidence=confidence, risk=risk)
        rec = exp.to_dict()
        rec["sources"] = [source]
        rec["occurrences"] = 1
        records.append(rec)
        self._save(records)
        return {"registered": True, "id": rec["id"], "merged": False}

    def record_verification(self, rule_id: str, case_id: str, outcome: str) -> Dict[str, Any]:
        """记录一次独立案例的验证结果。success 累计（同 case 不重复）；fail 重置累计。"""
        if outcome not in ("success", "fail"):
            return {"error": f"invalid outcome: {outcome}"}

        records = self._load()
        rec = next((r for r in records if r.get("rule_id") == rule_id), None)
        if not rec:
            return {"error": f"rule not found: {rule_id}"}
        if rec.get("status") == STATUS_REJECTED:
            return {"error": "rule already rejected"}

        events = rec.get("verify_events", [])
        if any(e.get("case_id") == case_id for e in events):
            return {"verified": False, "duplicate_case": True, "id": rec["id"]}

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        events.append({"case_id": case_id, "outcome": outcome, "at": now})
        rec["verify_events"] = events
        rec["updated_at"] = now

        if outcome == "success":
            count = rec.get("verify_count", 0) + 1
            rec["verify_count"] = count
            self._save(records)
            if count >= PROMOTE_THRESHOLD:
                return {"verified": True, "id": rec["id"], "count": count,
                        **self._promote(rec, records)}
            return {"verified": True, "id": rec["id"], "count": count,
                    "status": rec["status"], "promote_pending": PROMOTE_THRESHOLD - count}
        else:
            rec["verify_count"] = 0
            fail_streak = rec.get("fail_streak", 0) + 1
            rec["fail_streak"] = fail_streak
            if fail_streak >= FAIL_LIMIT:
                rec["status"] = STATUS_REJECTED
                result = {"verified": False, "id": rec["id"], "status": STATUS_REJECTED,
                          "reason": "连续 2 次验证失败，经验判定无效"}
            else:
                result = {"verified": False, "id": rec["id"], "count": 0,
                          "status": rec["status"], "fail_streak": fail_streak}
            self._save(records)
            return result

    def _promote(self, rec: Dict[str, Any], records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """升级：生成规则草案。低风险自动 promoted；高风险 require_review 待人工确认。"""
        rec["status"] = STATUS_PROMOTED
        rec["promoted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rec["promote_draft"] = (
            f"「{rec['rule_id']}」——{rec['content']}\n"
            f"（经验来源 {rec['source']}，{rec['verify_count']} 次独立验证成功，"
            f"置信度 {rec['confidence']}，风险 {rec['risk']}）"
        )
        if rec.get("risk") == "high":
            rec["require_review"] = True
            rec["status"] = STATUS_PROMOTED + ":review"  # 待人工确认
            self._save(records)
            return {"promoted": True, "require_review": True, "id": rec["id"],
                    "draft": rec["promote_draft"]}
        self._save(records)
        return {"promoted": True, "require_review": False, "id": rec["id"],
                "draft": rec["promote_draft"]}

    def confirm_promotion(self, rule_id: str, accept: bool = True) -> Dict[str, Any]:
        """高风险经验的升级确认（人工门槛）。accept=False → 回退为 rejected。"""
        records = self._load()
        rec = next((r for r in records if r.get("rule_id") == rule_id), None)
        if not rec:
            return {"error": f"rule not found: {rule_id}"}
        if rec.get("status") != STATUS_PROMOTED + ":review":
            return {"error": f"rule not in review state: {rec.get('status')}"}
        if accept:
            rec["status"] = STATUS_PROMOTED
            rec["require_review"] = False
            rec["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save(records)
            return {"confirmed": True, "id": rec["id"], "status": STATUS_PROMOTED}
        rec["status"] = STATUS_REJECTED
        rec["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save(records)
        return {"confirmed": False, "id": rec["id"], "status": STATUS_REJECTED}

    def status(self, rule_id: Optional[str] = None) -> List[Dict[str, Any]]:
        records = self._load()
        if rule_id:
            records = [r for r in records if r.get("rule_id") == rule_id]
        return records


def register_failure(rule_id: str, content: str, source: str = "manual",
                     confidence: float = 1.0, risk: str = "low",
                     path: Optional[str] = None) -> Dict[str, Any]:
    return ExperienceStore(path).register_failure(rule_id, content, source, confidence, risk)


def record_verification(rule_id: str, case_id: str, outcome: str,
                        path: Optional[str] = None) -> Dict[str, Any]:
    return ExperienceStore(path).record_verification(rule_id, case_id, outcome)


def status(rule_id: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, Any]]:
    return ExperienceStore(path).status(rule_id)


# ── CLI ──
def _cli(argv: List[str]) -> int:
    path = os.environ.get("AIPLAT_EXPERIENCE_FILE")
    def arg(name: str, default: str = "") -> str:
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    if "--register" in argv:
        r = register_failure(arg("--rule"), arg("--content"),
                             source=arg("--source", "manual"),
                             confidence=float(arg("--confidence", "1.0")),
                             risk=arg("--risk", "low"), path=path)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("registered") else 1
    if "--verify" in argv:
        r = record_verification(arg("--rule"), arg("--case"), arg("--outcome"), path=path)
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if "--confirm" in argv:
        r = ExperienceStore(path).confirm_promotion(arg("--rule"))
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if "--status" in argv:
        rule = arg("--rule") or None
        print(json.dumps(status(rule, path=path), ensure_ascii=False, indent=2))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    # 允许直接按文件路径运行（不经包导入）：把平台根加入 sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(_cli(sys.argv[1:]))
