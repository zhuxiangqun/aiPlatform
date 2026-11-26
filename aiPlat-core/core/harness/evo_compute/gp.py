"""GP 强类型 DSL 沙箱（Phase 3 / G3；禁止生成核心代码）。

只允许规则树 / 条件 / 动作 / 受限 workflow 节点。
非目标：不写生产、不 ``exec``/``eval``、不输出 Python 源码、不宣称 G3 完成。
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# 允许的 DSL 节点类型（强类型白名单）
ALLOWED_NODE_TYPES: frozenset = frozenset(
    {
        "rule",
        "condition",
        "action",
        "workflow_step",
        "and",
        "or",
        "not",
        "const",
    }
)

# 禁止出现在程序中的危险键/形态
_FORBIDDEN_KEYS: frozenset = frozenset(
    {
        "python",
        "code",
        "source",
        "exec",
        "eval",
        "import",
        "bytecode",
        "module_path",
        "file_write",
    }
)


def dsl_node(
    node_type: str,
    *,
    name: str = "",
    value: Any = None,
    children: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构造 DSL 节点。

    Args:
        node_type: 须在 ``ALLOWED_NODE_TYPES``。
        name: 可选名称。
        value: 常量/谓词值。
        children: 子节点。
    """
    return {
        "type": str(node_type or "").strip().lower(),
        "name": str(name or "").strip(),
        "value": value,
        "children": [dict(c) for c in (children or [])],
    }


def validate_dsl_program(program: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """校验程序仅含白名单节点且无核心代码载荷。

    Args:
        program: DSL 根节点或 ``{"root": node}``。

    Returns:
        ``ok`` / ``dsl_only`` / ``errors``；``emits_core_code`` 恒关注。
    """
    errors: List[str] = []
    root = program
    if isinstance(program, dict) and "root" in program:
        root = program.get("root")
    if not isinstance(root, dict):
        return {
            "ok": False,
            "dsl_only": False,
            "emits_core_code": False,
            "errors": ["root_not_object"],
            "g3_foundation": True,
            "g3_complete": False,
        }

    def walk(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path}:not_object")
            return
        for k in node.keys():
            if str(k).lower() in _FORBIDDEN_KEYS:
                errors.append(f"{path}:forbidden_key:{k}")
        t = str(node.get("type") or "").strip().lower()
        if t not in ALLOWED_NODE_TYPES:
            errors.append(f"{path}:illegal_type:{t or 'missing'}")
        # 值侧禁止像源码的长字符串带 def/class/import
        val = node.get("value")
        if isinstance(val, str):
            low = val.lower()
            if any(x in low for x in ("\ndef ", "\nclass ", "import ", "exec(", "eval(")):
                errors.append(f"{path}:value_looks_like_code")
        for i, ch in enumerate(node.get("children") or []):
            walk(ch, f"{path}.c{i}")

    walk(root, "root")
    emits = any("forbidden_key" in e or "value_looks_like_code" in e for e in errors)
    dsl_only = len(errors) == 0
    return {
        "ok": dsl_only,
        "dsl_only": dsl_only,
        "emits_core_code": emits,
        "errors": errors,
        "node_types_allowed": sorted(ALLOWED_NODE_TYPES),
        "g3_foundation": True,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
        "note": "GP DSL validate only; illegal types/code payloads rejected",
    }


def default_seed_program() -> Dict[str, Any]:
    """默认种子规则树（夹具）。"""
    return {
        "root": dsl_node(
            "rule",
            name="seed_rule",
            children=[
                dsl_node(
                    "and",
                    children=[
                        dsl_node("condition", name="latency_ok", value="lt:200"),
                        dsl_node("condition", name="safety_ok", value="eq:0"),
                    ],
                ),
                dsl_node("action", name="accept", value="rank"),
                dsl_node("workflow_step", name="record", value="lineage"),
            ],
        )
    }


def _rng(seed: int, salt: str = "") -> random.Random:
    h = hashlib.sha256(f"{int(seed)}:{salt}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def _collect_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = [node]
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            out.extend(_collect_nodes(ch))
    return out


def _clone(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": node.get("type"),
        "name": node.get("name"),
        "value": node.get("value"),
        "children": [_clone(c) for c in (node.get("children") or []) if isinstance(c, dict)],
    }


def _mutate_tree(root: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    """在白名单内突变：改 name/value 或替换叶子 type。"""
    tree = _clone(root)
    nodes = _collect_nodes(tree)
    target = rng.choice(nodes)
    roll = rng.random()
    if roll < 0.34:
        target["name"] = f"{target.get('name') or 'n'}_{rng.randint(0, 99)}"
    elif roll < 0.67:
        target["value"] = f"v{rng.randint(0, 9)}"
    else:
        # 叶子可换成 const；内部保持逻辑型
        if not (target.get("children") or []):
            target["type"] = rng.choice(["const", "condition", "action"])
        else:
            target["type"] = rng.choice(["and", "or", "rule"])
    return tree


def _crossover(a: Dict[str, Any], b: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    """交换子树（仍须通过 validate）。"""
    ca, cb = _clone(a), _clone(b)
    na, nb = _collect_nodes(ca), _collect_nodes(cb)
    if len(na) < 2 or len(nb) < 2:
        return ca
    ia = rng.randrange(1, len(na))
    ib = rng.randrange(1, len(nb))
    # 替换 ca 的子引用：简化为把 na[ia] 内容换成 nb[ib]
    donor = _clone(nb[ib])
    na[ia]["type"] = donor.get("type")
    na[ia]["name"] = donor.get("name")
    na[ia]["value"] = donor.get("value")
    na[ia]["children"] = donor.get("children") or []
    return ca


def program_fingerprint(program: Dict[str, Any]) -> str:
    """程序指纹。

    Args:
        program: 含 root 的程序。
    """
    blob = str(program.get("root") or program)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def run_gp_offline(
    *,
    population_size: int = 6,
    generations: int = 3,
    seed: int = 42,
    seed_program: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """离线 GP：仅在强类型 DSL 内繁殖；拒绝核心代码。

    Args:
        population_size: 种群。
        generations: 代数。
        seed: 种子。
        seed_program: 可选种子程序。

    Returns:
        回执；``dsl_only`` 须为 True；``emits_core_code``/``g3_complete`` 恒 false。
    """
    base = seed_program or default_seed_program()
    v0 = validate_dsl_program(base)
    if not v0.get("ok"):
        return {
            "ok": False,
            "error": "seed_invalid",
            "validation": v0,
            "dsl_only": False,
            "emits_core_code": bool(v0.get("emits_core_code")),
            "g3_foundation": True,
            "g3_complete": False,
            "certified": False,
            "e2_claimed": False,
            "production_write": False,
        }

    pop_n = max(2, int(population_size))
    gens = max(1, int(generations))
    rng = _rng(seed, "gp-init")
    root0 = base.get("root") if isinstance(base, dict) else base
    population: List[Dict[str, Any]] = [{"root": _clone(root0)}]
    while len(population) < pop_n:
        population.append({"root": _mutate_tree(root0, _rng(seed, f"init-{len(population)}"))})

    history: List[Dict[str, Any]] = []
    best = population[0]
    best_score = 0.0

    def score(prog: Dict[str, Any]) -> float:
        val = validate_dsl_program(prog)
        if not val.get("ok"):
            return -1.0
        # 简单：节点数适中更好（代理适应度，非生产）
        n = len(_collect_nodes(prog.get("root") or {}))
        return 1.0 / (1.0 + abs(n - 6))

    for g in range(gens):
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for i, ind in enumerate(population):
            val = validate_dsl_program(ind)
            if not val.get("dsl_only"):
                # 非法个体丢弃为种子突变
                ind = {"root": _mutate_tree(root0, _rng(seed, f"repair-{g}-{i}"))}
                val = validate_dsl_program(ind)
            s = score(ind) if val.get("ok") else -1.0
            scored.append((s, ind))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        history.append(
            {
                "generation": g,
                "best_score": round(best_score, 6),
                "fingerprint": program_fingerprint(best),
            }
        )
        # 下一代：精英 + 交叉/突变
        next_pop = [scored[0][1], scored[min(1, len(scored) - 1)][1]]
        while len(next_pop) < pop_n:
            pa = scored[rng.randrange(0, min(3, len(scored)))][1]
            pb = scored[rng.randrange(0, min(3, len(scored)))][1]
            child_root = _crossover(pa.get("root") or {}, pb.get("root") or {}, rng)
            if rng.random() < 0.5:
                child_root = _mutate_tree(child_root, rng)
            child = {"root": child_root}
            if not validate_dsl_program(child).get("ok"):
                child = {"root": _mutate_tree(root0, rng)}
            next_pop.append(child)
        population = next_pop

    final_val = validate_dsl_program(best)
    return {
        "ok": bool(final_val.get("ok")),
        "algorithm": "gp_dsl",
        "population_size": pop_n,
        "generations": gens,
        "seed": int(seed),
        "best": best,
        "best_score": round(float(best_score), 6),
        "history": history,
        "validation": final_val,
        "dsl_only": bool(final_val.get("dsl_only")),
        "emits_core_code": False,
        "production_write": False,
        "g3_foundation": True,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "offline typed-DSL GP only; no core code generation",
    }


def reject_core_code_payload(payload: Any) -> Dict[str, Any]:
    """显式拒绝核心代码载荷（门禁探针）。

    Args:
        payload: 任意载荷（若含 python/code 等则拒）。
    """
    fake = {"root": {"type": "rule", "python": payload, "children": []}}
    if isinstance(payload, dict):
        fake = {"root": dict(payload)}
        if "type" not in fake["root"]:
            fake["root"]["type"] = "rule"
    return validate_dsl_program(fake)
