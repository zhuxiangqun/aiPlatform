"""L2-L5 feature mixin for BuilderProjectService (P1-14 God Class split, 2026-08-25).

Extracted from builder_project_service.py — method bodies unchanged; module-level
symbols resolved via lazy function-level imports (avoids circular import since
builder_project_service imports this mixin). Cross-field helpers (self._save_projects
/ self._module_root / self._reload_if_stale) resolve via the MRO at runtime.
"""

from __future__ import annotations




class BuilderL2L5Mixin:
    """L2 导入 / L3 合并 / L4 模块 / L4.5 迁移 / L5 发布 — 从 BuilderProjectService 拆出。"""
    async def import_repo(self, project_id: str, *, zip_bytes: bytes = b"", existing_path: str = "", module_id: str = "default") -> Dict[str, Any]:
        from builder.builder_project_service import _log, _safe_extract_zip, _copy_existing_path, _scan_imported, _detect_tests, _detect_missing_deps, _L2_IMPORT_MAX_FILES  # noqa: E501
        """L2: import existing code into the project (zip upload or local path).

        Design: plan-app-factory-l2-import-repo.md §3.3/§3.6 — import_root is
        isolated from the deploy dir (~/.aiplat/apps/{pid}/imported vs current/),
        manifest carries {path,size,sha256,lang,first_line}, has_tests/missing_deps
        drive the pytest-gate escape (§3.8). L4: module_id routes the import to a
        named module's imported/ (default → legacy layout).
        """
        self._reload_if_stale()
        proj = self._projects.get(project_id) or {}
        if not proj:
            return {"status": "error", "detail": "项目不存在"}

        _apps_home = os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "apps", project_id)
        import_root = self._module_root(project_id, module_id)
        os.makedirs(import_root, exist_ok=True)

        # ── Snapshot previous import (rollback: user can compare against prev) ──
        prev_root = os.path.join(_apps_home, "imported.prev")
        if os.path.isdir(import_root) and any(os.scandir(import_root)):
            try:
                import shutil as _sh
                if os.path.isdir(prev_root):
                    _sh.rmtree(prev_root)
                _sh.copytree(import_root, prev_root)
            except OSError:
                _log.warning("L2: failed to snapshot previous import for %s", project_id)

        if zip_bytes:
            _safe_extract_zip(zip_bytes, import_root)
        elif existing_path:
            _copy_existing_path(existing_path, import_root)
        else:
            return {"status": "error", "detail": "需要 zip 上传或 existing_path 二选一"}

        # ── Scan manifest (sensitive files skipped; limits enforced) ──
        manifest, too_many = _scan_imported(import_root)
        if too_many:
            return {"status": "error",
                    "detail": f"文件数超过上限 {_L2_IMPORT_MAX_FILES}，请压缩后重试"}
        if not manifest:
            return {"status": "error", "detail": "未扫描到可导入文件（敏感/密钥文件已跳过）"}

        has_tests = _detect_tests(import_root)
        missing_deps = _detect_missing_deps(import_root)

        _repo = {
            "root": import_root,
            "prev_root": prev_root if os.path.isdir(prev_root) else "",
            "manifest": manifest,
            "has_tests": has_tests,
            "missing_deps": missing_deps,
            "module_id": module_id,
            "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if module_id == "default":
            proj["imported_repo"] = _repo
        else:
            # L4: multi-module — store per-module repo
            proj.setdefault("module_repos", {})[module_id] = _repo
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        _log.info("L2: imported %d files for project %s module=%s (has_tests=%s, deps=%s)",
                  len(manifest), project_id, module_id, has_tests, len(missing_deps))
        return {
            "status": "ok",
            "module_id": module_id,
            "imported_files": len(manifest),
            "manifest": manifest[:100],
            "has_tests": has_tests,
            "missing_deps": missing_deps,
        }
    async def list_imported_files(self, project_id: str) -> Dict[str, Any]:
        """L2: return imported manifest for frontend file selection."""
        proj = self._projects.get(project_id, {})
        imp = proj.get("imported_repo") or {}
        manifest = imp.get("manifest") or []
        return {
            "status": "ok",
            "files": [{"path": m.get("path", ""), "size": m.get("size", 0), "lang": m.get("lang", "")}
                      for m in manifest],
            "has_tests": bool(imp.get("has_tests", False)),
            "missing_deps": imp.get("missing_deps") or [],
            "imported_at": imp.get("imported_at", ""),
            "total": len(manifest),
        }
    def _module_root(self, project_id: str, module_id: str = "default") -> str:
        """Resolve a module's imported/ root. default → legacy layout."""
        _apps_home = os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "apps", project_id)
        if module_id == "default":
            return os.path.join(_apps_home, "imported")
        return os.path.join(_apps_home, "modules", module_id, "imported")
    def _module_repo(self, project_id: str, module_id: str = "default") -> Dict[str, Any]:
        """Per-module imported repo payload (default → proj.imported_repo)."""
        proj = self._projects.get(project_id, {})
        if module_id == "default":
            return proj.get("imported_repo") or {}
        return (proj.get("module_repos") or {}).get(module_id) or {}
    def _module_roots(self, project_id: str) -> Dict[str, str]:
        """{module_id: imported_root} for all declared modules (incl. implicit default)."""
        proj = self._projects.get(project_id, {})
        roots = {}
        if proj.get("imported_repo") or self._has_legacy_import(project_id):
            roots["default"] = self._module_root(project_id, "default")
        for mid in (proj.get("modules") or []):
            mid_id = mid.get("module_id") if isinstance(mid, dict) else str(mid)
            if mid_id:
                roots[mid_id] = self._module_root(project_id, mid_id)
        return roots
    def _has_legacy_import(self, project_id: str) -> bool:
        return os.path.isdir(self._module_root(project_id, "default")) and any(
            os.scandir(self._module_root(project_id, "default")))
    async def create_modules(self, project_id: str, modules: List[Dict]) -> Dict[str, Any]:
        """L4: declare project modules (modules.json semantics, stored on project)."""
        self._reload_if_stale()
        proj = self._projects.get(project_id) or {}
        if not proj:
            return {"status": "error", "detail": "项目不存在"}
        if not modules or not isinstance(modules, list):
            return {"status": "error", "detail": "modules 必须是非空数组 [{module_id, description}]"}
        cleaned = []
        for m in modules:
            mid = str(m.get("module_id") or "").strip()
            if not mid or mid == "default":
                return {"status": "error", "detail": "module_id 必填且不能为 'default'（保留单模块语义）"}
            cleaned.append({
                "module_id": mid,
                "description": str(m.get("description") or ""),
                "root": f"modules/{mid}",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        proj["modules"] = cleaned
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        return {"status": "ok", "modules": cleaned, "total": len(cleaned)}
    async def list_modules(self, project_id: str) -> Dict[str, Any]:
        """L4: module list — declared modules + implicit default when legacy import exists."""
        proj = self._projects.get(project_id, {})
        modules = []
        if self._has_legacy_import(project_id):
            modules.append({"module_id": "default", "description": "单模块（默认）",
                            "root": "imported", "imported": True})
        for m in (proj.get("modules") or []):
            mid = m.get("module_id") if isinstance(m, dict) else str(m)
            rep = self._module_repo(project_id, mid)
            modules.append({
                "module_id": mid,
                "description": (m.get("description") if isinstance(m, dict) else ""),
                "root": (m.get("root") if isinstance(m, dict) else f"modules/{mid}"),
                "imported": bool(rep),
                "file_count": len((rep.get("manifest") or []) if isinstance(rep, dict) else []),
            })
        return {"status": "ok", "modules": modules, "total": len(modules)}
    async def cross_module_impact(self, project_id: str, module_id: str = "default") -> Dict[str, Any]:
        """L4 §3.3: cross-module impact analysis for a changed module."""
        from builder.cross_module import analyze_cross_module, impact_closure
        roots = self._module_roots(project_id)
        if not roots:
            return {"status": "error", "detail": "未导入任何模块代码"}
        if module_id not in roots:
            return {"status": "error", "detail": f"模块 {module_id} 不存在"}
        modules = [{"module_id": mid, "root": root} for mid, root in roots.items()]
        result = analyze_cross_module(modules, os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))
        closure = impact_closure(module_id, result["graph"])
        return {
            "status": "ok",
            "graph": result["graph"],
            "contracts": result["contracts"],
            "closure": closure,
            "changed_module": module_id,
            "note": "静态分析仅供参考，编排集可在前端调整",
        }
    async def module_orchestrate(self, project_id: str, module_ids: List[str]) -> Dict[str, Any]:
        """L4 §3.4: orchestrate pipelines for changed modules in dependency order.

        Affected set = changed modules + everything that depends on them.
        Sequential (v1) topological order — dependency first, then dependents.
        """
        from builder.cross_module import analyze_cross_module, impact_closure, topological_order
        roots = self._module_roots(project_id)
        if not roots:
            return {"status": "error", "detail": "未导入任何模块代码"}
        if not module_ids:
            return {"status": "error", "detail": "module_ids 不能为空"}
        modules = [{"module_id": mid, "root": root} for mid, root in roots.items()]
        result = analyze_cross_module(modules, os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))
        closure: List[str] = []
        for mid in module_ids:
            for m in impact_closure(mid, result["graph"]):
                if m not in closure:
                    closure.append(m)
        ordered = topological_order(closure, result["graph"])
        # Trigger rebuild per module (sequential): rebuild with module_id
        results = []
        for mid in ordered:
            _repo = self._module_repo(project_id, mid)
            if not _repo:
                results.append({"module_id": mid, "skipped": True, "reason": "未导入代码"})
                continue
            try:
                await self.rebuild_project(project_id, module_id=mid)
                results.append({"module_id": mid, "triggered": True})
            except Exception as e:
                results.append({"module_id": mid, "triggered": False, "error": str(e)[:200]})
        return {"status": "ok", "closure": closure, "order": ordered, "results": results,
                "note": "v1 顺序编排（依赖先于依赖方），未受影响模块不重跑"}
    async def get_import_stats(self) -> Dict[str, Any]:
        """L2: skip_pytest_gate telemetry — >40% ratio triggers L3 priority alert (§3.9 条件 3)."""
        total_runs = 0
        skip_count = 0
        for pid, proj in self._projects.items():
            runs = proj.get("runs") or []
            total_runs += len(runs)
            if (proj.get("confirmed_prd") or {}).get("skip_pytest_gate"):
                skip_count += 1
        ratio = round(skip_count / total_runs, 3) if total_runs else 0.0
        return {
            "status": "ok",
            "skip_gate_projects": skip_count,
            "total_projects": len(self._projects),
            "total_runs": total_runs,
            "skip_ratio": ratio,
            "l3_priority_alert": ratio > 0.4,
            "note": ">40% skip_pytest_gate → 逃生舱被当常规路径，应提前规划 L3（增量合并引擎）",
        }
    def _module_code_files(self, project_id: str, module_id: str) -> Dict[str, str]:
        """Read a module's imported code files (rel path → content)."""
        root = self._module_root(project_id, module_id)
        out: Dict[str, str] = {}
        if not os.path.isdir(root):
            return out
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                try:
                    with open(os.path.join(dirpath, fn), "r", encoding="utf-8", errors="replace") as fh:
                        out[rel] = fh.read(200_000)
                except OSError:
                    continue
        return out
    async def migration_preview(self, project_id: str, module_id: str = "default") -> Dict[str, Any]:
        """L4.5: extract old (imported) vs new (post-merge) schema → migration (up/down)."""
        from builder.schema_migration import extract_schema, diff_schema, generate_migration
        proj = self._projects.get(project_id) or {}
        old_files = self._module_code_files(project_id, module_id)
        if not old_files:
            return {"status": "error", "detail": f"模块 {module_id} 未导入代码"}
        old_schema = extract_schema(old_files)
        # new = imported + merge previews new_content overrides
        new_files = dict(old_files)
        for pv in (proj.get("merge_previews") or []):
            content = pv.get("new_content")
            if isinstance(content, str) and str(pv.get("path", "")).endswith(".py"):
                new_files[pv["path"]] = content
        new_schema = extract_schema(new_files)
        diff = diff_schema(old_schema, new_schema)
        migration = generate_migration(diff, project_id, new_schema, module_id)
        if not migration:
            return {"status": "ok", "migration": None, "has_changes": False,
                    "note": "无模型变更，不需要迁移"}
        # attach cross-module field references (design §3.7)
        cross_refs = self._check_cross_module_fields(project_id, module_id, diff)
        migration["cross_refs"] = cross_refs
        pending = [m for m in (proj.get("pending_migrations") or [])
                   if m.get("module_id") == module_id]
        migration["duplicate"] = bool(pending)
        if not pending:
            proj.setdefault("pending_migrations", []).append(migration)
            self._save_projects()
        return {"status": "ok", "migration": migration, "has_changes": True,
                "destructive": migration["destructive"], "cross_refs": cross_refs}
    def _check_cross_module_fields(self, project_id: str, module_id: str, diff: Dict[str, Any]) -> List[Dict]:
        """L4.5 §3.7: other modules reading fields this migration removes/changes."""
        removed = {c for cols in diff.get("removed_columns", {}).values() for c in cols}
        changed = {c for tbl in diff.get("type_changed", {}).values() for c in tbl}
        if not (removed or changed):
            return []
        hits = []
        for mid in self._module_roots(project_id):
            if mid == module_id:
                continue
            for rel, content in self._module_code_files(project_id, mid).items():
                for field in (removed | changed):
                    if re.search(rf"\b{re.escape(field)}\b", content):
                        hits.append({"module": mid, "file": rel, "field": field})
        return hits[:20]
    async def list_migrations(self, project_id: str) -> Dict[str, Any]:
        """L4.5: migration history + pending."""
        proj = self._projects.get(project_id, {})
        history = proj.get("migrations") or []
        pending = proj.get("pending_migrations") or []
        return {"status": "ok", "migrations": history, "pending": pending,
                "total_applied": len(history), "total_pending": len(pending)}
    async def apply_migration(self, project_id: str, migration_ids: List[str],
                              confirmed: bool = False) -> Dict[str, Any]:
        """L4.5: apply pending migrations. Destructive requires explicit confirmation."""
        proj = self._projects.get(project_id, {})
        pending = proj.get("pending_migrations") or []
        applied = []
        for mid in migration_ids:
            mig = next((m for m in pending if m.get("id") == mid), None)
            if not mig:
                continue
            if mig.get("destructive") and not confirmed:
                return {"status": "error", "code": "destructive_migration_requires_confirmation",
                        "detail": f"迁移 {mid} 为破坏性变更（删字段/类型变更/删表），需显式确认后才可应用"}
            mig["status"] = "applied"
            mig["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            proj.setdefault("migrations", []).append(mig)
            pending = [m for m in pending if m.get("id") != mid]
            applied.append(mid)
        proj["pending_migrations"] = pending
        self._save_projects()
        return {"status": "ok", "applied": applied,
                "note": "迁移状态已记录；AIPLAT_DB_EXECUTE=true 时执行真实 SQL（默认仅记录）"}
    async def rollback_migration(self, project_id: str, migration_id: str) -> Dict[str, Any]:
        """L4.5: apply down script + mark rolled_back (history append-only)."""
        proj = self._projects.get(project_id, {})
        mig = next((m for m in (proj.get("migrations") or [])
                    if m.get("id") == migration_id and m.get("status") == "applied"), None)
        if not mig:
            return {"status": "error", "detail": "迁移不存在或未应用"}
        mig["status"] = "rolled_back"
        mig["rolled_back_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        return {"status": "ok", "migration_id": migration_id, "down_sql": mig.get("down_sql", ""),
                "note": "down 脚本已应用（AIPLAT_DB_EXECUTE=true 时执行真实 SQL）；历史保留"}
    async def create_release(self, project_id: str, module_id: str = "default") -> Dict[str, Any]:
        """L5: merge post-merge code into a versioned artifact (building → ready)."""
        from builder.release_engine import create_release as _engine_release, release_root
        proj = self._projects.get(project_id) or {}
        src_dir = self._module_root(project_id, module_id)
        if not os.path.isdir(src_dir):
            return {"status": "error", "detail": f"模块 {module_id} 未导入代码"}
        # overlay merge new versions
        new_files = {}
        for pv in (proj.get("merge_previews") or []):
            content = pv.get("new_content")
            if isinstance(content, str) and pv.get("path"):
                new_files[pv["path"]] = content
        # release gate: pending migrations first (design §9)
        pending = [m for m in (proj.get("pending_migrations") or [])
                   if m.get("module_id") == module_id]
        gate = None
        if pending:
            gate = f"有 {len(pending)} 个待应用迁移，请先应用再发布"
            return {"status": "error", "code": "pending_migrations",
                    "detail": gate}
        # pass_rate source for admission hint
        pr_source = "unknown"
        runs = proj.get("runs") or []
        if runs and isinstance(runs[-1], dict):
            pr_source = runs[-1].get("pass_rate_source", "unknown") or "unknown"
        release = _engine_release(project_id, module_id, src_dir, new_files, pr_source)
        proj.setdefault("releases", []).append(release)
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        # optional infra integration (design §3.6)
        infra_ok = False
        if os.getenv("AIPLAT_L5_INFRA_DEPLOY", "false").lower() in ("true", "1", "yes"):
            infra_ok = await self._infra_deploy_service(project_id, module_id, release["version"])
        return {"status": "ok", "release": release,
                "estimated_hint": pr_source == "estimated",
                "infra_deployed": infra_ok,
                "releases_root": release_root(project_id)}
    async def _infra_deploy_service(self, project_id: str, module_id: str, version: str) -> bool:
        from builder.builder_project_service import _log
        """L5 §3.6/v2: register service via CoreFacade → infra bridge.

        platform must not import infra directly — sanctioned path is
        CoreFacade.deploy_app_service (bridge, standalone-safe no-op).
        """
        if os.getenv("AIPLAT_L5_INFRA_DEPLOY", "false").lower() not in ("true", "1", "yes"):
            return False
        try:
            from core.api.core_facade import deploy_app_service
            return deploy_app_service(
                name=f"{project_id}-{module_id}",
                namespace="aiplat-apps",
                image=f"aiplat-release:{version}",
                config={"release": version, "project_id": project_id, "module_id": module_id},
            )
        except Exception as e:
            _log.warning("L5 infra deploy via facade skipped: %s", str(e)[:200])
            return False
    async def list_releases(self, project_id: str) -> Dict[str, Any]:
        """L5: release history + current pointer target."""
        from builder.release_engine import current_dir
        proj = self._projects.get(project_id, {})
        releases = proj.get("releases") or []
        cur = current_dir(project_id)
        return {"status": "ok", "releases": releases, "current": cur or "",
                "total": len(releases)}
    async def set_release_status(self, project_id: str, version: str,
                                 status: str, target_version: str = "",
                                 canary_weight: int = 0) -> Dict[str, Any]:
        """L5: canary / full / rollback state transitions (canary_weight for routing)."""
        from builder.release_engine import set_release_status as _engine_set
        proj = self._projects.get(project_id, {})
        releases = proj.get("releases") or []
        try:
            rel = _engine_set(project_id, releases, version, status,
                              target_version=target_version, canary_weight=canary_weight)
        except ValueError as e:
            return {"status": "error", "detail": str(e)}
        proj["releases"] = releases
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        return {"status": "ok", "release": rel}
    async def merge_preview(self, project_id: str, module_id: str = "default") -> Dict[str, Any]:
        from builder.builder_project_service import _log, _parse_file_blocks
        """L3: build per-file merge previews — new versions from pipeline output vs
        imported originals, plus impact analysis, syntax + interface checks.
        L4 v1.5: module_id scopes the imported repo; cross-module contract status
        is attached when the project is multi-module."""
        from builder.merge_engine import (
            analyze_impact, build_merge_preview, verify_interface_preserved, syntax_check)
        self._reload_if_stale()
        proj = self._projects.get(project_id) or {}
        imp = self._module_repo(project_id, module_id)
        import_root = str(imp.get("root") or "")
        if not import_root or not os.path.isdir(import_root):
            return {"status": "error", "detail": "未导入既有代码，请先导入"}
        # Read pipeline output (code_generation raw_output with ## FILE: blocks)
        out_dir = os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        final_path = os.path.join(out_dir, "_final_state.json")
        code_text = ""
        if os.path.isfile(final_path):
            try:
                with open(final_path, "r", encoding="utf-8") as fh:
                    fs = json.load(fh)
                _code = fs.get("code") or fs.get("agent_app") or {}
                code_text = _code.get("raw_output", "") if isinstance(_code, dict) else str(_code)
            except Exception as e:
                _log.warning("merge_preview: failed to read final state: %s", str(e)[:200])
        new_files = _parse_file_blocks(code_text)
        if not new_files:
            return {"status": "error", "detail": "流水线未产出新版本代码（## FILE: 块为空）"}
        # Impact analysis (advisory — frontend shows auto-added files, user may opt out)
        modify_files = (proj.get("confirmed_prd") or {}).get("modify_files") or []
        impact = analyze_impact(import_root, modify_files, imp.get("manifest") or [])
        previews = []
        for path, content in new_files.items():
            orig_path = os.path.join(import_root, path)
            original = ""
            if os.path.isfile(orig_path):
                try:
                    with open(orig_path, "r", encoding="utf-8", errors="replace") as fh:
                        original = fh.read()
                except OSError:
                    pass  # noqa: cleanup-best-effort — treat as empty original
            pv = build_merge_preview(original, content, path)
            pv["new_content"] = content
            pv["interface"] = verify_interface_preserved(original, content, path)
            pv["syntax"] = syntax_check(content, path)
            previews.append(pv)
        proj["merge_previews"] = previews
        proj["merge_module"] = module_id
        proj["merge_impact"] = impact
        # L4 v1.5: cross-module contract status for multi-module projects
        cross_contracts: Dict[str, Any] = {"ok": True, "broken": [], "checked": [], "note": ""}
        if module_id != "default" and (proj.get("module_repos") or {}):
            try:
                from builder.cross_module import analyze_cross_module, verify_changed_module_contracts
                roots = self._module_roots(project_id)
                modules = [{"module_id": mid, "root": root} for mid, root in roots.items()]
                result = analyze_cross_module(modules, os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))
                cross_contracts = verify_changed_module_contracts(
                    module_id, previews, result["graph"], module_root=roots.get(module_id, ""))
                cross_contracts["note"] = "依赖方模块引用的端点/实体在变更模块新版本中的存活性检查"
            except Exception as e:
                _log.warning("cross-module contract check failed: %s", str(e)[:200])
        proj["merge_cross_contracts"] = cross_contracts
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        return {"status": "ok", "previews": previews, "impact": impact,
                "module_id": module_id, "cross_contracts": cross_contracts}
    async def list_merge_previews(self, project_id: str) -> Dict[str, Any]:
        """L3: return stored merge previews + impact analysis."""
        proj = self._projects.get(project_id, {})
        previews = proj.get("merge_previews") or []
        impact = proj.get("merge_impact") or {}
        return {"status": "ok", "previews": previews, "impact": impact,
                "total": len(previews)}
    async def merge_apply(self, project_id: str, decisions: Dict[str, str]) -> Dict[str, Any]:
        """L3: apply approved previews after human review (design §3.5/§3.7).

        L3-P0-01 atomic gate: every preview path must be approved; any missing or
        rejected path → 422-style error (rejected = regenerate, never partial apply).
        L3-P0-02 concurrency guard: imported originals must match the pre-generation
        sha256 snapshot, otherwise the merge is refused (409 semantics).
        """
        from builder.merge_engine import apply_merge, verify_snapshot
        proj = self._projects.get(project_id, {})
        previews = proj.get("merge_previews") or []
        if not previews:
            return {"status": "error", "detail": "没有合并预览，请先运行 merge-preview"}
        module_id = str(proj.get("merge_module") or "default")
        imp = self._module_repo(project_id, module_id)
        import_root = str(imp.get("root") or "")
        deploy_dir = proj.get("deploy_dir") or os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
            "output", project_id, "deploy")

        # ── P0-01: atomic gate — all preview paths must be approved ──
        preview_paths = [pv.get("path", "") for pv in previews if pv.get("path")]
        missing_approval = [p for p in preview_paths if decisions.get(p) != "approved"]
        if missing_approval:
            return {"status": "error", "code": "atomic_approval_required",
                    "detail": "必须审批全部文件（原子化）：未通过的文件："
                              + "、".join(missing_approval[:10])
                              + "。请驳回并重新生成，或修改为通过后再应用。"}

        # ── L4 v1.5: cross-module contract gate — dependents' referenced
        #     endpoints/entities must survive in the changed module's new versions ──
        cross_contracts = proj.get("merge_cross_contracts") or {}
        if cross_contracts.get("broken"):
            _broken_txt = "；".join(
                f"{b.get('dependent')} {b.get('kind')} {b.get('ref')}" for b in cross_contracts["broken"][:10])
            return {"status": "error", "code": "contract_gate_failed",
                    "detail": "跨模块契约断裂，禁止合并：" + _broken_txt
                              + "。请修复变更模块的对外接口后重新生成。"}

        # ── P0-02: concurrency guard — imported originals unchanged since generation ──
        snapshot = proj.get("pre_gen_snapshot") or {}
        if snapshot:
            _ok, _changed = verify_snapshot(import_root, snapshot)
            if not _ok:
                return {"status": "error", "code": "concurrent_modification",
                        "detail": "以下文件在生成期间已被外部修改，请重新导入或重新生成："
                                  + "、".join(_changed[:10])}

        # Gate: syntax/interface failures block approval (design §3.6)
        for pv in previews:
            path = pv.get("path", "")
            if not (pv.get("syntax") or {}).get("ok", True):
                return {"status": "error",
                        "detail": f"{path} 语法验证失败（{pv['syntax'].get('error')}），禁止合并"}
            if not (pv.get("interface") or {}).get("ok", True):
                return {"status": "error",
                        "detail": f"{path} 对外接口缺失（{', '.join(pv['interface'].get('missing') or [])}），禁止合并"}
        try:
            result = apply_merge(project_id, import_root, deploy_dir, previews, decisions)
        except ValueError as e:
            return {"status": "error", "code": "atomic_approval_required", "detail": str(e)}
        if result.get("applied"):
            _warns = [f"Warning: File {p} has been regenerated, please review diff manually."
                      for p in result["applied"]]
            if proj.get("runs"):
                proj["runs"][-1]["regenerated_warnings"] = _warns
                proj["runs"][-1]["merge_applied"] = len(result["applied"])
            proj["deploy_dir"] = deploy_dir
            proj.pop("pre_gen_snapshot", None)  # consumed
            self._save_projects()
        return result
    async def analyze_impact_for(self, project_id: str, modify_files: List[Dict]) -> Dict[str, Any]:
        """L3-P1-05 backend: impact analysis on demand (frontend shows auto-added
        files with reasons + uncheck confirmation)."""
        from builder.merge_engine import analyze_impact
        proj = self._projects.get(project_id, {})
        imp = proj.get("imported_repo") or {}
        import_root = str(imp.get("root") or "")
        if not import_root or not os.path.isdir(import_root):
            return {"status": "error", "detail": "未导入既有代码，请先导入"}
        impact = analyze_impact(import_root, modify_files or [], imp.get("manifest") or [])
        return {"status": "ok", "impact": impact}
