"""platform_status_brief — deterministic inventory for 小朱 consultant."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


def test_brief_lists_agents_and_skills(tmp_path, monkeypatch):
    home = tmp_path / "aiplat"
    (home / "agents" / "factory_agent").mkdir(parents=True)
    (home / "agents" / "factory_agent" / "AGENT.md").write_text(
        "---\nname: factory_agent\ndisplay_name: 应用工厂\n---\n",
        encoding="utf-8",
    )
    (home / "skills" / "capability_scout").mkdir(parents=True)
    (home / "skills" / "capability_scout" / "SKILL.md").write_text(
        "---\nname: capability_scout\n---\n",
        encoding="utf-8",
    )
    (home / "teams").mkdir(parents=True)
    (home / "teams" / "default.yaml").write_text(
        "team_name: t\nstages:\n  - agent_id: pm_agent\n    order: 0\n",
        encoding="utf-8",
    )
    (home / "apps" / "prj_demo" / "current").mkdir(parents=True)
    (home / "ontologies").mkdir(parents=True)
    (home / "ontologies" / "registry.json").write_text(
        '{"domains": {"demo-domain": {}}}',
        encoding="utf-8",
    )
    (home / "teams" / "code.yaml").write_text("team_name: code\nstages: []\n", encoding="utf-8")
    (home / "wiki" / "collections" / "default").mkdir(parents=True)
    (home / "wiki" / "collections" / "default" / "intro.md").write_text("# hi\n", encoding="utf-8")
    (home / "projects.json").write_text(
        '{"projects":[{"project_id":"prj_demo","name":"演示工厂项目"}]}',
        encoding="utf-8",
    )
    (home / "datasources").mkdir(parents=True)
    (home / "datasources" / "mysql_inventory.yaml").write_text("kind: mysql\n", encoding="utf-8")
    (home / "profiles").mkdir(parents=True)
    (home / "profiles" / "poc-general.yaml").write_text("name: poc\n", encoding="utf-8")
    (home / "mcp").mkdir(parents=True)
    (home / "mcp" / "feishu_server.yaml").write_text("name: feishu\n", encoding="utf-8")
    import sqlite3

    db = home / "aiplat_executions.sqlite3"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE adapters (adapter_id TEXT, name TEXT, provider TEXT, "
        "status TEXT, models_json TEXT)"
    )
    con.execute(
        "INSERT INTO adapters VALUES (?,?,?,?,?)",
        ("local-scan:ollama:qwen2.5:3b", "q", "ollama", "active", '[{"name":"qwen2.5:3b"}]'),
    )
    con.execute(
        "INSERT INTO adapters VALUES (?,?,?,?,?)",
        ("adapter-ds", "ds", "deepseek", "active", '[{"name":"deepseek-chat"}]'),
    )
    con.execute(
        "CREATE TABLE prompt_templates (template_id TEXT, name TEXT, template TEXT)"
    )
    con.execute(
        "INSERT INTO prompt_templates VALUES (?,?,?)",
        ("tpl_demo", "演示模板", "SECRET_BODY_MUST_NOT_APPEAR"),
    )
    con.execute(
        "CREATE TABLE jobs (id TEXT, name TEXT, enabled INTEGER, cron TEXT, kind TEXT, target_id TEXT, payload_json TEXT)"
    )
    con.execute(
        "INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
        ("job1", "nightly_eval", 1, "0 2 * * *", "skill", "eval_skill", '{"secret":"JOB_PAYLOAD"}'),
    )
    con.execute("CREATE TABLE job_runs (id TEXT)")
    con.execute("INSERT INTO job_runs VALUES ('r1')")
    con.execute(
        "CREATE TABLE approval_requests (request_id TEXT, operation TEXT, status TEXT, details TEXT)"
    )
    con.execute(
        "INSERT INTO approval_requests VALUES (?,?,?,?)",
        ("req1", "skill:autoreview", "pending", "APPROVAL_SECRET"),
    )
    con.execute(
        "CREATE TABLE agent_executions ("
        "id TEXT, agent_id TEXT, status TEXT, input_json TEXT, "
        "error_code TEXT, created_at REAL)"
    )
    con.execute(
        "INSERT INTO agent_executions VALUES (?,?,?,?,?,?)",
        ("e1", "pm_agent", "completed", "EXEC_SECRET", "", 1.0),
    )
    con.execute(
        "INSERT INTO agent_executions VALUES (?,?,?,?,?,?)",
        ("e2", "orchestrator", "failed", "FAIL_IO_SECRET", "empty_output", 2.0),
    )
    con.execute(
        "CREATE TABLE skill_executions ("
        "id TEXT, skill_id TEXT, status TEXT, input_json TEXT, "
        "error_code TEXT, created_at REAL)"
    )
    con.execute(
        "INSERT INTO skill_executions VALUES (?,?,?,?,?,?)",
        ("s1", "capability_scout", "error", "SKILL_IO_SECRET", "timeout", 3.0),
    )
    con.execute("CREATE TABLE memory_sessions (id TEXT)")
    con.execute("INSERT INTO memory_sessions VALUES ('s1')")
    con.execute("CREATE TABLE long_term_memories (id TEXT, content TEXT)")
    con.execute("INSERT INTO long_term_memories VALUES ('m1', 'LTM_SECRET')")
    con.execute(
        "CREATE TABLE plugins (plugin_id TEXT, name TEXT, version TEXT, enabled INTEGER, manifest_json TEXT)"
    )
    con.execute(
        "INSERT INTO plugins VALUES (?,?,?,?,?)",
        ("p_demo", "demo", "1.0.0", 1, "MANIFEST_SECRET"),
    )
    con.execute("CREATE TABLE traces (trace_id TEXT, status TEXT)")
    con.execute("INSERT INTO traces VALUES ('t1', 'completed')")
    con.execute("CREATE TABLE tenant_policies (tenant_id TEXT, policy_json TEXT)")
    con.execute("INSERT INTO tenant_policies VALUES ('tn1', 'POLICY_SECRET')")
    con.execute(
        "CREATE TABLE audit_logs (id INTEGER, action TEXT, status TEXT, detail_json TEXT)"
    )
    con.execute(
        "INSERT INTO audit_logs VALUES (?,?,?,?)",
        (1, "execute_agent", "ok", "AUDIT_DETAIL_SECRET"),
    )
    con.execute(
        "CREATE TABLE session_queue (id TEXT, kind TEXT, status TEXT, payload_json TEXT)"
    )
    con.execute(
        "INSERT INTO session_queue VALUES (?,?,?,?)",
        ("q1", "skill", "dequeued", "QUEUE_SECRET"),
    )
    con.commit()
    con.close()
    (home / "credentials.json").write_text(
        '[{"id":"c1","name":"oss_ak","key":"CRED_SECRET_KEY","provider":"aliyun","tool_name":"oss"}]',
        encoding="utf-8",
    )
    (home / "variables.json").write_text(
        '[{"id":"v1","name":"TENANT","value":"VAR_SECRET_VAL","scope":"global"}]',
        encoding="utf-8",
    )
    (home / "memory").mkdir(parents=True)
    (home / "memory" / "MEMORY.md").write_text("# notes\n", encoding="utf-8")
    (home / "packages" / "registry" / "starter").mkdir(parents=True)
    (home / "auto_pipelines").mkdir(parents=True)
    (home / "auto_pipelines" / "abc123.json").write_text(
        '{"keywords":["巡检报障"],"agent_sequence":["pm_agent"]}',
        encoding="utf-8",
    )
    (home / "eval_sets" / "default").mkdir(parents=True)
    (home / "eval_sets" / "default" / "high_risk.json").write_text("[]", encoding="utf-8")
    (home / "eval_results").mkdir(parents=True)
    (home / "eval_results" / "run1.json").write_text("{}", encoding="utf-8")
    (home / "actions").mkdir(parents=True)
    (home / "actions" / "bell24_actions.yaml").write_text(
        'actions:\n  - action_id: "bell_deploy_ai_agent"\n',
        encoding="utf-8",
    )
    (home / "kb" / "tenants" / "default").mkdir(parents=True)
    (home / "fde-manuals").mkdir(parents=True)
    (home / "fde-manuals" / "政务_demo-current.md").write_text("# m\n", encoding="utf-8")
    (home / "org").mkdir(parents=True)
    (home / "org" / "goals.json").write_text(
        '{"pilot": {}, "goals": [{"goal_id": "g1", "title": "开放告警SLA"}]}',
        encoding="utf-8",
    )
    (home / "org" / "approval_rules.yaml").write_text("rules: []\n", encoding="utf-8")
    (home / "file_checkpoints" / "sessA").mkdir(parents=True)
    (home / "learning" / "results" / "demo_student").mkdir(parents=True)
    (home / "finetune_data").mkdir(parents=True)
    (home / "finetune_data" / "demo_sft.jsonl").write_text('{"text":"FT_SAMPLE_SECRET"}\n', encoding="utf-8")
    (home / "model_quality").mkdir(parents=True)
    (home / "model_quality" / "probe_demo.json").write_text('{"score":1}\n', encoding="utf-8")
    import sqlite3 as _sq

    cg = home / "cap_graph.db"
    ccon = _sq.connect(str(cg))
    ccon.execute("CREATE TABLE cap_nodes (id TEXT)")
    ccon.execute("INSERT INTO cap_nodes VALUES ('n1')")
    ccon.execute("CREATE TABLE cap_edges (id TEXT)")
    ccon.execute("INSERT INTO cap_edges VALUES ('e1')")
    ccon.commit()
    ccon.close()
    ot = home / "ontology_triples.sqlite3"
    ocon = _sq.connect(str(ot))
    ocon.execute("CREATE TABLE triples (s TEXT, p TEXT, o TEXT)")
    ocon.execute("INSERT INTO triples VALUES ('a','b','TRIPLE_SECRET')")
    ocon.commit()
    ocon.close()
    wq = home / "wiki_quality.sqlite3"
    wcon = sqlite3.connect(str(wq))
    wcon.execute(
        "CREATE TABLE wiki_quality_alerts (page_title TEXT, collection_id TEXT, explanation TEXT)"
    )
    wcon.execute(
        "INSERT INTO wiki_quality_alerts VALUES (?,?,?)",
        ("intro", "default", "WIKI_EXPL_SECRET"),
    )
    wcon.commit()
    wcon.close()
    (home / "decision_traces").mkdir(parents=True)
    (home / "decision_traces" / "t1.json").write_text('{"secret":"TRACE_BODY_SECRET"}', encoding="utf-8")
    (home / "governance_cycles").mkdir(parents=True)
    (home / "governance_cycles" / "gov-cycle-demo-domain-1001.json").write_text(
        '{"secret":"GOV_BODY_SECRET"}', encoding="utf-8"
    )
    (home / "awareness_logs").mkdir(parents=True)
    (home / "awareness_logs" / "awareness_log_2026-10-06.jsonl").write_text(
        '{"secret":"AWARE_SECRET"}\n', encoding="utf-8"
    )
    (home / "evolution").mkdir(parents=True)
    (home / "evolution" / "last_run.json").write_text(
        '{"date":"2026-10-06","status":"completed","step_count":3,"detail":"EVO_SECRET"}',
        encoding="utf-8",
    )
    (home / "experience_feedback.json").write_text(
        '[{"rule_id":"architecture-guard-fail","status":"pending","content":"EXP_CONTENT_SECRET"}]',
        encoding="utf-8",
    )
    (home / "diagrams").mkdir(parents=True)
    (home / "diagrams" / "login_flow.xml").write_text("<mx>DIAGRAM_SECRET</mx>", encoding="utf-8")
    (home / "prd_gates").mkdir(parents=True)
    (home / "prd_gates" / "media.yaml").write_text("gate: media\n", encoding="utf-8")
    (home / "ontology_gen" / "ai-knowledge").mkdir(parents=True)
    (home / "optimizations").mkdir(parents=True)
    (home / "optimizations" / "materials_chat.yaml").write_text("name: materials_chat\n", encoding="utf-8")
    (home / "acceptance").mkdir(parents=True)
    (home / "acceptance" / "pack1.json").write_text('{"body":"ACCEPT_SECRET"}', encoding="utf-8")
    cg = home / "code_graph.db"
    cgcon = sqlite3.connect(str(cg))
    cgcon.execute("CREATE TABLE files (path TEXT)")
    cgcon.execute("INSERT INTO files VALUES ('a.py')")
    cgcon.execute("CREATE TABLE symbols (name TEXT)")
    cgcon.execute("INSERT INTO symbols VALUES ('Foo')")
    cgcon.execute("INSERT INTO symbols VALUES ('Bar')")
    cgcon.execute("CREATE TABLE edges (src TEXT, dst TEXT)")
    cgcon.commit()
    cgcon.close()
    plat = home / "data" / "aiplat_platform.sqlite3"
    plat.parent.mkdir(parents=True, exist_ok=True)
    pcon = sqlite3.connect(str(plat))
    pcon.execute(
        "CREATE TABLE auth_users (username TEXT, role TEXT, status TEXT, data_json TEXT)"
    )
    pcon.execute(
        "INSERT INTO auth_users VALUES (?,?,?,?)",
        ("alice", "admin", "active", "USER_JSON_SECRET"),
    )
    pcon.execute(
        "CREATE TABLE api_keys (key_hash TEXT, key_prefix TEXT, active INTEGER)"
    )
    pcon.execute(
        "INSERT INTO api_keys VALUES (?,?,?)",
        ("HASH_SECRET_VALUE", "sk-test", 1),
    )
    pcon.commit()
    pcon.close()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db))
    monkeypatch.setenv("AIPLAT_PLATFORM_DB_PATH", str(plat))

    from core.harness.digital_human import platform_status_brief as brief_mod

    brief_mod.clear_brief_cache()

    text = brief_mod.build_platform_status_brief(
        page_context={"route": "/app/factory", "label": "应用工厂", "groupLabel": "AI 应用工厂"},
        force_refresh=True,
    )
    assert "factory_agent" in text
    assert "应用工厂" in text
    assert "capability_scout" in text
    assert "pm_agent" in text
    assert "prj_demo" in text
    assert "demo-domain" in text
    assert "演示工厂项目" in text
    assert "code" in text
    assert "Wiki: 1 页 / 1 集合" in text
    assert "/app/factory" in text
    assert "/governance" in text
    assert "治理仪表盘" in text
    assert "当前页: 应用工厂" in text
    assert "这个画面" in text
    assert "禁止把简报里的全量 Agent/Skill 名单当成本页内容" in text
    assert "通用说明，非 aiPlat 既有" in text
    assert "做一个应用/产品" in text
    assert "不等于用户的应用已经交付" in text
    assert "Chat LLM" in text
    assert "unified_pipeline" in text
    assert "/infra/models" in text
    assert "qwen2.5:3b" in text
    assert "deepseek-chat" in text
    assert "mysql_inventory" in text
    assert "poc-general" in text
    assert "feishu_server" in text
    assert "starter" in text
    assert "巡检报障" in text
    assert "default/high_risk" in text
    assert "eval_results 1 份" in text
    assert "bell24_actions" in text
    assert "bell_deploy_ai_agent" in text
    assert "开放告警SLA" in text
    assert "引擎 Skill" in text
    assert "autoreview" in text
    assert "KB 租户" in text
    assert "FDE 手册 (1)" in text
    assert "政务" in text
    assert "pilot" in text
    assert "approval_rules.yaml" in text
    assert "tpl_demo" in text
    assert "演示模板" in text
    assert "SECRET_BODY_MUST_NOT_APPEAR" not in text
    assert "工作区记忆笔记: 1 个 md" in text
    assert "nightly_eval" in text
    assert "job_runs 1 条" in text
    assert "JOB_PAYLOAD" not in text
    assert "oss_ak" in text
    assert "CRED_SECRET_KEY" not in text
    assert "TENANT" in text
    assert "VAR_SECRET_VAL" not in text
    assert "skill:autoreview pending×1" in text
    assert "APPROVAL_SECRET" not in text
    assert "completed×1" in text
    assert "EXEC_SECRET" not in text
    assert "FAIL_IO_SECRET" not in text
    assert "SKILL_IO_SECRET" not in text
    assert "最近失败运行" in text
    assert "Agent:orchestrator" in text
    assert "Skill:capability_scout" in text
    assert "empty_output" in text
    assert "ModelManager" in text
    assert "LTM_SECRET" not in text
    assert "sessA" in text
    assert "demo_student" in text
    assert "p_demo" in text
    assert "MANIFEST_SECRET" not in text
    assert "POLICY_SECRET" not in text
    assert "completed×1" in text
    assert "租户策略记录: 1" in text
    assert "ollama/" in text or "ollama " in text
    assert "OPENAI_API_KEY" not in text
    assert "DEEPSEEK_API_KEY" not in text
    assert "execute_agent×1" in text or "execute_agent" in text
    assert "AUDIT_DETAIL_SECRET" not in text
    assert "skill/dequeued×1" in text
    assert "QUEUE_SECRET" not in text
    assert "sk-test" in text
    assert "HASH_SECRET_VALUE" not in text
    assert "alice" in text
    assert "USER_JSON_SECRET" not in text
    assert "demo_sft" in text
    assert "FT_SAMPLE_SECRET" not in text
    assert "probe_demo" in text
    assert "files 1" in text
    assert "symbols 2" in text
    assert "Graph 运行:" in text
    assert "引导证据:" in text
    assert "发布灰度:" in text
    assert "能力关系图: nodes 1, edges 1" in text
    assert "本体三元组: 1 条" in text
    assert "TRIPLE_SECRET" not in text
    assert "决策轨迹: 1 份" in text
    assert "TRACE_BODY_SECRET" not in text
    assert "Wiki 质量告警: 1 条" in text
    assert "WIKI_EXPL_SECRET" not in text
    assert "治理循环: 1 份" in text
    assert "demo-domain" in text
    assert "GOV_BODY_SECRET" not in text
    assert "觉察日志: 1 天" in text
    assert "AWARE_SECRET" not in text
    assert "自演进上次运行: 2026-10-06 / completed" in text
    assert "EVO_SECRET" not in text
    assert "architecture-guard-fail" in text
    assert "EXP_CONTENT_SECRET" not in text
    assert "login_flow" in text
    assert "DIAGRAM_SECRET" not in text
    assert "media" in text
    assert "ai-knowledge" in text
    assert "materials_chat" in text
    assert "验收包: 1 份" in text
    assert "ACCEPT_SECRET" not in text
    assert "能力图谱" not in text


def test_brief_explains_agents_screen_purpose(tmp_path, monkeypatch):
    home = tmp_path / "aiplat"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    from core.harness.digital_human import platform_status_brief as brief_mod

    brief_mod.clear_brief_cache()
    text = brief_mod.build_platform_status_brief(
        page_context={"route": "/workspace/agents", "label": "Agent", "groupLabel": "AI 应用工厂"},
        force_refresh=True,
    )
    assert "当前页: Agent (/workspace/agents)" in text
    assert "当前页功能:" in text
    assert "应用库 Agent" in text
    assert "不是整条工厂流水线" in text


def test_screen_deixis_omits_inventory_keeps_audit(tmp_path, monkeypatch):
    home = tmp_path / "aiplat"
    (home / "agents" / "factory_agent").mkdir(parents=True)
    (home / "agents" / "factory_agent" / "AGENT.md").write_text(
        "---\nname: factory_agent\n---\n", encoding="utf-8"
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    from core.harness.digital_human import platform_status_brief as brief_mod

    brief_mod.clear_brief_cache()
    assert brief_mod.refers_to_current_screen("根据这个画面的审核结果，我应该怎么做？")
    assert brief_mod.refers_to_current_screen("这个画面的功能是什么")
    assert not brief_mod.refers_to_current_screen("设备报修该怎么建")
    assert brief_mod.use_page_only_brief(
        "能不能把解读精简一点解释？",
        "skillId: upload_video；issue0: error/unrealized_side_effect 真上传",
    )
    assert not brief_mod.use_page_only_brief(
        "对象存储是什么？",
        "skillId: upload_video；issue0: error/unrealized_side_effect",
    )
    assert not brief_mod.use_page_only_brief(
        "平台选模是怎么走的？",
        "skillId: upload_video；issue0: error/unrealized_side_effect",
    )
    assert not brief_mod.use_page_only_brief(
        "我想做一个分析视频的应用，应该做 agent 还是应用工厂？",
        "skillId: upload_video；issue0: error/unrealized_side_effect",
    )
    text = brief_mod.build_platform_status_brief(
        page_context={
            "route": "/workspace/skills",
            "label": "Skill",
            "groupLabel": "AI 应用工厂",
            "purpose": "工作区 Skill：管理可复用技能，不是 Agent 列表。",
        },
        page_data=(
            "pageTitle: 编辑 Skill；skillId: upload_video；"
            "issue0: error/unrealized_side_effect SIDE_EFFECT_UNREALIZED；"
            "actions: 保存、AI 审核；totalAgents: 47"
        ),
        force_refresh=True,
        include_inventory=False,
    )
    assert "当前页功能:" in text
    assert "upload_video" in text
    assert "unrealized_side_effect" in text
    assert "factory_agent" not in text
    assert "工作区 Agent" not in text
    assert "totalAgents" not in text
    assert "47" not in text


def test_brief_cache_clears(tmp_path, monkeypatch):
    from core.harness.digital_human import platform_status_brief as brief_mod

    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "empty_home"))
    (tmp_path / "empty_home").mkdir()
    brief_mod.clear_brief_cache()
    a = brief_mod.build_platform_status_brief(force_refresh=True)
    brief_mod.clear_brief_cache()
    b = brief_mod.build_platform_status_brief(force_refresh=True)
    assert "工作区 Agent" in a
    assert "工作区 Agent" in b
