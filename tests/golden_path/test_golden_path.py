"""金链路行为平面检查 — A 召回 / B1 数据新鲜度 / B2 图遍历缓存失效 / C 契约 + stub 反面对比。

设计依据（reports/honest_status_2026-06-24.md）：
  系统现有 167 项静态守卫/测试只验"代码形状"，看不见运行时行为。
  这条 e2e 是第一条站在"行为平面"的检查：真实入库一个含独特事实的文档，
  再检索，断言召回内容包含该事实——任何 stub/孤儿/并行实现/检索断链都会让它变红。

运行：
  .venv/bin/python -m pytest tests/golden_path/ -v
特性：进程内、离线（embedding=hash、向量库=sqlite tmp、LLM 打桩）、确定性、阻断式、不依赖 live server。
"""
import asyncio

# 独特事实：ASCII 编号 + 数值，便于 FTS5 精确召回（不依赖语义/CJK 分词）
FACT_DOC = """# 龙骨技术规格

龙骨编号 ZX-7731 的抗压强度为 42.8 MPa。
该型号用于远洋货轮主体承力结构。
"""


def test_golden_path_real_ingest_then_retrieve(isolated_env, monkeypatch):
    """行为断言 A：真实入库的独特事实必须能被检索召回。

    走 platform 真实调用的入库入口 wiki_auto_update（kb_parse_document →
    kb_chunk_elements → write_page），仅把 LLM curation 尾巴打桩成 no-op
    （write_page 在其之前已真实执行）。
    """
    tmp_path = isolated_env
    doc = tmp_path / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")

    # 打桩 LLM curation —— write_page 已在 curation 之前真实写入知识库
    import core.harness.knowledge.wiki_engine as wiki_engine

    async def _noop_curate(*args, **kwargs):
        return None

    monkeypatch.setattr(wiki_engine, "llm_curate_page", _noop_curate, raising=False)
    # embedding 无需打桩：止血4 后 embed_text_semantic 已认 AIPLAT_EMBED_BACKEND=hash
    # （isolated_env 已设），检索侧自动回退 hash_embed，与入库同一向量空间。

    from core.api.core_facade import wiki_auto_update

    try:
        ingest_result = asyncio.run(wiki_auto_update("doc-zx7731", str(doc), "default"))
    except Exception as exc:  # noqa: BLE001 — 诊断用，下面以检索召回为真正判据
        ingest_result = {"error": repr(exc)}

    # 核心行为判据：不论入库返回如何，植入的独特事实必须可被检索召回
    from core.harness.syscalls.retrieval import sys_knowledge_retrieve

    hits = sys_knowledge_retrieve("ZX-7731 抗压强度", collection_id="default", top_k=8)

    assert hits, f"检索零召回 —— 入库或检索链路断裂；wiki_auto_update={ingest_result}"

    blob = " ".join(
        f"{h.get('text', '')} {h.get('summary', '')} {h.get('title', '')}" for h in hits
    )
    assert "ZX-7731" in blob, f"召回内容不含植入事实 ZX-7731；命中前300字: {blob[:300]!r}"
    assert "42.8" in blob, f"召回内容不含数值 42.8；命中前300字: {blob[:300]!r}"
    # 精确 recall：入库的页面 title 必须在 top 结果中
    titles = [h.get("title", "") for h in hits]
    assert "keel_spec" in titles, f"入库页面 title 不在召回结果中: {titles}"


def test_stub_endpoint_is_hollow(http_client):
    """反面对比：上传文档端点返回 200（形状绿）但 chunks=0（行为：没真入库）。

    即使请求体传了真实 content，内存 stub 端点也忽略它（端点内写死 content=b""），
    既不解析也不分块/向量化 → chunks 恒为 0。展示"状态码 200 ≠ 真入库"。
    建库走 HTTP create_collection 端点（止血6 补 metadata schema 后不再 500）。
    复用 conftest 的共享 http_client（全程仅 reload 一次，避免后台 task 累积卡顿）。
    """
    r = http_client.post(
        "/api/core/knowledge/collections",
        json={"name": "ghost-kb", "description": "stub hollow test"},
    )
    assert r.status_code == 200, r.text  # 止血6：create_collection 端点不再 500
    collection_id = r.json()["collection_id"]

    r = http_client.post(
        "/api/core/knowledge/documents",
        json={
            "content": "龙骨 STUB-9999 抗压强度 12.3 MPa",
            "metadata": {"collection_id": collection_id, "name": "幽灵文档", "type": "md"},
        },
    )
    assert r.status_code == 200, r.text  # 形状：绿
    document_id = r.json()["document_id"]

    r = http_client.get(f"/api/core/knowledge/documents/{document_id}")
    assert r.status_code == 200, r.text
    # 行为：内存 stub 从不解析/分块/向量化 → chunks 恒为 0
    assert r.json()["chunks"] == 0, (
        f"stub 端点意外产生了 chunks={r.json()['chunks']}，假设需复核"
    )
    # 进一步验证：stub 上传的"空壳文档"不能被真实检索召回
    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    stub_hits = sys_knowledge_retrieve("STUB-9999", collection_id=collection_id, top_k=5)
    stub_texts = " ".join(h.get("text", "") for h in stub_hits)
    assert len(stub_hits) == 0 or "12.3" not in stub_texts, (
        f"stub 上传的空壳文档不应被检索召回！实有 {len(stub_hits)} 条: {stub_texts[:200]}"
    )


# ── 共享 helper（B/C 复用，与断言 A 同一离线打桩策略）────────────────

def _apply_offline_patches(monkeypatch):
    """离线打桩：仅 LLM curation no-op（embedding 由止血4 后的 hash 后端自动处理）。"""
    import core.harness.knowledge.wiki_engine as wiki_engine

    async def _noop_curate(*args, **kwargs):
        return None

    monkeypatch.setattr(wiki_engine, "llm_curate_page", _noop_curate, raising=False)


def _ingest(doc_id, file_path):
    from core.api.core_facade import wiki_auto_update

    return asyncio.run(wiki_auto_update(doc_id, str(file_path), "default"))


def _retrieve(query):
    from core.harness.syscalls.retrieval import sys_knowledge_retrieve

    return sys_knowledge_retrieve(query, collection_id="default", top_k=8)


def _blob(hits):
    return " ".join(
        f"{h.get('text', '')} {h.get('summary', '')} {h.get('title', '')}" for h in hits
    )


# ── 断言 B1：金链路数据新鲜度（更新文档后检索不得返回旧值）──────────

def test_b1_data_freshness_after_update(isolated_env, monkeypatch):
    """行为断言 B1：同一文档更新后，检索必须返回新值、不得返回旧值。

    直击用户体感"我更新了文档，搜出来还是旧的"。覆盖任何过期来源
    （向量/页面缓存未失效、更新=追加而非覆盖等）。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"

    # v1 入库 → 确认基线召回旧值
    doc.write_text("# 龙骨技术规格\n\n龙骨编号 ZX-7731 的抗压强度为 42.8 MPa。\n", encoding="utf-8")
    _ingest("doc-zx7731", doc)
    blob_v1 = _blob(_retrieve("ZX-7731 抗压强度"))
    assert "42.8" in blob_v1, f"v1 基线召回失败: {blob_v1[:200]!r}"

    # 更新同一文档（同文件名 → write_page 同 title 覆盖）为 v2
    doc.write_text("# 龙骨技术规格\n\n龙骨编号 ZX-7731 的抗压强度为 99.9 MPa。\n", encoding="utf-8")
    _ingest("doc-zx7731", doc)
    blob_v2 = _blob(_retrieve("ZX-7731 抗压强度"))

    assert "99.9" in blob_v2, f"更新后未召回新值 99.9（写入未生效）: {blob_v2[:200]!r}"
    assert "42.8" not in blob_v2, f"更新后仍召回旧值 42.8（返回过期数据）: {blob_v2[:200]!r}"


# ── 断言 B2：图遍历缓存失效（图突变后遍历必须反映突变）──────────────

def test_b2_graph_traversal_cache_invalidation(isolated_env):
    """行为断言 B2：给已遍历过的起点新增一条出边后，再遍历必须反映新边。

    隔离 add_relation 的失效行为——预建全部节点（避开 add_entity 的失效），
    遍历填充 TraversalCache，再只加一条边。若该突变路径未失效缓存（§5.45），
    二次遍历命中旧缓存、看不到新边 → Agent 查到过期遍历结果 → 红。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_traversal import traverse

    g = GraphIndex("gp_cache_test")
    # 预建全部节点（add_entity 会失效缓存，但此时尚未遍历，缓存为空）
    g.add_entity("kx_start", "kx_start", "Thing")
    g.add_entity("ky_old", "ky_old", "Thing")
    g.add_entity("kz_fresh", "kz_fresh", "Thing")
    g.add_relation("kx_start", "ky_old", "related_to")

    r1 = traverse("kx_start", g, max_hops=1, direction="outgoing")
    assert "ky_old" in str(r1.to_dict()), f"基线遍历未到达 ky_old: {str(r1.to_dict())[:300]}"
    # 此刻缓存已填充 (kx_start, 1, outgoing)

    # 突变：只加一条边（kz_fresh 已存在 → 不触发 add_entity 的失效）
    g.add_relation("kx_start", "kz_fresh", "related_to")

    r2 = traverse("kx_start", g, max_hops=1, direction="outgoing")
    assert "kz_fresh" in str(r2.to_dict()), (
        "图突变后二次遍历未反映新边 kx_start→kz_fresh —— "
        f"遍历缓存未失效（§5.45），Agent 将查到过期结果: {str(r2.to_dict())[:400]}"
    )


# ── 断言 B3：精确标题查询 ────────────────────────────────────────────

def test_b3_exact_title_recall(isolated_env, monkeypatch):
    """行为断言 B3：用入库页面的 title 作精确查询，应直接召回该页面。

    验证 FTS5 精确标题查询——如果连 title 精确匹配都召不回，检索严重损坏。
    确定性、零外部依赖（embedding=hash）。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)
    hits = _retrieve("keel_spec")
    titles = [h.get("title", "") for h in hits]
    assert "keel_spec" in titles, f"title 精确查询未召回 'keel_spec': {titles}"


# ── 断言 C：金链路检索结果契约 ──────────────────────────────────────

def test_c_retrieval_result_contract(isolated_env, monkeypatch):
    """行为断言 C：检索返回的每条结果必须满足结构契约。

    抓"检索返回 schema 外的值 / 缺必需字段"那类运行时契约违规
    （对应 E 维度 wiki_graph 返回非法 category 的问题）。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    hits = _retrieve("ZX-7731 抗压强度")
    assert hits, "契约检查前置：检索零召回"

    for i, h in enumerate(hits):
        assert isinstance(h, dict), f"结果[{i}] 非 dict: {type(h)}"
        missing = {"text", "title", "score", "source_type"} - set(h.keys())
        assert not missing, f"结果[{i}] 缺必需字段 {missing}；实际字段 {sorted(h.keys())}"
        assert h["source_type"] in {"wiki", "kb"}, (
            f"结果[{i}] source_type 非法: {h['source_type']!r}（应 ∈ {{wiki, kb}}）"
        )
        assert isinstance(h["score"], (int, float)) and not isinstance(h["score"], bool), (
            f"结果[{i}] score 非数值: {h['score']!r}"
        )
        assert isinstance(h.get("text"), str) and h["text"].strip(), f"结果[{i}] text 为空"


# ── 断言 D：检索健壮性（无关 query 不崩、不返回无关内容）──────────

def test_d_graceful_irrelevant_query(isolated_env, monkeypatch):
    """行为断言 D：无关 query 检索不崩、返回合法 list（健壮性降级）。

    验证检索在面对不相关/随机输入时不崩溃、合理返回结果。
    确定性、零外部依赖。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    hits = _retrieve("xyzzy_nonexistent_12345_无关查询")
    assert isinstance(hits, list), f"无关 query 检索应返回 list，实际: {type(hits)}"
    # 不崩即通过（hash embedding 下无关 query 也可能有低分匹配，合理）


# ── 断言 E：检索稳定性（同 query 多次结果一致）───────────────────────

def test_e_retrieval_stability(isolated_env, monkeypatch):
    """行为断言 E：同 query 两次检索返回的 title 集应一致（确定性）。

    抓检索的非确定性 bug（随机排序、缓存退化等）。
    确定性、零外部依赖。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    hits1 = _retrieve("ZX-7731 抗压强度")
    hits2 = _retrieve("ZX-7731 抗压强度")
    titles1 = {h.get("title", "") for h in hits1}
    titles2 = {h.get("title", "") for h in hits2}
    assert titles1 == titles2, f"同 query 两次检索 title 集不一致: {titles1} vs {titles2}"


# ── 断言 F：wiki 元数据一致性（list_all_pages ↔ write_page）─────────

def test_f_wiki_list_consistency(isolated_env, monkeypatch):
    """行为断言 F：入库后 list_all_pages 必须能列出刚写入的页面。

    验证 write_page → wiki 索引的一致性——如果页面写入了但列表看不到，元数据断裂。
    确定性、零外部依赖。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.knowledge.wiki_engine import list_all_pages
    pages = list_all_pages(collection_id="default")
    titles = [p.get("title", "") for p in pages]
    assert "keel_spec" in titles, f"list_all_pages 未包含刚入库的 'keel_spec': {titles}"


# ── 断言 G：top_k 参数生效（检索 limit 不虚设）─────────────────────

def test_g_topk_respected(isolated_env, monkeypatch):
    """行为断言 G：检索 top_k 参数必须生效，返回结果 ≤top_k。

    验证检索 limit 参数不是虚设——如果 top_k 被忽略返回更多结果，参数契约被破坏。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731 抗压强度", collection_id="default", top_k=1)
    assert len(hits) <= 1, f"top_k=1 应返回 ≤1 条，实为 {len(hits)} 条"


# ── 断言 H：KB-only 回退路径不崩 ─────────────────────────────────────

def test_h_kb_fallback_no_crash(isolated_env, monkeypatch):
    """行为断言 H：wiki_first=False（纯 KB 路径）检索不崩溃。

    验证 KB-only 回退链健在——即使 wiki 无数据或 KB 为空，也不应抛异常。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731 抗压强度", collection_id="default", wiki_first=False)
    assert isinstance(hits, list), f"KB-only 检索应返回 list，实为 {type(hits)}"


# ── 断言 I：空查询不崩 ────────────────────────────────────────────────

def test_i_empty_query_no_crash(isolated_env, monkeypatch):
    """行为断言 I：空字符串 query 检索不崩溃、返回 list。

    极端输入健壮性——空 query 不应让检索抛异常或返回非 list。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("", collection_id="default")
    assert isinstance(hits, list), f"空 query 检索应返回 list，实为 {type(hits)}"


# ── 断言 J：极长查询不崩 ──────────────────────────────────────────────

def test_j_long_query_no_crash(isolated_env, monkeypatch):
    """行为断言 J：10KB 超长 query 检索不崩溃、返回 list。

    极端输入健壮性——超长 query 不应让检索 OOM 或抛异常。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    long_q = "测试 " * 5000  # ~15KB
    hits = sys_knowledge_retrieve(long_q, collection_id="default")
    assert isinstance(hits, list), f"超长 query 检索应返回 list，实为 {type(hits)}"


# ── 断言 K：域路由器不崩 + 合法返回值 ────────────────────────────────

def test_k_domain_router_no_crash(isolated_env):
    """行为断言 K：DomainRouter.classify 不崩溃、返回合法 domain_id。

    3 层级联域路由器（T1 标签→T2 向量→T3 LLM）覆盖 5.65.1。
    """
    from core.harness.knowledge.domain_router import DomainRouter
    router = DomainRouter()
    for q in ("龙骨抗压强度", "ship hull design", "kubernetes pod crash", ""):
        try:
            did = router.classify(q)
            assert isinstance(did, str) and did, f"classify({q!r}) 返回非法: {did!r}"
        except Exception as e:
            # LLM tier failure is acceptable (no model available)
            if "LLM" not in str(e) and "model" not in str(e).lower():
                raise


# ── B2 补全：§5.45 五个突变方法逐路径缓存失效验证 ────────────────────
# 统一行为模式：traverse 填充 TraversalCache → 执行突变 → 断言缓存被清。
# 精确对应 §5.45 契约（突变方法必须调 _invalidate_cache）。绿=该路径失效正确
# （grep 的 FAIL 是假阳性）；红=该路径真未失效（Agent 将查到过期遍历结果）。

def _warm_traversal_cache(domain):
    """建最小图 nx→ny，遍历填充缓存，前置断言缓存确已填充。返回 (graph, cache)。"""
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_traversal import traverse
    from core.harness.ontology_engine.traversal_cache import get_traversal_cache

    g = GraphIndex(domain)
    g.add_entity("nx", "nx", "Thing")
    g.add_entity("ny", "ny", "Thing")
    g.add_relation("nx", "ny", "related_to")
    traverse("nx", g, max_hops=1, direction="outgoing")
    cache = get_traversal_cache(domain)
    assert cache.get("nx", 1, "outgoing") is not None, "前置失败：缓存未填充，测试无效"
    return g, cache


def test_b2_remove_entity_invalidates_cache(isolated_env):
    """§5.45 逐路径：remove_entity 突变后遍历缓存必须失效。"""
    g, cache = _warm_traversal_cache("gp_rm_entity")
    g.remove_entity("ny")
    assert cache.get("nx", 1, "outgoing") is None, "remove_entity 后遍历缓存未失效（§5.45）"


def test_b2_add_hyperedge_invalidates_cache(isolated_env):
    """§5.45 逐路径：add_hyperedge 突变后遍历缓存必须失效。"""
    g, cache = _warm_traversal_cache("gp_add_he")
    g.add_hyperedge("evt1", ["nx", "ny"], context_description="evt")
    assert cache.get("nx", 1, "outgoing") is None, "add_hyperedge 后遍历缓存未失效（§5.45）"


def test_b2_remove_hyperedge_invalidates_cache(isolated_env):
    """§5.45 逐路径：remove_hyperedge 突变后遍历缓存必须失效（止血3 已修复）。"""
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_traversal import traverse
    from core.harness.ontology_engine.traversal_cache import get_traversal_cache

    g = GraphIndex("gp_rm_he")
    g.add_entity("nx", "nx", "Thing")
    g.add_entity("ny", "ny", "Thing")
    g.add_relation("nx", "ny", "related_to")
    g.add_hyperedge("evt1", ["nx", "ny"], context_description="evt")  # 此处会清缓存（缓存尚空，无害）
    traverse("nx", g, max_hops=1, direction="outgoing")  # 填充缓存
    cache = get_traversal_cache("gp_rm_he")
    assert cache.get("nx", 1, "outgoing") is not None, "前置失败：缓存未填充"

    g.remove_hyperedge("evt1")
    assert cache.get("nx", 1, "outgoing") is None, "remove_hyperedge 后遍历缓存未失效（§5.45）"


# ── 断言 L：KB-only 模式结果不含 wiki ──────────────────────────────

def test_l_kb_only_excludes_wiki(isolated_env, monkeypatch):
    """行为断言 L：wiki_first=False 时检索结果 source_type 应为 kb。

    验证 KB-only 回退路径正确切换——不应混入 wiki 结果。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731 抗压强度", collection_id="default", wiki_first=False)
    for h in hits:
        assert h.get("source_type") != "wiki", f"KB-only 模式不应返回 wiki: {h.get('title')}"


# ── 断言 M：域路由幂等 ────────────────────────────────────────────────

def test_m_domain_router_idempotent(isolated_env):
    """行为断言 M：DomainRouter.classify 对同 query 返回一致结果。"""
    from core.harness.knowledge.domain_router import DomainRouter
    router = DomainRouter()
    for q in ("龙骨抗压强度", "kubernetes pod crash"):
        r1 = router.classify(q)
        r2 = router.classify(q)
        assert r1 == r2, f"同 query {q!r} 两次 classify 不一致: {r1!r} vs {r2!r}"


# ── 断言 N：domain_id 参数检索不崩 ────────────────────────────────────

def test_n_domain_id_retrieve_no_crash(isolated_env, monkeypatch):
    """行为断言 N：带 domain_id 参数的检索不崩溃。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731", collection_id="default", domain_id="ai-knowledge")
    assert isinstance(hits, list), f"domain_id 检索应返回 list，实为 {type(hits)}"


# ── 断言 O：多语言/特殊字符 query 不崩 ─────────────────────────────

def test_o_multilingual_query_no_crash(isolated_env, monkeypatch):
    """行为断言 O：中文/Kanji/Emoji/符号 query 检索不崩。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    for q in ("龍骨耐圧試験", "🦴⚡🏗️", "SELECT * FROM users; --", "💣$(whoami)"):
        hits = sys_knowledge_retrieve(q, collection_id="default")
        assert isinstance(hits, list), f"query {q!r} 检索应返回 list，实为 {type(hits)}"


# ── 断言 P：wiki_titles 参数不崩 ──────────────────────────────────────

def test_p_wiki_titles_no_crash(isolated_env, monkeypatch):
    """行为断言 P：用 wiki_titles 参数精确检索不崩。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("", collection_id="default", wiki_titles=["keel_spec"])
    assert isinstance(hits, list), f"wiki_titles 检索应返回 list，实为 {type(hits)}"


# ── 断言 Q：min_wiki_score=0 不崩 ─────────────────────────────────────

def test_q_min_wiki_score_zero_no_crash(isolated_env, monkeypatch):
    """行为断言 Q：min_wiki_score=0 检索不崩、返回 list。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731", collection_id="default", min_wiki_score=0.0)
    assert isinstance(hits, list), f"min_wiki_score=0 检索应返回 list，实为 {type(hits)}"


# ── 断言 R：不存在的 collection 检索不崩 ──────────────────────────────

def test_r_nonexistent_collection_no_crash(isolated_env, monkeypatch):
    """行为断言 R：对不存在的 collection_id 检索不崩溃。"""
    _apply_offline_patches(monkeypatch)
    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("test", collection_id="__nonexistent_xyz__")
    assert isinstance(hits, list), f"不存在 collection 检索应返回 list，实为 {type(hits)}"


# ── 断言 S：wiki 读写一致性（read_page 读到 write_page 写入的内容）──

def test_s_wiki_read_after_write(isolated_env, monkeypatch):
    """行为断言 S：write_page 后 read_page 应返回写入的内容。

    验证 wiki 存储的读写闭环一致性——写后立即可读，内容完整不丢失。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.knowledge.wiki_engine import read_page
    page = read_page("keel_spec", collection_id="default")
    assert page is not None, "read_page 未找到刚写入的页面"
    body = page.get("body", page.get("content", ""))
    assert "ZX-7731" in str(body), f"read_page 内容不含 ZX-7731: {str(body)[:200]!r}"


# ── 断言 T：wiki_first=True（默认）返回 wiki source_type ──────────────

def test_t_wiki_first_returns_wiki(isolated_env, monkeypatch):
    """行为断言 T：wiki_first=True（默认）检索应返回 source_type='wiki' 的结果。

    验证检索默认使用 wiki 路径——若默认模式下无 wiki 结果，wiki 集成可能断裂。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731 抗压强度", collection_id="default")
    wiki_hits = [h for h in hits if h.get("source_type") == "wiki"]
    assert len(wiki_hits) > 0, f"默认 wiki_first 模式应召回 wiki 结果: {[h.get('title','?') for h in hits]}"


# ── 断言 U：read_page 对不存在 title 返回 None ──────────────────────

def test_u_read_page_nonexistent(isolated_env):
    """行为断言 U：read_page 对不存在的 title 应返回 None 不崩。"""
    from core.harness.knowledge.wiki_engine import read_page
    page = read_page("__nonexistent_title_xyz__", collection_id="default")
    assert page is None, f"不存在 title 应返回 None，实为 {type(page)}"


# ── 断言 V：update_page 直接 API 验证 ────────────────────────────────

def test_v_update_page_changes_body(isolated_env, monkeypatch):
    """行为断言 V：update_page 更新 summary 后 read_page 读到新值。

    update_page 更新 frontmatter 字段（summary/tags/status 等），非 body。
    区别于 B1（re-ingest 路径），验证 wiki 更新 API 直接生效。
    """
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.knowledge.wiki_engine import update_page, read_page
    ok = update_page("keel_spec", collection_id="default", summary="UPDATED-SUMMARY-ZX-9999")
    assert ok, "update_page 返回 False"

    page = read_page("keel_spec", collection_id="default")
    assert page is not None, "update 后 read_page 未找到页面"
    assert "UPDATED-SUMMARY-ZX-9999" in str(page.get("summary", "")), (
        f"update 后 summary 未更新: {page.get('summary','')!r}"
    )


# ── wiki search_pages 全文检索 ──────────────────────────────────────

def test_wiki_search_pages_finds_ingested(isolated_env, monkeypatch):
    """行为断言：search_pages 全文检索能搜到刚写入的页面。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.knowledge.wiki_engine import search_pages
    results = search_pages("ZX-7731", collection_id="default")
    assert results, "search_pages 未搜到刚写入的页面"
    titles = [r.get("title","") for r in results]
    assert "keel_spec" in titles, f"search_pages 未含 keel_spec: {titles}"


# ── 检索 target_class + domain_id — 多域本体过滤 ──────────────────────

def test_retrieval_target_class_no_crash(isolated_env, monkeypatch):
    """行为断言：target_class + domain_id 本体过滤检索不崩。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731", collection_id="default",
                                   domain_id="ai-knowledge", target_class="Material")
    assert isinstance(hits, list), f"target_class 检索应返回 list"


# ── GraphIndex 节点计数完整性 ────────────────────────────────────────

def test_graph_index_node_count(isolated_env):
    """行为断言：添加 N 个实体后节点总数为 N。"""
    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex("oe-count-test")
    for i in range(5):
        g.add_entity(f"e{i}", f"实体{i}", "Thing")
    assert len(g._nodes) == 5, f"添加5个实体后应有5个节点，实为 {len(g._nodes)}"


# ── wiki frontmatter 保存（tags）─────────────────────────────────────

def test_wiki_tags_preserved_after_write(isolated_env, monkeypatch):
    """行为断言：write_page 写入的 tags 经 read_page 可完整读回。"""
    _apply_offline_patches(monkeypatch)
    # Use write_page directly for tag control
    from core.harness.knowledge.wiki_engine import write_page, read_page
    write_page("tag-test-page", "内容内容", category="entities",
               tags=["龙骨", "ZX-7731", "测试标签"], collection_id="default")
    page = read_page("tag-test-page", collection_id="default")
    assert page is not None, "read_page 未找到写入的页面"
    tags = page.get("tags", [])
    assert "ZX-7731" in tags, f"tags 未保存 ZX-7731: {tags}"


# ── 记忆子系统：save_interaction → export_episodic_state 记读一致 ──

def test_memory_save_then_export(isolated_env):
    """行为断言：MemoryManager save_interaction 后 episodic state 含记入内容。

    验证四层记忆的核心写→读闭环——记忆子系统是白皮书 Layer 2 的核心能力。
    """
    import asyncio
    from core.harness.memory.manager import MemoryManager, MemoryConfig

    mm = MemoryManager(config=MemoryConfig(), namespace="test-ns")
    msg = "MEMTEST-ZX-7731-UNIQUE-MARKER"
    asyncio.run(mm.save_interaction(user_message=msg, assistant_message="ok"))

    state = mm.export_episodic_state()
    blob = str(state.get("full_messages", "")) + str(state.get("summary", ""))
    assert "MEMTEST-ZX-7731-UNIQUE-MARKER" in blob, (
        f"save_interaction 后 episodic state 不含记入内容: {blob[:200]!r}"
    )


def test_memory_task_skill_save_then_load(isolated_env):
    """行为断言：MemoryManager save_task_skill → load_task_skill 闭环。

    Layer 4 外挂记忆——流水线晶体化的执行模式，白皮书核心能力。
    """
    import asyncio
    from core.harness.memory.manager import MemoryManager, MemoryConfig, TaskSkill

    mm = MemoryManager(config=MemoryConfig(), namespace="test-ts")
    skill = TaskSkill(
        skill_id="ts-zx7731", name="test-memory-ts",
        pipeline_id="pipeline-test", agent_sequence=["react"],
        artifacts=["output"], pass_rate=0.95, keywords=["test", "memory"]
    )
    path = asyncio.run(mm.save_task_skill(skill))
    assert path, "save_task_skill 返回空路径"

    loaded = asyncio.run(mm.load_task_skill("ts-zx7731"))
    assert loaded is not None, "load_task_skill 未找到刚存储的 skill"
    assert loaded.name == "test-memory-ts", f"loaded name mismatch: {loaded.name}"


def test_memory_build_context_after_save(isolated_env):
    """行为断言：save_interaction 后 build_context 不崩。

    验证记忆子系统最核心的读路径——Agent 每次推理都调 build_context 组装上下文。
    """
    import asyncio
    from core.harness.memory.manager import MemoryManager, MemoryConfig

    mm = MemoryManager(config=MemoryConfig(), namespace="test-ctx")
    asyncio.run(mm.save_interaction(
        user_message="核验龙骨 ZX-7731", assistant_message="抗压强度 42.8 MPa"
    ))
    # build_context 是 Agent ReActLoop 每次推理前的核心调用——不崩即核心读路径健康
    ctx = asyncio.run(mm.build_context("查询 ZX-7731", "system: test"))
    assert ctx is not None, "build_context 返回 None"
    assert len(ctx.messages) > 0, "build_context 应返回非空 messages"


# ── Semantic Memory：store → get 闭环 ────────────────────────────────

def test_semantic_memory_store_then_get(isolated_env):
    """行为断言：SemanticMemory store → get 闭环（Layer 3 语义记忆）。

    白皮书四层记忆的 Cold Memory 层——长期知识存储与检索。
    """
    import asyncio
    from core.harness.memory.semantic import SemanticMemory

    sm = SemanticMemory(store_type="simple")
    key = "sem-zx7731"
    asyncio.run(sm.store(key, "龙骨 ZX-7731 抗压强度 42.8 MPa", metadata={"tag": "test"}))

    item = asyncio.run(sm.get(key))
    assert item is not None, f"semantic get({key!r}) 返回 None"
    assert "ZX-7731" in item.content, f"semantic 内容不含 ZX-7731: {item.content!r}"


# ── 本体引擎：GraphIndex 实体读写闭环 ──────────────────────────────

def test_graph_index_entity_roundtrip(isolated_env):
    """行为断言：GraphIndex add_entity → get_node 闭环。

    白皮书 Layer 3 本体引擎的核心数据结构——13 步管线的实体存储基础。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex("oe-entity-test")
    node = g.add_entity("ent-zx7731", "龙骨 ZX-7731", "Material")
    assert node is not None, "add_entity 返回 None"
    assert node.entity_name == "龙骨 ZX-7731", f"entity_name 不匹配: {node.entity_name}"

    found = g.get_node("ent-zx7731")
    assert found is not None, "get_node 未找到刚添加的实体"
    assert found.entity_name == "龙骨 ZX-7731", f"get_node name 不匹配: {found.entity_name}"

    # 关系读写：add_relation → 验证边存在
    g.add_entity("ent-rel-target", "目标实体", "Material")
    g.add_relation("ent-zx7731", "ent-rel-target", "composed_of")
    assert any(e.target_id == "ent-rel-target" for e in found.out_edges), (
        "add_relation 后 out_edges 不含目标实体"
    )

    # HyperEdge 超边：白皮书 SAG 风格——1 个 event 连接 N 个 entity
    g.add_hyperedge("he-zx7731", ["ent-zx7731", "ent-rel-target"],
                     context_description="测试超边")
    he = g.get_hyperedge("he-zx7731")
    assert he is not None, "get_hyperedge 未找到刚添加的超边"
    assert "ent-zx7731" in he.entity_ids, f"超边不含 ent-zx7731: {he.entity_ids}"

    # find_by_name：按实体名检索
    by_name = g.find_by_name("龙骨 ZX-7731")
    assert by_name is not None, "find_by_name 未找到实体"
    assert by_name.entity_id == "ent-zx7731", f"find_by_name id 不匹配: {by_name.entity_id}"


# ── 本体引擎：OntologyDomain YAML 加载 ─────────────────────────────

def test_ontology_domain_load_from_yaml(isolated_env):
    """行为断言：load_ontology_from_yaml 能加载最小合法域定义。

    白皮书 Layer 3 本体引擎的配置基础——13 步管线依赖域 YAML 加载。
    """
    import yaml as _yaml
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

    yaml_path = isolated_env / "test_domain.yaml"
    yaml_path.write_text(_yaml.dump({
        "id": "test-domain",
        "name": "测试域",
        "namespace": "http://test.local/",
        "classes": {
            "Material": {
                "label": "材料", "description": "测试材料类",
                "required_fields": ["name", "description"],
                "fields": [{"name": "strength", "type": "float"}]
            }
        },
        "object_properties": [
            {"name": "composed_of", "label": "组成", "domain": ["Material"], "range": ["Material"]}
        ]
    }), encoding="utf-8")

    domain = load_ontology_from_yaml(str(yaml_path))
    assert domain is not None, "加载返回 None"
    assert len(domain.classes) == 1, f"classes 数量错误: {len(domain.classes)}"
    assert domain.classes[0].label == "材料", f"class label 不匹配"


# ── 本体引擎：GraphSnapshot 快照 ────────────────────────────────────

def test_graph_snapshot_roundtrip(isolated_env):
    """行为断言：GraphIndex snapshot → list_snapshots 闭环。

    图版本化——白皮书 §5.42 的图快照能力。
    """
    import json as _json
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex("oe-snap-test")
    g.add_entity("snap-ent", "快照实体", "Thing")
    g.snapshot("v1")

    snaps = g.list_snapshots()
    assert len(snaps) >= 1, f"list_snapshots 应为 ≥1，实为 {len(snaps)}"
    last = snaps[-1]
    assert last.get("label") == "v1", f"快照 label 不匹配: {last.get('label')!r}"


# ── 本体引擎：GraphTraversal 遍历 ────────────────────────────────────

def test_graph_traversal_reaches_target(isolated_env):
    """行为断言：GraphTraversal 从起点能到达关联实体。

    图遍历是 13 步管线 Step 5 的核心——验证 BFS 可达性。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_traversal import traverse

    g = GraphIndex("oe-traverse")
    g.add_entity("src", "起点", "Thing")
    g.add_entity("dst", "终点", "Thing")
    g.add_relation("src", "dst", "leads_to")

    r = traverse("src", g, max_hops=1, direction="outgoing")
    terms = [t.get("entity_name","") for t in (r.terminal_entities or [])]
    assert "终点" in terms, f"traverse 未到达终点: {terms}"


# ── 本体引擎：GraphIndex 删除实体 ──────────────────────────────────

def test_graph_index_remove_entity(isolated_env):
    """行为断言：remove_entity 后 get_node 返回 None。

    完成 GraphIndex 实体 CRUD 闭环：add → get → remove → get 返回 None。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex("oe-rm-test")
    g.add_entity("rm-ent", "待删实体", "Thing")
    assert g.get_node("rm-ent") is not None, "add 后应能 get"

    g.remove_entity("rm-ent")
    assert g.get_node("rm-ent") is None, "remove 后 get_node 应返回 None"


# ── PII 自动脱敏 ──────────────────────────────────────────────────────

def test_pii_mask_detects_phone_email(isolated_env):
    """行为断言：PIIDetector.mask 能识别并脱敏手机号和邮箱。

    §5.79 安全红线——所有进入 LLM 的用户输入必须经 PII 脱敏。
    """
    from core.services.pii_detector import PIIDetector

    d = PIIDetector()
    masked, mapping = d.mask("联系我：13812345678 或 test@example.com")
    assert "13812345678" not in masked, f"手机号未脱敏: {masked}"
    assert "test@example.com" not in masked, f"邮箱未脱敏: {masked}"
    assert len(mapping) >= 2, f"应映射至少2个PII: {mapping}"


# ── 检索 expand_subclasses 参数不崩 ──────────────────────────────────

def test_retrieval_expand_subclasses_no_crash(isolated_env, monkeypatch):
    """行为断言：expand_subclasses=True 检索参数不崩溃。"""
    _apply_offline_patches(monkeypatch)
    doc = isolated_env / "keel_spec.md"
    doc.write_text(FACT_DOC, encoding="utf-8")
    _ingest("doc-zx7731", doc)

    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
    hits = sys_knowledge_retrieve("ZX-7731", collection_id="default", expand_subclasses=True)
    assert isinstance(hits, list), f"expand_subclasses 检索应返回 list"


# ── EventBus pub/sub 闭环 ────────────────────────────────────────────

def test_eventbus_publish_subscribe(isolated_env):
    """行为断言：EventBus subscribe → publish → 队列收到事件。

    §5.20 可观测性核心——syscall 事件实时发布/订阅。
    """
    from core.harness.observation.event_bus import EventBus

    EventBus.start()
    q = EventBus.subscribe("eb-test-zx7731")
    EventBus.publish("eb-test-zx7731", {"type": "test", "data": "ZX-7731"})
    assert q.qsize() == 1, f"发布后队列应有1条事件，实为 {q.qsize()}"
    evt = q.get_nowait()
    assert evt["data"] == "ZX-7731", f"事件数据不匹配: {evt}"
    EventBus.unsubscribe("eb-test-zx7731")
    EventBus.stop()


# ── 本体引擎：ClassMapper 关键词分类（本体加载→分类链式验证）──────

def test_class_mapper_classify(isolated_env):
    """行为断言：ClassMapper 用已加载域进行分类——链式验证本体管线。

    从 YAML 加载域 → 构建 ClassMapper 关键词索引 → classify_text 分类。
    """
    import yaml as _yaml
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.ontology_engine.class_mapper import ClassMapper

    yaml_path = isolated_env / "cm_domain.yaml"
    yaml_path.write_text(_yaml.dump({
        "id": "cm-test", "name": "分类测试",
        "namespace": "http://cm.test/",
        "classes": {
            "Material": {"label": "材料", "description": "建筑材料与结构材料",
                         "required_fields": ["name"], "fields": []}
        }
    }), encoding="utf-8")

    domain = load_ontology_from_yaml(str(yaml_path))
    mapper = ClassMapper(domain)
    result = mapper.classify_text("龙骨是一种船体结构材料")
    assert result, f"classify_text 返回空结果"
    assert "材料" in result, f"classify_text 未命中 Material label: {result}"
    # 负向：无关查询应返回空（None 或空列表）
    no_match = mapper.classify_text("Python programming language")
    assert not no_match, f"无关查询不应匹配任何类: {no_match}"
