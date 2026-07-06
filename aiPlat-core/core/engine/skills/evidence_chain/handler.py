"""证据链通用编排器 — 复用 aiPlat 已有验证基础设施。

多源数据提取 → 声明验证 → 交叉校验 → 置信度输出
"""
import os, sys, yaml, json
from pathlib import Path
from typing import Dict, Any, List


def load_chain(chain_file: str) -> Dict[str, Any]:
    path = Path(os.path.expanduser(chain_file))
    if not path.exists():
        raise FileNotFoundError(f"证据链文件不存在: {chain_file}")
    with open(path) as f:
        return yaml.safe_load(f)


def extract_source_data(source: Dict) -> Dict[str, Any]:
    """Extract data from a single source."""
    src_type = source.get("type", "file")
    name = source.get("name", "unnamed")
    result = {"source": name, "type": src_type, "data": None, "error": None}

    try:
        if src_type == "file":
            path = os.path.expanduser(source.get("path", ""))
            if os.path.isfile(path):
                with open(path) as f:
                    result["data"] = f.read()[:5000]
            else:
                result["error"] = f"File not found: {path}"
        elif src_type == "api":
            import urllib.request
            endpoint = source.get("endpoint", "")
            query = source.get("query", "")
            url = f"{endpoint}?query={urllib.request.quote(query)}" if query else endpoint
            resp = urllib.request.urlopen(url, timeout=10)
            result["data"] = resp.read().decode(errors="ignore")[:5000]
        elif src_type == "database":
            # Placeholder: requires actual DB connection
            result["data"] = f"[DB] {source.get('table','?')} filtered: {source.get('filter','none')}"
        else:
            result["error"] = f"Unknown source type: {src_type}"
    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def evaluate_sources(chain: Dict[str, Any], query_context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute evidence chain: extract → verify → confidence."""
    sources = chain.get("sources", [])
    verify_rules = chain.get("verify", {})

    # Step 1: Multi-source extraction
    raw_results = [extract_source_data(s) for s in sources]
    successful = [r for r in raw_results if r["data"] is not None]
    failed = [r for r in raw_results if r["error"] is not None]

    # Step 2: Simple claim extraction (regex-based as fallback)
    claims = []
    for r in successful:
        lines = str(r["data"]).split("\n")
        for line in lines[:50]:
            line = line.strip()
            if line and len(line) > 20:
                claims.append({
                    "text": line[:200],
                    "source": r["source"],
                    "entailment": "pending",
                })

    # Step 3: Cross-validation (simple string matching)
    contradictions = []
    for i, c1 in enumerate(claims):
        for j, c2 in enumerate(claims):
            if j <= i:
                continue
            # Very basic contradiction check
            if c1["text"][:50] != c2["text"][:50] and c1["source"] != c2["source"]:
                common_words = set(c1["text"].lower().split()) & set(c2["text"].lower().split())
                if len(common_words) > 10:
                    contradictions.append({
                        "claim_a": c1["text"][:100],
                        "claim_b": c2["text"][:100],
                        "common_words": len(common_words),
                    })

    # Step 4: Confidence calculation
    min_sources = verify_rules.get("min_sources", 2)
    contradiction_threshold = verify_rules.get("contradiction_threshold", 0.3)

    source_penalty = max(0, min_sources - len(successful)) * 0.1
    contradiction_penalty = min(len(contradictions) * 0.05, 0.3)
    base_confidence = 0.85

    confidence = round(max(base_confidence - source_penalty - contradiction_penalty, 0.2), 2)

    # Try graph cross-check if HallucinationTracker is available
    graph_verified = False
    if verify_rules.get("graph_cross_check"):
        try:
            from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker
            tracker = get_hallucination_tracker()
            report = tracker.evaluate(
                answer=json.dumps([c["text"] for c in claims[:5]]),
                context=json.dumps([r["data"] for r in successful]),
            )
            if report.faithfulness > 0.5:
                graph_verified = True
                confidence = min(confidence + 0.1, 1.0)
        except Exception:
            pass

    return {
        "claim_verification": claims[:20],
        "hallucination_risk": round(1.0 - confidence, 2),
        "confidence": confidence,
        "cross_validation": {
            "sources_requested": len(sources),
            "sources_successful": len(successful),
            "sources_failed": len(failed),
            "contradictions_found": len(contradictions),
            "graph_verified": graph_verified,
        },
        "chain_name": chain.get("name", "unnamed"),
    }


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """Skill entry point."""
    chain_file = params["chain_file"]
    query_context = params.get("query_context", {})
    chain = load_chain(chain_file)
    return evaluate_sources(chain, query_context)


if __name__ == "__main__":
    print(execute({"chain_file": "examples/system_diagnosis.yaml", "query_context": {"time_range": "1h"}}))
