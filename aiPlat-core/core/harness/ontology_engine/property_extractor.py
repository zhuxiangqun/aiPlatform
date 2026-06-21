"""
PropertyExtractor — 按类字段定义从文本中提取属性值。

策略: 将 OntologyClass.fields 动态注入 LLM prompt，
     LLM 返回结构化 JSON → 映射到实例字段。
     零硬编码——字段定义全部来自 YAML 配置。
"""

from __future__ import annotations

import json as _json
import re as _re
from typing import Any, Dict, List, Optional

from core.harness.knowledge.knowledge_ontology import OntologyClass
from core.harness.knowledge.ontology_loader import OntologyDomain


class PropertyExtractor:
    """Extract property values from text using LLM, guided by class field definitions."""

    def __init__(self, domain: OntologyDomain):
        self._domain = domain

    def build_extraction_prompt(self, class_name: str, text: str, *,
                                  table_context: str = "") -> str:
        """Build LLM prompt with class field definitions + optional table context."""
        cls: Optional[OntologyClass] = None
        for c in self._domain.classes:
            if c.label == class_name:
                cls = c
                break
        if cls is None:
            raise ValueError(f"Class '{class_name}' not found in domain '{self._domain.id}'")

        # Build fields description from cls.fields + required_fields
        fields_desc = []
        required_set = set(cls.required_fields)
        for f in (cls.fields or []):
            fname = f.get("name", "")
            ftype = f.get("type", "string")
            fdesc = f.get("description", "")
            fvalues = f.get("values", [])
            marker = "*" if fname in required_set else ""
            fields_desc.append(
                f"  - {fname}{marker}: {ftype}"
                + (f" (可选值: {', '.join(fvalues)})" if fvalues else "")
                + (f" // {fdesc}" if fdesc else "")
            )
        # Also include required_fields not in fields
        for rf in cls.required_fields:
            if not any(f.get("name") == rf for f in (cls.fields or [])):
                fields_desc.append(f"  - {rf}*: string (必填)")

        fields_text = "\n".join(fields_desc) if fields_desc else "  (无字段定义)"

        prompt = (
            f"你是知识图谱数据提取专家。从以下文本中提取「{cls.label}」类型实例的字段值。\n\n"
            f"字段定义 (带*号的为必填):\n{fields_text}\n\n"
        )
        if table_context:
            prompt += f"参考表格数据:\n{table_context}\n\n"
        prompt += (
            f"文本:\n{text[:3000]}\n\n"
            f"输出严格JSON (无markdown标记):\n"
            f'{{"提取结果":{{"字段名":"字段值",...}},"置信度":0.9,"理由":"简短说明"}}\n\n'
            f"规则:\n"
            f"- 字段值直接从文本提取,不要编造\n"
            f"- 枚举字段必须从可选值中选择,如果文本不明确则选最可能的\n"
            f"- 如果某个字段在文本中无对应内容,填写默认值或留空\n"
            f"- 必填字段必须有值"
        )
        return prompt

    async def extract(
        self,
        class_name: str,
        text: str,
        *,
        model_name: str = "",
        timeout: int = 120,
        table_context: str = "",
    ) -> Dict[str, Any]:
        """Extract field values from text using LLM.

        Returns: {"name": "RAG", "description": "...", "maturity": "production", ...}
        """
        prompt = self.build_extraction_prompt(class_name, text, table_context=table_context)

        from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
        from core.adapters.llm.base import LLMConfig

        model = model_name or best_model_for_purpose("ontology_gen")
        adapter = create_selected_adapter(model_name=model)
        config = LLMConfig(model="", timeout=timeout)

        try:
            resp = await adapter.generate(
                [{"role": "user", "content": prompt}],
                config=config,
            )
            content = resp.content if hasattr(resp, 'content') else str(resp)
            return self._parse_response(content)
        except Exception:
            return {}

    def extract_sync(
        self,
        class_name: str,
        text: str,
        *,
        model_name: str = "",
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for non-async contexts."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.extract(class_name, text, model_name=model_name, timeout=timeout),
                    )
                    return future.result(timeout=timeout + 10)
            return asyncio.run(self.extract(class_name, text, model_name=model_name, timeout=timeout))
        except RuntimeError:
            return asyncio.run(self.extract(class_name, text, model_name=model_name, timeout=timeout))

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM JSON response into flat field dict."""
        clean = content.strip()
        if clean.startswith("```"):
            clean = _re.sub(r'^```\w*\n?', '', clean)
            clean = _re.sub(r'\n?```$', '', clean)
        # Use raw_decode to parse only the first valid JSON value (prevents greedy match bugs)
        dec = _json.JSONDecoder()
        try:
            data, _ = dec.raw_decode(clean)
        except (_json.JSONDecodeError, TypeError):
            # Fallback: try finding first { or [
            start = max(clean.find('{'), clean.find('['))
            if start >= 0:
                try:
                    data, _ = dec.raw_decode(clean[start:])
                except (_json.JSONDecodeError, TypeError):
                    return {}
            else:
                return {}
        # Handle nested {"提取结果": {...}} format
        inner = data.get("提取结果", data)
        if isinstance(inner, dict):
            return {k: v for k, v in inner.items() if v is not None}
        return {}
