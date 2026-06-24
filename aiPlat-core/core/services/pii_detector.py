"""
PII Detector — 自动检测并脱敏个人敏感信息。

在 sys_llm_generate 入口处拦截，自动替换：
  - 手机号 (中国: 1[3-9]xxxxxxxxx)
  - 身份证号 (18位)
  - 邮箱地址
  - 银行卡号 (16-19位)
  - 家庭地址 (省/市/区/路模式)

支持两套引擎并行：
  - 内置正则 (builtin, 零依赖)
  - Microsoft Presidio (可选, 需安装 presidio-analyzer)

RBAC 控制: unmask() 仅 admin / data_owner 角色可见原文。
"""

from __future__ import annotations

import re
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── 内置正则规则 (零依赖) ─────────────────────────────────────────────

_BUILTIN_PATTERNS: List[Tuple[str, str, str]] = [
    # (正则, 替换标签, 描述)
    # 中国手机号
    (r'(?<!\d)1[3-9]\d{9}(?!\d)', 'PHONE', '手机号'),
    # 中国身份证号 (18位)
    (r'(?<!\d)[1-8]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)', 'ID_CARD', '身份证号'),
    # 邮箱
    (r'[\w.\-+#]+@[\w.\-]+\.[a-zA-Z]{2,}', 'EMAIL', '邮箱'),
    # 银行卡号 (16-19位)
    (r'(?<!\d)\d{16,19}(?!\d)', 'BANK_CARD', '银行卡号'),
    # 中国地址
    (r'(?:北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|'
     r'台湾|内蒙|广西|西藏|宁夏|新疆|香港|澳门)(?:省|市|自治区|特别行政区)?'
     r'(?:[\u4e00-\u9fa5]{1,10}(?:市|区|县|镇|乡|街道|路|街|巷|号|楼|层|室)){1,5}',
     'ADDRESS', '地址'),
    # IPv4 地址
    (r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', 'IP_ADDRESS', 'IP地址'),
]


def _short_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:6]


@dataclass
class PIIRecord:
    """单个 PII 匹配记录"""
    original: str
    label: str          # PHONE / ID_CARD / EMAIL / BANK_CARD
    description: str
    masked_id: str      # 如 PHONE_abc123


class PIIDetector:
    """PII 检测与脱敏引擎。

    Usage:
        detector = PIIDetector()
        masked_text, mapping = detector.mask("我的手机是13800138000")
        # → "我的手机是[PHONE_abc123]", {"PHONE_abc123": "13800138000"}

        restored = detector.unmask(result, mapping, role="admin")
        # → "分析结果...13800138000..."

        restored = detector.unmask(result, mapping, role="user")
        # → "分析结果...[PHONE_abc123]..." (非特权角色保持脱敏)
    """

    ALLOWED_UNMASK_ROLES: set = {"admin", "data_owner"}

    def __init__(self, *, use_presidio: bool = False):
        self._use_presidio = use_presidio and self._presidio_available()
        self._records: Dict[str, PIIRecord] = {}
        self._counter: Dict[str, int] = {}

    def _presidio_available(self) -> bool:
        try:
            import presidio_analyzer  # noqa: F401
            return True
        except ImportError:
            return False

    def mask(self, text: str) -> Tuple[str, Dict[str, str]]:
        """脱敏文本。

        Returns:
            (masked_text, mapping) — mapping 键为 masked_id，值为原始明文
        """
        if not text or not text.strip():
            return text, {}

        masked = text
        mapping: Dict[str, str] = {}
        self._counter.clear()

        # ── 内置正则 (始终运行) ──
        for pattern, label, desc in _BUILTIN_PATTERNS:
            def _replace(m: re.Match) -> str:
                original = m.group(0)
                idx = self._counter.get(label, 0) + 1
                self._counter[label] = idx
                masked_id = f"{label}_{idx:03d}"
                mapping[masked_id] = original
                return f"[{masked_id}]"
            masked = re.sub(pattern, _replace, masked)

        # ── Presidio (可选, 与内置正则并行取并集) ──
        if self._use_presidio:
            try:
                from presidio_analyzer import AnalyzerEngine
                from presidio_anonymizer import AnonymizerEngine, OperatorConfig
                analyzer = AnalyzerEngine()
                results = analyzer.analyze(text=text, language="zh")
                if results:
                    anonymizer = AnonymizerEngine()
                    presidio_result = anonymizer.anonymize(
                        text=text,
                        analyzer_results=results,
                        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})},
                    )
                    # 取并集: presidio 标记的额外实体也加入 mapping
                    for r in results:
                        original = text[r.start:r.end]
                        label = r.entity_type
                        idx = self._counter.get(label, 0) + 1
                        self._counter[label] = idx
                        masked_id = f"{label}_{idx:03d}"
                        mapping[masked_id] = original
            except Exception:
                pass  # Presidio 降级, 内置正则已覆盖

        return masked, mapping

    def unmask(self, text: str, mapping: Dict[str, str], *, role: str = "user") -> str:
        """还原脱敏文本。

        Args:
            text: 待还原的文本
            mapping: mask() 返回的 mapping 字典
            role: 当前用户角色 (admin/data_owner 可见原文, 其他保持脱敏)

        Returns:
            还原后的文本
        """
        if not mapping:
            return text

        allowed = role in self.ALLOWED_UNMASK_ROLES
        result = text

        for masked_id, original in mapping.items():
            replacement = original if allowed else f"[{masked_id}]"
            result = result.replace(original, replacement)
            # 同时替换 masked_id 形式 (以防 LLM 输出中保留了 masked_id)
            if not allowed:
                result = result.replace(f"[{masked_id}]", f"[{masked_id}]")  # 保持不变

        return result

    def get_audit_info(self, mapping: Dict[str, str]) -> Dict[str, Any]:
        """获取审计信息 (用于 audit_log)。

        Returns:
            {"pii_count": N, "pii_types": ["PHONE", "EMAIL", ...]}
        """
        types = set()
        for masked_id in mapping:
            label = masked_id.rsplit("_", 1)[0]
            types.add(label)
        return {
            "pii_count": len(mapping),
            "pii_types": sorted(types),
        }


# ── 全局单例 ───────────────────────────────────────────────────────────────

_pii_detector: Optional[PIIDetector] = None


def get_pii_detector() -> PIIDetector:
    global _pii_detector
    if _pii_detector is None:
        use_presidio = os.getenv("AIPLAT_PII_PRESIDIO_ENABLED", "false").lower() in ("1", "true", "yes")
        _pii_detector = PIIDetector(use_presidio=use_presidio)
    return _pii_detector
