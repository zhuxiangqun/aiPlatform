"""Post-execution product-quality review (rule-based, no LLM).

Runtime "completed" ≠ content acceptable. Surfaces issues + where/how to fix
(usually Skill/Agent SOP) so management UI does not leave users with only
「已正常结束」.

One-click fix: appends idempotent SOP iron-law snippets into SKILL.md body
(same pattern as workspace apply-lint-fix `_sop_append`).
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.management.asset_audit import summarize_audit_issues

logger = logging.getLogger(__name__)

# Idempotent SOP patches keyed by issue code (HTML comment markers).
_QUALITY_SOP_FIXES: Dict[str, Dict[str, str]] = {
    "missing_hard_constraint": {
        "fix_id": "eq_fix_hard_constraint",
        "marker": "<!-- eq_fix:missing_hard_constraint -->",
        "title": "硬约束原词保留",
        "chunk": (
            "<!-- eq_fix:missing_hard_constraint -->\n"
            "### 一键加固：硬约束原词保留\n"
            "- 客户口述硬约束必须原词进入 `constraints` / `decisions`（如「不上公网」「不能传到公网」「照片不外传」「钉钉 API 未开放」）。\n"
            "- 禁止弱化为笼统「合规检查」「安全要求」。\n"
            "- 自检：输入中出现的硬约束短语，输出全文必须可检索到等价原词（「不上公网」或「照片不外传」或「不能传到公网」任一即可）。\n"
        ),
    },
    "soft_acceptance_criteria": {
        "fix_id": "eq_fix_soft_ac",
        "marker": "<!-- eq_fix:soft_acceptance_criteria -->",
        "title": "禁止软验收标准",
        "chunk": (
            "<!-- eq_fix:soft_acceptance_criteria -->\n"
            "### 一键加固：禁止软 AC\n"
            "- `acceptance_criteria` 必须可验证（能量化尽量量化；否则写清可观察结果）。\n"
            "- 禁止：「可以查看」「可以通过看板查看」「通过看板查看」「能通过系统查看」「上传成功」「能正确上传」「返回成功提示」「审批成功提示」「清晰可见」「功能正常」「能正常使用」「实际操作测试」「操作成功」「正确无误」。\n"
        ),
    },
    "invented_nfr": {
        "fix_id": "eq_fix_invented_nfr",
        "marker": "<!-- eq_fix:invented_nfr -->",
        "title": "禁止编造 NFR",
        "chunk": (
            "<!-- eq_fix:invented_nfr -->\n"
            "### 一键加固：禁止编造未口述 NFR\n"
            "- 未口述的数量级 / 本地服务器 / P95 / 多语言等，禁止写成正式方案。\n"
            "- 未知项写入 `open_questions`，或标「待确认 / 待压测」。\n"
            "- performance 只许转述口述并标注待确认。\n"
        ),
    },
    "empty_open_questions_on_draft": {
        "fix_id": "eq_fix_open_questions",
        "marker": "<!-- eq_fix:empty_open_questions_on_draft -->",
        "title": "草稿轮 open_questions 非空",
        "chunk": (
            "<!-- eq_fix:empty_open_questions_on_draft -->\n"
            "### 一键加固：草稿轮 open_questions 禁止空\n"
            "- 输入含「未定 / 未开放 / 希望 / 预算 / 编制未 / 暂时没有 / 待确认」时，`open_questions` 必须非空。\n"
            "- 至少列入：钉钉 API、预算/编制、其它口述未知项。\n"
            "- 仅用户确认定稿后才允许 `open_questions: []`。\n"
        ),
    },
    "premature_prd_ready": {
        "fix_id": "eq_fix_prd_ready",
        "marker": "<!-- eq_fix:premature_prd_ready -->",
        "title": "草稿轮禁止 PRD_READY",
        "chunk": (
            "<!-- eq_fix:premature_prd_ready -->\n"
            "### 一键加固：草稿轮禁止 PRD_READY\n"
            "- 仍有未决信息时禁止输出 `PRD_READY` / `<!-- PRD_READY -->`。\n"
            "- 待 `open_questions` 可关闭后再定稿。\n"
        ),
    },
    "constraints_thin": {
        "fix_id": "eq_fix_constraints_thin",
        "marker": "<!-- eq_fix:constraints_thin -->",
        "title": "补齐 constraints 结构",
        "chunk": (
            "<!-- eq_fix:constraints_thin -->\n"
            "### 一键加固：constraints 须含 performance + security\n"
            "- `constraints` 必须结构化写出 performance 与 security（勿只写功能 AC）。\n"
            "- 客户已声明的硬约束必须原样保留。\n"
        ),
    },
    "constraint_bucket_mismatch": {
        "fix_id": "eq_fix_constraint_bucket",
        "marker": "<!-- eq_fix:constraint_bucket_mismatch -->",
        "title": "constraints 分桶",
        "chunk": (
            "<!-- eq_fix:constraint_bucket_mismatch -->\n"
            "### 一键加固：performance / security 分桶\n"
            "- `constraints.performance` 只写时延/吞吐/试点节奏等性能项（可标「待压测」）。\n"
            "- 「不上公网 / 照片不外传 / 加密」必须写在 `constraints.security`，禁止放进 performance。\n"
        ),
    },
    "pending_as_acceptance_criteria": {
        "fix_id": "eq_fix_pending_ac",
        "marker": "<!-- eq_fix:pending_as_acceptance_criteria -->",
        "title": "待确认项不得充当 AC",
        "chunk": (
            "<!-- eq_fix:pending_as_acceptance_criteria -->\n"
            "### 一键加固：待确认 ≠ 验收标准\n"
            "- 「钉钉 API 未开放 / 集成待确认 / 是否开放」写入 `open_questions` 或 `decisions=pending`，禁止当作 `acceptance_criteria`。\n"
            "- AC 必须是可判定通过/失败的观察结果（状态字段、返回字段、权限边界）。\n"
        ),
    },
    "insufficient_functional_requirements": {
        "fix_id": "eq_fix_fr_count",
        "marker": "<!-- eq_fix:insufficient_functional_requirements -->",
        "title": "FR 至少 3 条",
        "chunk": (
            "<!-- eq_fix:insufficient_functional_requirements -->\n"
            "### 一键加固：functional_requirements ≥ 3\n"
            "- `functional_requirements` 至少 3 条，每条含可验证 `acceptance_criteria`。\n"
            "- 覆盖主流程（上报/审批派修）、管理看板、集成边界等，勿合并成笼统 1～2 条。\n"
        ),
    },
    "out_of_scope_reopened": {
        "fix_id": "eq_fix_out_of_scope",
        "marker": "<!-- eq_fix:out_of_scope_reopened -->",
        "title": "明确不做不得再列入待确认",
        "chunk": (
            "<!-- eq_fix:out_of_scope_reopened -->\n"
            "### 一键加固：明确不做不进 open_questions\n"
            "- 客户「明确不做」的能力（如 OCR、语音转写）写入 `decisions` 为不做，禁止再问「是否需要」。\n"
            "- `open_questions` 只列真正未决项（API/预算/编制等）。\n"
            "- 禁止把「明确不做」写成 `functional_requirements` / 正向 AC。\n"
        ),
    },
    "out_of_scope_as_feature": {
        "fix_id": "eq_fix_out_of_scope",
        "marker": "<!-- eq_fix:out_of_scope_reopened -->",
        "title": "明确不做不得写成功能需求",
        "chunk": (
            "<!-- eq_fix:out_of_scope_reopened -->\n"
            "### 一键加固：明确不做不进 open_questions\n"
            "- 客户「明确不做」的能力（如 OCR、语音转写）写入 `decisions` 为不做，禁止再问「是否需要」。\n"
            "- `open_questions` 只列真正未决项（API/预算/编制等）。\n"
            "- 禁止把「明确不做」写成 `functional_requirements` / 正向 AC。\n"
        ),
    },
    "constraint_as_functional_requirement": {
        "fix_id": "eq_fix_constraint_as_fr",
        "marker": "<!-- eq_fix:constraint_as_functional_requirement -->",
        "title": "约束不得冒充 FR",
        "chunk": (
            "<!-- eq_fix:constraint_as_functional_requirement -->\n"
            "### 一键加固：constraints ≠ functional_requirements\n"
            "- 「不上公网 / 照片不外传 / 试点周期 / 明确不做」写入 `constraints` / `decisions`，禁止单独占一条 FR。\n"
            "- FR 只写可交付能力：上报、审批派修、管理看板等，每条含可验证 AC。\n"
        ),
    },
    "missing_core_flow_fr": {
        "fix_id": "eq_fix_core_flow_fr",
        "marker": "<!-- eq_fix:missing_core_flow_fr -->",
        "title": "主流程 FR 覆盖",
        "chunk": (
            "<!-- eq_fix:missing_core_flow_fr -->\n"
            "### 一键加固：主流程 FR 必须覆盖\n"
            "- 输入含拍照/上报、审批/派修、看板/报障量时，`functional_requirements` 必须分别覆盖，禁止用安全约束条顶替上报 FR。\n"
            "- 推荐 AC：`status=pending_approval` / `assigned`+`repair_task_id` / `ticket_count`+`avg_close_hours`。\n"
        ),
    },
    "fr_without_ac": {
        "fix_id": "eq_fix_fr_ac",
        "marker": "<!-- eq_fix:fr_without_ac -->",
        "title": "每条 FR 必须有 AC",
        "chunk": (
            "<!-- eq_fix:fr_without_ac -->\n"
            "### 一键加固：FR 必须带 acceptance_criteria\n"
            "- 每条 `functional_requirements` 必须有非空 `acceptance_criteria` 数组；禁止把 AC 写进 name/description 后留空 AC。\n"
            "- AC 须可判定（如 `status=pending_approval`、`repair_task_id` 非空、`ticket_count`/`avg_close_hours`）。\n"
        ),
    },
    "missing_required_ac_tokens": {
        "fix_id": "eq_fix_fr_ac",
        "marker": "<!-- eq_fix:fr_without_ac -->",
        "title": "AC 须含输入要求的可判定字段",
        "chunk": (
            "<!-- eq_fix:fr_without_ac -->\n"
            "### 一键加固：FR 必须带 acceptance_criteria\n"
            "- 每条 `functional_requirements` 必须有非空 `acceptance_criteria` 数组；禁止把 AC 写进 name/description 后留空 AC。\n"
            "- AC 须可判定（如 `status=pending_approval`、`repair_task_id` 非空、`ticket_count`/`avg_close_hours`）。\n"
        ),
    },
    "public_cloud_photo_storage": {
        "fix_id": "eq_fix_arch_no_public_photo",
        "marker": "<!-- eq_fix:public_cloud_photo_storage -->",
        "title": "照片禁止公有云/公网存储",
        "chunk": (
            "<!-- eq_fix:public_cloud_photo_storage -->\n"
            "### 一键加固：照片不上公网 → 禁止公有云对象存储\n"
            "- 输入含「不上公网 / 不可上公网 / 照片不外传」时，存储选型禁止：阿里云 OSS、腾讯云 COS、七牛、AWS S3、公有云对象存储。\n"
            "- 须写内网/私有化落地（私有桶、VPC 内 MinIO/本地盘等），并在假设中标明钉钉 API 未开放时不编造对接细节。\n"
        ),
    },
    "invented_third_party_api": {
        "fix_id": "eq_fix_arch_no_invent_api",
        "marker": "<!-- eq_fix:invented_third_party_api -->",
        "title": "禁止编造未给定的第三方接口细节",
        "chunk": (
            "<!-- eq_fix:invented_third_party_api -->\n"
            "### 一键加固：无 API 文档时禁止编造第三方调用\n"
            "- 输入含「暂无 API 文档 / API 未开放 / 禁止编造」时：禁止写「发送至钉钉审批/派修/看板接口」等具体调用步骤。\n"
            "- 允许：组件 tech 标「钉钉 API（待确认）」；未知项写入 `open_questions` / 假设「待确认」。\n"
            "- 数据流写到「待对接 / 占位通知通道」即可，勿假装已有钉钉业务 API。\n"
        ),
    },
    "architecture_sections_thin": {
        "fix_id": "eq_fix_arch_sections",
        "marker": "<!-- eq_fix:architecture_sections_thin -->",
        "title": "架构草稿须覆盖输入要求的章节",
        "chunk": (
            "<!-- eq_fix:architecture_sections_thin -->\n"
            "### 一键加固：架构输出覆盖评审章节\n"
            "- 输入要求「上下文与假设」时：必须输出非空字段 `context` 或 `assumptions`（或 `context_and_assumptions`），写明边界/假设/待确认；仅有 `open_questions` 不算覆盖该章节。\n"
            "- 输入要求「数据流 / 安全与合规 / 分期与风险」时，输出须有对应章节或等价字段，禁止只丢 components 清单。\n"
            "- 若输入含「6 周 / 试点 / 分期」，必须输出非空字段 `rollout_and_risks`（或 `phases`+`risks` / 中文键「分期切片与风险」），写明周次切片与风险；禁止省略。\n"
            "- API 契约须含方法/路径/请求响应要点；禁止编造未给定的第三方接口细节。\n"
            "- 输入要求上报/审批/派修/看板数据流时，data_flow 须覆盖四段业务，禁止只写「拍照上传」。\n"
            "- 输入要求安全与合规（落地/脱敏/内网）时，须有独立 security 叙述，禁止只用 overview 里的「安全性」一词冒充。\n"
            "- API 的 request/response 禁止占位空壳（如 body=「处理结果」/「照片数据」）；字段须可评审。\n"
            "- 输入要求标明待确认时，context/assumptions/open_questions 须含「待确认」类表述。\n"
        ),
    },
    "missing_auth_todo": {
        "fix_id": "eq_fix_missing_auth_todo",
        "marker": "<!-- eq_fix:missing_auth_todo -->",
        "title": "鉴权未给出须标 TODO",
        "chunk": (
            "<!-- eq_fix:missing_auth_todo -->\n"
            "### 一键加固：鉴权未给出须标 TODO\n"
            "- 输入写明「鉴权未给出 / 标 TODO」时，必须在 apiClient/fetch **代码行**写 "
            "`// TODO: auth`（TS）或 `# TODO: auth`（Python）；markdown「### TODO: auth」"
            "或正文「添加了 TODO」不算。\n"
            "- 禁止假实现「已对接钉钉 / DingTalk integrated」；未给出的鉴权细节只标 TODO。\n"
        ),
    },
    "dangling_local_import": {
        "fix_id": "eq_fix_dangling_local_import",
        "marker": "<!-- eq_fix:dangling_local_import -->",
        "title": "禁止悬空相对导入",
        "chunk": (
            "<!-- eq_fix:dangling_local_import -->\n"
            "### 一键加固：禁止悬空相对导入\n"
            "- `## FILE` 冒烟切片内禁止 `from './utils'` / `import '../helpers'` "
            "引用**未交付**文件。\n"
            "- **允许**交付物之间互相 import（如页面 import 同批交付的 "
            "`../types`、`../api/apiClient`）。\n"
            "- 辅助函数须内联，或另起 `## FILE:` 一并交付；外部包（如 axios）除外。\n"
        ),
    },
    "frontend_module_incomplete": {
        "fix_id": "eq_fix_frontend_module_incomplete",
        "marker": "<!-- eq_fix:frontend_module_incomplete -->",
        "title": "前端须交付可组装模块",
        "chunk": (
            "<!-- eq_fix:frontend_module_incomplete -->\n"
            "### 一键加固：前端可组装模块\n"
            "- 任务要求页面/组件时，禁止只交单个 `apiClient.ts`。\n"
            "- 至少 2 个 `## FILE`：类型或 API 客户端（`.ts`）+ 页面/组件（`.tsx`）。\n"
            "- types 字段与 JSX 必须写实：禁止 `// Define request fields here` / "
            "`// Render page content here` 空壳。\n"
            "- 页面只调用 apiClient；不要生成 Vite/`package.json`（属 scaffold）。\n"
        ),
    },
    "frontend_flow_pages_incomplete": {
        "fix_id": "eq_fix_frontend_flow_pages_incomplete",
        "marker": "<!-- eq_fix:frontend_flow_pages_incomplete -->",
        "title": "多流程前端须按流程分页面交付",
        "chunk": (
            "<!-- eq_fix:frontend_flow_pages_incomplete -->\n"
            "### 一键加固：多流程前端页面\n"
            "- PRD 含上报/审批/派修（或多流程）时，禁止压成单页单 POST。\n"
            "- 至少 3 个 `## FILE: frontend/src/pages/*.tsx`（每流程一页）。\n"
            "- `apiClient.ts` 须覆盖契约中每个 method+path；缺接口标 BLOCKED。\n"
            "- 可加 `components/`，但不能替代 pages。\n"
        ),
    },
    "isolated_fe_vite_files": {
        "fix_id": "eq_fix_isolated_fe_vite_files",
        "marker": "<!-- eq_fix:isolated_fe_vite_files -->",
        "title": "单独测切片不要交工程入口",
        "chunk": (
            "<!-- eq_fix:isolated_fe_vite_files -->\n"
            "### 一键加固：单独测禁止工程入口（所有 code Agent 共用）\n"
            "- 「单独测·可组装切片」只交任务列出的模块文件；前端=types+apiClient+pages，"
            "后端=routes+schemas。可加 components。\n"
            "- 禁止 `App.tsx` / `main.tsx` / `package.json` / `vite.config` / `index.html`"
            "（除非任务是「有脚手架挂路由」）。\n"
            "- 不要用 `npm run dev` / `uvicorn` 当单独测验收；工程骨架属 scaffold_agent。\n"
        ),
    },
    "scaffold_startup_incomplete": {
        "fix_id": "eq_fix_scaffold_startup_incomplete",
        "marker": "<!-- eq_fix:scaffold_startup_incomplete -->",
        "title": "脚手架须可启动前后端",
        "chunk": (
            "<!-- eq_fix:scaffold_startup_incomplete -->\n"
            "### 一键加固：可启动脚手架\n"
            "- 后端至少 `main.py` + `requirements.txt`（uvicorn 可起）。"
            "`.py` 文件 `\"\"\"` / `'''` 必须成对；禁止文件开头孤立三引号后直接 `import`。\n"
            "- 前端至少 Vite 入口链：`frontend/package.json`、`vite.config.ts`、"
            "`index.html`、`src/main.tsx`、`src/App.tsx`，以及 `frontend/tsconfig.json`"
            "（TS 骨架 / `tsc` build 必需）。禁止只交 README 占位。\n"
            "- 根 README 写清 `uvicorn` 与 `npm run dev`。\n"
            "- 「可启动」含落盘：Harness 把 `## FILE` 写入 "
            "`AIPLAT_HOME/run_workspaces/{run_id}/`（须在 "
            "`AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS` 内）；禁止只交观察区正文。\n"
        ),
    },
    "scaffold_not_on_disk": {
        "fix_id": "eq_fix_scaffold_not_on_disk",
        "marker": "<!-- eq_fix:scaffold_not_on_disk -->",
        "title": "可启动脚手架必须落到磁盘",
        "chunk": (
            "<!-- eq_fix:scaffold_not_on_disk -->\n"
            "### 一键加固：脚手架落盘\n"
            "- 可启动骨架在 `## FILE:` 交齐后必须写入运行工作区，"
            "不能只停在执行观察正文。\n"
            "- 落盘目录：`$AIPLAT_HOME/run_workspaces/{run_id}/`，"
            "且必须在 `AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS` 白名单内。\n"
            "- 不要把仓库根当输出目录；不要把「请用户自行复制」当完成。\n"
        ),
    },
    "broken_python_quotes": {
        "fix_id": "eq_fix_broken_python_quotes",
        "marker": "<!-- eq_fix:broken_python_quotes -->",
        "title": "Python 三引号必须成对",
        "chunk": (
            "<!-- eq_fix:broken_python_quotes -->\n"
            "### 一键加固：Python 三引号\n"
            "- 每个 `.py` 的 `\"\"\"` 与 `'''` 必须成对闭合。\n"
            "- 禁止文件第一行孤立 `\"\"\"` 后紧跟 `import` / `from` / `def`（整文件会变成字符串）。\n"
            "- 模块说明必须在第一处三引号内写完并闭合，再写 import。\n"
        ),
    },
    "fake_integration_claim": {
        "fix_id": "eq_fix_fake_integration_claim",
        "marker": "<!-- eq_fix:fake_integration_claim -->",
        "title": "禁止假对接声明",
        "chunk": (
            "<!-- eq_fix:fake_integration_claim -->\n"
            "### 一键加固：禁止假对接声明\n"
            "- 禁止写「已对接钉钉」等未给出细节的假集成；鉴权/SSO 未给出时只标 TODO。\n"
        ),
    },
    "undeclared_api_schema_assumption": {
        "fix_id": "eq_fix_undeclared_api_schema_assumption",
        "marker": "<!-- eq_fix:undeclared_api_schema_assumption -->",
        "title": "禁止一边「不推断」一边编 API 字段",
        "chunk": (
            "<!-- eq_fix:undeclared_api_schema_assumption -->\n"
            "### 一键加固：API 字段须标临时假设\n"
            "- 任务要求「不自行推断 API 格式」且 contracts 无字段级细节时，"
            "可写最小可运行 Request/Response，但必须在类型旁显式标注"
            "「临时假设 / ASSUMPTION / 以真实 contracts 覆盖」。\n"
            "- 禁止写「本文件不推断 API」同时又定义完整请求字段却无假设声明。\n"
        ),
    },
}


def quality_fix_catalog() -> Dict[str, Dict[str, str]]:
    """Public catalog for docs/tests."""
    return dict(_QUALITY_SOP_FIXES)


def _attach_quality_fix(issue: Dict[str, Any]) -> Dict[str, Any]:
    code = str(issue.get("code") or "").strip()
    # Map platform PRD gate codes onto nearest SOP fix when possible
    catalog_code = code if code in quality_fix_catalog() else ""
    if not catalog_code and (
        code.startswith("prd_")
        or code
        in (
            "missing_constraints",
            "missing_decisions",
            "constraints_thin",
        )
    ):
        catalog_code = "constraints_thin" if "constraint" in code or code.startswith("prd_") else ""
    if not catalog_code and code in ("fr_without_ac", "missing_required_ac_tokens"):
        catalog_code = "fr_without_ac"
    meta = quality_fix_catalog().get(catalog_code or code)
    if not meta:
        # Generic PRD gate → soft AC + open_questions bundle not auto-applied as one;
        # leave unfixable unless we have a match.
        issue["fix_available"] = False
        return issue
    issue["fix_available"] = True
    issue["fix"] = {
        "type": "apply_quality_sop_fix",
        "fix_id": meta["fix_id"],
        "issue_code": catalog_code or code,
        "auto_applicable": True,
        "title": meta["title"],
        "patch": {
            "format": "frontmatter_merge",
            "ops": [{"op": "upsert", "path": ["_sop_append"], "value": meta["chunk"]}],
        },
    }
    return issue


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "warning",
    suggestion: str = "",
    where: str = "",
    where_label: str = "",
    how: str = "",
) -> Dict[str, Any]:
    return _attach_quality_fix(
        {
            "code": code,
            "severity": severity,
            "category": "execution_quality",
            "message": message,
            "suggestion": suggestion,
            "where": where,
            "where_label": where_label,
            "how": how,
            "fix_available": False,
        }
    )


def apply_quality_sop_to_skill_md(
    skill_md_path: Path,
    *,
    issue_codes: Optional[Sequence[str]] = None,
    fix_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Append selected quality SOP snippets into SKILL.md / AGENT.md body (idempotent).

    Returns ``{status, applied, skipped, path, markers}``.
    """
    return apply_quality_sop_to_markdown(
        skill_md_path, issue_codes=issue_codes, fix_ids=fix_ids
    )


def apply_quality_sop_to_markdown(
    md_path: Path,
    *,
    issue_codes: Optional[Sequence[str]] = None,
    fix_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Append selected quality SOP snippets into a frontmatter markdown body (idempotent)."""
    path = Path(md_path)
    if not path.is_file():
        return {"status": "error", "error": f"markdown not found: {path}", "applied": [], "skipped": []}

    want_codes = {str(x).strip() for x in (issue_codes or []) if str(x).strip()}
    want_fix_ids = {str(x).strip() for x in (fix_ids or []) if str(x).strip()}
    if not want_codes and not want_fix_ids:
        return {
            "status": "error",
            "error": "issue_codes 或 fix_ids 必填（请从来自 quality_review 的可修复项传入）",
            "applied": [],
            "skipped": [],
            "path": str(path),
        }

    selected: List[Tuple[str, Dict[str, str]]] = []
    for code, meta in _QUALITY_SOP_FIXES.items():
        if code in want_codes or meta["fix_id"] in want_fix_ids:
            selected.append((code, meta))

    if not selected:
        return {
            "status": "noop",
            "applied": [],
            "skipped": [],
            "path": str(path),
            "message": "没有匹配的可写 SOP 加固项",
        }

    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return {"status": "error", "error": f"{path.name} missing frontmatter", "applied": [], "skipped": []}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {"status": "error", "error": f"{path.name} frontmatter malformed", "applied": [], "skipped": []}

    body = parts[2] or ""
    applied: List[str] = []
    skipped: List[str] = []
    for code, meta in selected:
        marker = meta["marker"]
        if marker in body:
            skipped.append(code)
            continue
        body = body.rstrip() + "\n\n" + meta["chunk"].strip() + "\n"
        applied.append(code)

    if not applied:
        return {
            "status": "noop",
            "applied": [],
            "skipped": skipped,
            "path": str(path),
            "message": "所选加固项已在 SOP 中，无需重复写入",
        }

    path.write_text(f"---{parts[1]}---\n{body.lstrip()}", encoding="utf-8")
    return {
        "status": "applied",
        "applied": applied,
        "skipped": skipped,
        "path": str(path),
        "markers": [_QUALITY_SOP_FIXES[c]["marker"] for c in applied],
        "message": f"已写入 {len(applied)} 条 SOP 铁律；请用同一用例再执行验证（勿把旧产物当通过）",
    }


def candidate_agent_md_paths(
    agent_id: str,
    *,
    primary: Optional[Path] = None,
) -> List[Path]:
    """~/.aiplat (+ AIPLAT_HOME) + engine/workspace seed AGENT.md mirrors."""
    import os

    aid = str(agent_id or "").strip()
    out: List[Path] = []
    if primary is not None:
        out.append(Path(primary))
    if aid:
        out.append(Path.home() / ".aiplat" / "agents" / aid / "AGENT.md")
        aiplat_home = str(os.environ.get("AIPLAT_HOME") or "").strip()
        if aiplat_home:
            out.append(Path(aiplat_home) / "agents" / aid / "AGENT.md")
        core_root = Path(__file__).resolve().parents[1]
        out.append(core_root / "workspace_seeds" / "agents" / aid / "AGENT.md")
        out.append(core_root / "engine" / "agents" / aid / "AGENT.md")
    seen = set()  # type: ignore[var-annotated]
    uniq: List[Path] = []
    for p in out:
        try:
            if not p.is_file():
                continue
            key = str(p.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        uniq.append(Path(key))
    return uniq


def apply_quality_sop_for_agent_id(
    agent_id: str,
    *,
    primary_path: Optional[Path] = None,
    issue_codes: Optional[Sequence[str]] = None,
    fix_ids: Optional[Sequence[str]] = None,
    bound_skill_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Write quality SOP into AGENT.md (LLM path) and bound Skill SKILL.md mirrors.

    Agent execute often does ReAct LLM without calling the Skill — Skill-only
    patches would never affect the next run. Always prefer AGENT.md first.
    """
    paths = candidate_agent_md_paths(agent_id, primary=primary_path)
    results: List[Dict[str, Any]] = []
    applied_codes: List[str] = []
    skipped_codes: List[str] = []
    wrote_paths: List[str] = []

    if not paths and not (bound_skill_ids or []):
        return {
            "status": "error",
            "error": f"AGENT.md not found for agent_id={agent_id}",
            "applied": [],
            "skipped": [],
            "paths": [],
            "results": [],
        }

    for p in paths:
        r = apply_quality_sop_to_markdown(p, issue_codes=issue_codes, fix_ids=fix_ids)
        results.append(r)
        if r.get("status") == "applied":
            wrote_paths.append(str(r.get("path") or p))
            for c in r.get("applied") or []:
                if c not in applied_codes:
                    applied_codes.append(str(c))
        for c in r.get("skipped") or []:
            if c not in skipped_codes and c not in applied_codes:
                skipped_codes.append(str(c))

    # Mirror onto bound skills (architecture_design etc.) — Skill SOP remains SSOT for skill runs
    for sid in bound_skill_ids or []:
        sid_s = str(sid or "").strip()
        if not sid_s:
            continue
        sk = apply_quality_sop_for_skill_id(
            sid_s, issue_codes=issue_codes, fix_ids=fix_ids
        )
        results.append({"skill_id": sid_s, **sk})
        if sk.get("status") == "applied":
            for pth in sk.get("paths") or ([sk.get("path")] if sk.get("path") else []):
                if pth and str(pth) not in wrote_paths:
                    wrote_paths.append(str(pth))
            for c in sk.get("applied") or []:
                if c not in applied_codes:
                    applied_codes.append(str(c))
        for c in sk.get("skipped") or []:
            if c not in skipped_codes and c not in applied_codes:
                skipped_codes.append(str(c))

    if applied_codes:
        return {
            "status": "applied",
            "applied": applied_codes,
            "skipped": [c for c in skipped_codes if c not in applied_codes],
            "paths": wrote_paths or [str(p) for p in paths],
            "path": wrote_paths[0] if wrote_paths else (str(paths[0]) if paths else None),
            "results": results,
            "message": (
                f"已写入 AGENT.md / Skill 共 {len(applied_codes)} 类铁律；"
                "请用同一用例再执行（LLM 直出读 AGENT.md，Skill 路径读 SKILL.md）"
            ),
        }
    if skipped_codes:
        return {
            "status": "noop",
            "applied": [],
            "skipped": skipped_codes,
            "paths": [str(p) for p in paths] + wrote_paths,
            "path": str(paths[0]) if paths else None,
            "results": results,
            "message": "所选加固项已在 AGENT.md / Skill SOP 中，无需重复写入",
        }
    err = next((r.get("error") for r in results if r.get("status") == "error"), None)
    return {
        "status": "error",
        "error": err or f"AGENT.md not found for agent_id={agent_id}",
        "applied": [],
        "skipped": [],
        "paths": [str(p) for p in paths],
        "results": results,
    }


def resolve_skill_md_path(skill: Any) -> Optional[Path]:
    """Best-effort SKILL.md path from skill object / metadata."""
    if skill is None:
        return None
    md = getattr(skill, "metadata", None)
    if not isinstance(md, dict):
        md = skill.get("metadata") if isinstance(skill, dict) else None
    if isinstance(md, dict):
        fs = md.get("filesystem") if isinstance(md.get("filesystem"), dict) else {}
        p = fs.get("skill_md") or md.get("skill_md") or ""
        if p and Path(str(p)).is_file():
            return Path(str(p))
        sop = md.get("sop_markdown_path") or ""
        if sop and Path(str(sop)).is_file():
            return Path(str(sop))
    return None


def candidate_skill_md_paths(
    skill_id: str,
    *,
    primary: Optional[Path] = None,
) -> List[Path]:
    """Engine + ~/.aiplat (+ AIPLAT_HOME) mirrors for the same skill_id."""
    import os

    sid = str(skill_id or "").strip()
    out: List[Path] = []
    if primary is not None:
        out.append(Path(primary))
    if sid:
        core_root = Path(__file__).resolve().parents[1]  # .../core
        out.append(core_root / "engine" / "skills" / sid / "SKILL.md")
        out.append(Path.home() / ".aiplat" / "skills" / sid / "SKILL.md")
        aiplat_home = str(os.environ.get("AIPLAT_HOME") or "").strip()
        if aiplat_home:
            out.append(Path(aiplat_home) / "skills" / sid / "SKILL.md")
    # de-dupe existing files
    seen = set()  # type: ignore[var-annotated]
    uniq: List[Path] = []
    for p in out:
        try:
            if not p.is_file():
                continue
            key = str(p.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        uniq.append(Path(key))
    return uniq


# Banner injected into next-run input when SOP iron is already present but product still fails.
FAIL_CONSTRAINT_BANNER = "[质量门禁失败点 — 本轮必须遵守，勿重复上次错误]"

# Semantic fallback when HTML comment marker was never written but SOP already says the iron.
_SOP_COVER_PHRASES: Dict[str, Tuple[str, ...]] = {
    "invented_third_party_api": ("禁止编造", "未给定的接口", "暂无 API 文档"),
    "public_cloud_photo_storage": ("禁止", "公有云对象存储", "不上公网"),
    "architecture_sections_thin": ("上下文与假设", "分期与风险", "open_questions"),
    "missing_hard_constraint": ("硬约束必须原词", "不上公网"),
}


def _sop_already_covers(code: str, bodies: Sequence[str]) -> bool:
    meta = _QUALITY_SOP_FIXES.get(code) or {}
    marker = str(meta.get("marker") or "")
    title = str(meta.get("title") or "").strip()
    for b in bodies:
        if marker and marker in b:
            return True
        if title and title in b:
            return True
    phrases = _SOP_COVER_PHRASES.get(code) or ()
    if not phrases:
        return False
    for b in bodies:
        if all(p in b for p in phrases):
            return True
    return False

_ARCH_QUALITY_CODES = frozenset(
    {
        "architecture_sections_thin",
        "public_cloud_photo_storage",
        "invented_third_party_api",
        "architecture_template_echo",
    }
)

_KNOWN_QUALITY_SKILL_IDS = (
    "architecture_design",
    "requirement_analysis",
    "security_evidence",
)


def resolve_quality_fix_skill_id(
    *,
    kind: str,
    asset_id: str = "",
    hints: str = "",
    issues: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """Best-effort Skill id that owns SOP iron for these quality issues."""
    if str(kind or "").lower() == "skill":
        return str(asset_id or "").strip()
    codes = {str(i.get("code") or "") for i in (issues or [])}
    if codes & _ARCH_QUALITY_CODES:
        return "architecture_design"
    h = str(hints or "")
    for known in _KNOWN_QUALITY_SKILL_IDS:
        if known in h:
            return known
    for token in re.findall(r"[a-z][a-z0-9_]{2,}", h.lower()):
        if token.endswith("_agent"):
            continue
        if candidate_skill_md_paths(token):
            return token
    return ""


def probe_quality_sop_markers(
    *,
    kind: str = "skill",
    asset_id: str = "",
    hints: str = "",
    issue_codes: Optional[Sequence[str]] = None,
    bound_skill_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Probe AGENT.md / SKILL.md for eq_fix markers of given issue codes.

    ``all_present`` is True when every catalogued code already has its marker
    in at least one checked markdown (idempotent one-click would be noop).
    """
    codes: List[str] = []
    seen_c = set()
    for c in issue_codes or []:
        cs = str(c or "").strip()
        if not cs or cs in seen_c:
            continue
        if cs not in _QUALITY_SOP_FIXES:
            continue
        seen_c.add(cs)
        codes.append(cs)

    bodies: List[str] = []
    paths_checked: List[str] = []

    def _read(p: Path) -> None:
        try:
            bodies.append(p.read_text(encoding="utf-8"))
            paths_checked.append(str(p))
        except Exception:
            return

    skill_ids: List[str] = []
    for sid in bound_skill_ids or []:
        s = str(sid or "").strip()
        if s and s not in skill_ids:
            skill_ids.append(s)

    k = str(kind or "").lower()
    if k == "skill":
        aid = str(asset_id or "").strip()
        if aid and aid not in skill_ids:
            skill_ids.insert(0, aid)
    else:
        aid = str(asset_id or "").strip()
        if aid:
            for p in candidate_agent_md_paths(aid):
                _read(p)
        resolved = resolve_quality_fix_skill_id(
            kind=kind, asset_id=asset_id, hints=hints, issues=[{"code": c} for c in codes]
        )
        if resolved and resolved not in skill_ids:
            skill_ids.append(resolved)
        h = str(hints or "")
        for known in _KNOWN_QUALITY_SKILL_IDS:
            if known in h and known not in skill_ids:
                skill_ids.append(known)

    for sid in skill_ids:
        for p in candidate_skill_md_paths(sid):
            _read(p)

    present: List[str] = []
    missing: List[str] = []
    for code in codes:
        if _sop_already_covers(code, bodies):
            present.append(code)
        else:
            missing.append(code)

    return {
        "present_codes": present,
        "missing_codes": missing,
        "all_present": bool(codes) and not missing,
        "paths_checked": paths_checked,
        "skill_ids": skill_ids,
    }


def build_fail_constraint_overlay(issues: Optional[Sequence[Dict[str, Any]]] = None) -> str:
    """Compact fail-point constraints to prepend on the next same-case run.

    Keep short: long overlays stall local LLMs and invite echo (run-30e631 / run-2ebd).
    Never include a copyable lone-endpoint JSON/dict example.
    """
    lines: List[str] = [FAIL_CONSTRAINT_BANNER]
    n = 0
    codes_seen: List[str] = []
    msgs: List[str] = []
    for issue in issues or []:
        sev = str(issue.get("severity") or "").lower()
        if sev not in ("error", "warning", ""):
            continue
        msg = str(issue.get("message") or "").strip()
        if not msg:
            continue
        code = str(issue.get("code") or "").strip()
        # Skip pure runtime empties — overlay won't help
        if code in ("empty_output", "runtime_timeout", "runtime_failed"):
            continue
        n += 1
        msgs.append(msg)
        if code and code not in codes_seen:
            codes_seen.append(code)
        # One line per issue — drop multi-line「正确做法」to cut tokens
        short = msg if len(msg) <= 80 else (msg[:77] + "…")
        prefix = f"- [{code}] " if code else "- "
        lines.append(f"{prefix}{short}")
        if n >= 6:
            break
    if n == 0:
        return ""
    joined = " ".join(msgs)
    arch_codes = {
        "architecture_sections_thin",
        "public_cloud_photo_storage",
        "invented_third_party_api",
        "architecture_template_echo",
    }
    is_arch = any(c in arch_codes for c in codes_seen) or ("完整架构" in joined)
    lone_api_prev = ("单个 API" in joined) or ("端点对象" in joined and "完整架构" in joined)
    if lone_api_prev:
        lines.insert(1, "【严禁复读】根对象须是完整架构 JSON，禁止只交单个 API 端点。")
    # Architect-only keys — never inject onto FE/BE coding agent reruns.
    if is_arch:
        lines.append(
            "【必含键】title、context/assumptions、components、data_flow、"
            "api_contracts(≥3)、security、rollout_and_risks(含 W1–W6)。"
            "api_contracts 只是字段之一。"
        )
    if "architecture_sections_thin" in codes_seen and any(
        "API" in str(i.get("message") or "") for i in (issues or [])
    ):
        lines.append(
            "【API】每项 method/path/request对象/response对象；覆盖上报·审批·派修·看板；禁空壳。"
        )
    if is_arch and any("按周" in m or "W1" in m or "分期" in m for m in msgs):
        lines.append("【分期】rollout_and_risks 写 W1–W6 可交付切片 + 风险，勿只写「一个车间」。")
    if "invented_third_party_api" in codes_seen:
        lines.append("【钉钉】tech=通知通道（钉钉·待确认）；禁止 SDK / 假装已有审批派修接口。")
    if "undeclared_api_schema_assumption" in codes_seen:
        lines.append(
            "【契约】types/apiClient 只用输入 api_contracts 已写明的字段；"
            "额外字段须在该 FILE 内标 ASSUMPTION/临时假设。"
        )
    if any(
        c
        in (
            "frontend_module_incomplete",
            "frontend_flow_pages_incomplete",
            "missing_auth_todo",
            "undeclared_api_schema_assumption",
            "language_mismatch",
            "dangling_local_import",
        )
        for c in codes_seen
    ):
        lines.append(
            "【交付】按原任务 ## FILE 清单交切片；禁止 Vite/package.json；页面禁止裸 fetch。"
        )
    lines.append("以上优先于模板；禁止公有云/编造接口绕过。")
    return "\n".join(lines)


def _looks_like_endpoint_example(text: str) -> bool:
    """True if text contains a copyable lone-endpoint shape (model echo bait)."""
    t = str(text or "")
    tl = t.lower().replace(" ", "")
    if '"method"' in tl and '"path"' in tl:
        return True
    if "method=post" in tl and "path=/api" in tl:
        return True
    if "{'method'" in tl or '{"method"' in tl:
        return True
    if "/api/tickets" in tl and ("request" in tl or "response" in tl):
        return True
    return False


def apply_quality_sop_for_skill_id(
    skill_id: str,
    *,
    primary_path: Optional[Path] = None,
    issue_codes: Optional[Sequence[str]] = None,
    fix_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Apply quality SOP patches to all known SKILL.md mirrors (idempotent)."""
    paths = candidate_skill_md_paths(skill_id, primary=primary_path)
    if not paths:
        return {
            "status": "error",
            "error": f"SKILL.md not found for skill_id={skill_id}",
            "applied": [],
            "skipped": [],
            "paths": [],
            "results": [],
        }

    results: List[Dict[str, Any]] = []
    applied_codes: List[str] = []
    skipped_codes: List[str] = []
    wrote_paths: List[str] = []
    for p in paths:
        r = apply_quality_sop_to_skill_md(p, issue_codes=issue_codes, fix_ids=fix_ids)
        results.append(r)
        if r.get("status") == "applied":
            wrote_paths.append(str(r.get("path") or p))
            for c in r.get("applied") or []:
                if c not in applied_codes:
                    applied_codes.append(str(c))
        for c in r.get("skipped") or []:
            if c not in skipped_codes and c not in applied_codes:
                skipped_codes.append(str(c))

    if any(r.get("status") == "error" and not wrote_paths for r in results) and not wrote_paths:
        # all errored
        err = next((r.get("error") for r in results if r.get("status") == "error"), "apply failed")
        return {
            "status": "error",
            "error": err,
            "applied": [],
            "skipped": skipped_codes,
            "paths": [str(p) for p in paths],
            "results": results,
        }

    if applied_codes:
        return {
            "status": "applied",
            "applied": applied_codes,
            "skipped": skipped_codes,
            "paths": wrote_paths or [str(p) for p in paths],
            "path": wrote_paths[0] if wrote_paths else str(paths[0]),
            "results": results,
            "message": (
                f"已写入 {len(applied_codes)} 类铁律到 {len(wrote_paths) or 1} 个 SKILL.md；"
                "请用同一用例再执行验证（旧产物不会自动变绿）"
            ),
        }

    return {
        "status": "noop",
        "applied": [],
        "skipped": skipped_codes,
        "paths": [str(p) for p in paths],
        "path": str(paths[0]),
        "results": results,
        "message": "所选加固项已在 SOP 中，无需重复写入",
    }


def _text_blob(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # Coding skill envelope: prefer raw code body over json.dumps so
        # ## FILE headers stay line-anchored for contract checks (run-1b2df4).
        code_v = obj.get("code")
        if isinstance(code_v, str) and code_v.strip():
            extra: List[str] = [code_v.strip()]
            for k in ("text", "markdown", "output", "answer", "content"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip() and v.strip() != code_v.strip():
                    extra.append(v.strip())
            return "\n".join(extra)
        # Common empty envelopes from stream upsert: {"text":""} / {"output":null}
        only_keys = set(obj.keys())
        if only_keys <= {"text", "output", "answer", "content", "response", "markdown"}:
            parts = []
            for k in ("text", "output", "answer", "content", "response", "markdown"):
                if k not in obj:
                    continue
                v = obj.get(k)
                if v is None:
                    continue
                if isinstance(v, str):
                    if v.strip():
                        parts.append(v.strip())
                elif isinstance(v, (dict, list)) and v:
                    parts.append(_text_blob(v))
                elif not isinstance(v, (dict, list)) and str(v).strip():
                    parts.append(str(v).strip())
            if not parts:
                return ""
            return "\n".join(parts)
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def _input_asks_for_deliverable(input_text: str) -> bool:
    """User asked for a concrete product (any Agent: PRD / architecture / code)."""
    t = str(input_text or "")
    if len(t.strip()) < 20:
        return False
    return bool(
        re.search(
            r"(?:"
            r"实现|生成|编码|请完成|编码冒烟|可运行|"
            r"\bGenerate\b|\bImplement\b|\bWrite\b(?:\s+a)?\s+(?:TypeScript|Python|JavaScript|TS|JS)|"
            r"API\s+client|full\s+runnable|no\s+empty\s+##\s*FILE|"
            r"POST\s+/|GET\s+/|curl|"
            r"##\s*FILE:|"
            r"Pydantic|路由\s*\+|附\s*\d+\s*个|"
            r"写出|交付|产出"
            r")",
            t,
            re.I,
        )
    )


def _input_asks_coding_delivery(input_text: str) -> bool:
    """True when the task asks for runnable code files — not PRD / architecture / QA prose.

    PM/architect/QA prompts routinely say 交付/生成/请完成 and mention 上报/审批/派修.
    Those must not inherit ## FILE / TSX / FastAPI gates. Driven by input shape,
    never by agent_id. Not every Agent binds ``code_generation``.
    """
    t = str(input_text or "")
    if len(t.strip()) < 12:
        return False
    if _input_asks_backend_api_slice(t) or _input_asks_frontend_module(t):
        return True
    if _input_asks_isolated_coding_slice(t) or _input_asks_startable_scaffold(t):
        return True
    if _input_asks_tsx_frontend_pages(t):
        return True
    return bool(
        re.search(
            r"(?i)"
            r"##\s*FILE:|"
            r"\bcode_generation\b|"
            r"Pydantic|APIRouter|\bFastAPI\b|"
            r"apiClient|types\.ts|"
            r"\bWrite\b(?:\s+a)?\s+(?:TypeScript|Python|JavaScript|TS|JS)|"
            r"API\s+client|full\s+runnable|"
            r"可运行代码|生成前端代码|生成后端|"
            r"uvicorn|vite\.config",
            t,
        )
    )


def _output_is_clarification_only(output_text: str) -> bool:
    """Model asked the user to confirm readiness instead of delivering the product."""
    t = str(output_text or "")
    if len(t.strip()) < 40:
        return False
    ask_hits = re.findall(
        r"(?:"
        r"请确认以下信息|"
        r"是否已经准备好|"
        r"如果你已经准备好|"
        r"请告诉我[，,]?\s*我们(?:可以)?开始|"
        r"我们可以开始下一步|"
        r"需要你(?:先)?确认|"
        r"等你确认后再|"
        r"准备好了吗|"
        # English clarify / ask-more-details (code_generation false success)
        r"I need more details|"
        r"Could you please provide more|"
        r"please provide more (?:information|details|context)|"
        r"I understand you want|"
        r"what specific functionality|"
        r"are you looking for a (?:simple )?script|"
        r"This will help me provide a more accurate|"
        r"需要(?:更多|进一步)(?:信息|细节|上下文)|"
        r"请(?:再)?补充(?:一下)?(?:需求|细节|信息)"
        r")",
        t,
        re.I,
    )
    if len(ask_hits) < 1:
        return False
    # Real deliverables usually include code fences / FILE markers / curl examples
    has_product = bool(
        re.search(
            r"(?:"
            r"##\s*FILE:|"
            r"```(?:python|ts|tsx|js|json|bash|sh)|"
            r"\bcurl\s+|"
            r"class\s+\w+\s*[\(:]|def\s+\w+\s*\(|"
            r"\"(?:path|method|request|response)\"\s*:"
            r")",
            t,
            re.I,
        )
    )
    return not has_product


def _strip_codegen_done_prefix(text: str) -> str:
    """Strip DONE: / DONE / DONEn (mangled ``DONE\\n``) prefixes from weak models."""
    s = str(text or "").strip()
    return re.sub(r"^(?:DONE\s*:?\s*|DONEn)", "", s, count=1, flags=re.I).strip()


def _unwrap_code_envelope(text: str) -> str:
    """Pull ``code`` field from JSON / Python-repr ``{code, language}`` blobs."""
    s = str(text or "").strip()
    if not s:
        return ""
    # JSON object
    if s.startswith("{") and ("code" in s or "language" in s):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                for k in ("code", "generated_code", "source", "snippet"):
                    v = obj.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
        except Exception:
            pass  # noqa: cleanup-best-effort
        # Python dict repr from skill observe (single quotes)
        try:
            import ast

            obj = ast.literal_eval(s)
            if isinstance(obj, dict):
                for k in ("code", "generated_code", "source", "snippet"):
                    v = obj.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
        except Exception:
            pass  # noqa: cleanup-best-effort
    return s


def _code_body_has_substance(text: str) -> bool:
    """True when code text has runnable body, not only a ## FILE: / DONE header stub."""
    s = _strip_codegen_done_prefix(_unwrap_code_envelope(text))
    body = re.sub(r"(?m)^##\s*FILE:\s*\S+\s*$", "", s)
    body = re.sub(r"(?m)^```\w*\s*$", "", body).strip()
    if len(body) < 40:
        return False
    # Require code-shaped tokens — bare "class"/"function"/"from" in English prose
    # must NOT count (run-0b130688: clarification stuffed into {code, language}).
    return bool(
        re.search(
            r"(?:"
            r"\b(?:async\s+)?def\s+\w+\s*\(|"
            r"\bclass\s+\w+\s*[\(:]|"
            r"\bfunction\s+\w+\s*\(|"
            r"\bconst\s+\w+\s*=|"
            r"\bexport\s+(?:default\s+)?(?:async\s+)?function\s+\w+|"
            r"\b(?:import|from)\s+[\w.\"']+|"
            r"@router\.|APIRouter|BaseModel|FastAPI|"
            r"\bcurl\s+|"
            r"app\.(?:get|post|put|delete|patch)\("
            r")",
            body,
            re.I,
        )
    )


def _output_is_thin_code_stub(output_text: str, raw_out: Any) -> bool:
    """
    Coding task returned a fake deliverable: DONE + empty ## FILE header, or
    {code, language} envelope with no runnable body (run-6db080 / DONEn## FILE /
    run-0b130688 clarification prose in code field).
    """
    candidates: List[str] = []
    if isinstance(raw_out, dict):
        for k in ("code", "generated_code", "source", "snippet"):
            v = raw_out.get(k)
            if isinstance(v, str) and v.strip():
                candidates.append(v)
        files = raw_out.get("files")
        if isinstance(files, list):
            for f in files:
                if isinstance(f, dict) and isinstance(f.get("content"), str) and f["content"].strip():
                    candidates.append(f["content"])
        # Agent finalize often stores skill blob as text / Python-repr dict
        for k in ("text", "answer", "output", "result"):
            v = raw_out.get(k)
            if isinstance(v, str) and v.strip():
                unwrapped = _unwrap_code_envelope(v)
                if unwrapped.strip():
                    candidates.append(unwrapped)
                candidates.append(v)
            elif isinstance(v, dict):
                for ck in ("code", "generated_code", "source", "snippet", "text"):
                    cv = v.get(ck)
                    if isinstance(cv, str) and cv.strip():
                        candidates.append(cv)
    blob = str(output_text or "")
    if blob.strip():
        unwrapped = _unwrap_code_envelope(blob)
        if unwrapped.strip():
            candidates.append(unwrapped)
        candidates.append(blob)

    if not candidates:
        return False

    # Only flag when output looks like an attempted code delivery
    joined = "\n".join(candidates)
    looks_code = bool(
        (isinstance(raw_out, dict) and any(k in raw_out for k in ("code", "language", "files")))
        or re.search(r"##\s*FILE:|(?:DONE\s*:?|DONEn)|['\"]language['\"]\s*:|'code'\s*:|\"code\"\s*:", joined, re.I)
        or (isinstance(raw_out, dict) and isinstance(raw_out.get("text"), str) and re.search(
            r"['\"]code['\"]\s*:|language['\"]?\s*:\s*['\"]python",
            str(raw_out.get("text") or ""),
            re.I,
        ))
    )
    if not looks_code:
        return False

    # Any candidate with real substance → not thin
    for c in candidates:
        if _code_body_has_substance(c):
            return False
    return True


_TS_LANG_FAMILY = frozenset({"typescript", "javascript", "ts", "tsx", "js", "jsx"})
_PY_LANG_FAMILY = frozenset({"python", "py"})


def _detect_requested_code_language(input_text: str) -> Optional[str]:
    """Normalized language family the task asks for (typescript/javascript/python)."""
    t = str(input_text or "")
    if not t.strip():
        return None
    # Drop negated language clauses so 「禁止 Python/FastAPI」 does not count as
    # asking for Python (FE smoke; preferred_language must not lose to false detect).
    _lang_tok = (
        r"(?:type\s*-?\s*script|typescript|javascript|python|fastapi|pydantic|"
        r"\.tsx?\b|\.jsx?\b|\.py\b)"
    )
    # 「不要生成 Vite / App.tsx / package.json」 is a ban list, not a TS ask
    # (run-c11c4dd16a9f backend slice rejected as language_mismatch).
    t = re.sub(
        r"(?i)(?:禁止|勿|不要|别|不得|严禁)(?:使用|用|写|生成|交付)?"
        r"[^\n]{0,80}?(?:App\.tsx|main\.tsx|vite\.config)",
        " ",
        t,
    )
    t = re.sub(
        rf"(?i)(?:禁止|勿|不要|别|不得|严禁|禁止使用|no|not|don't|do\s+not|without)"
        rf"(?:使用|用|写|生成)?\s*"
        rf"(?:{_lang_tok}\s*[/,、]\s*)*{_lang_tok}",
        " ",
        t,
    )
    # Specificity: TypeScript before generic Script; Python via FastAPI/Pydantic.
    # Note: ``*.ts`` has no word-boundary before the dot — do not require ``\b`` before ``.ts``.
    if re.search(
        r"(?i)(?:\b(?:type\s*-?\s*script|typescript|tsx)\b|\.tsx?\b|"
        r"\bgenerate\s+(?:a\s+)?(?:ts|typescript)\b|\bts\s+api\s+client\b)",
        t,
    ):
        return "typescript"
    if re.search(
        r"(?i)\b(?:java\s*-?\s*script|javascript|\.jsx?\b|\bnodejs\b|\bnode\.js\b)\b",
        t,
    ):
        return "javascript"
    if re.search(r"(?i)\b(?:python|\.py\b|fastapi|pydantic)\b", t):
        return "python"
    return None


def _detect_output_code_language(output_text: str, raw_out: Any = None) -> Optional[str]:
    """Best-effort language of the coding deliverable (envelope / fences / files).

    When the envelope ``language`` field conflicts with clear body evidence
    (``## FILE: *.ts`` / `````typescript``), trust the body — skill defaults
    often leave ``language=python`` while the model correctly emits TS.
    """
    field_lang: Optional[str] = None
    if isinstance(raw_out, dict):
        lang = raw_out.get("language")
        if isinstance(lang, str) and lang.strip():
            low = lang.strip().lower()
            if low in _TS_LANG_FAMILY:
                field_lang = "typescript" if low in ("typescript", "ts", "tsx") else "javascript"
            elif low in _PY_LANG_FAMILY:
                field_lang = "python"
        for k in ("text", "output", "result", "answer"):
            v = raw_out.get(k)
            if isinstance(v, dict):
                nested = _detect_output_code_language("", v)
                if nested:
                    return nested
    blob = str(output_text or "")
    if isinstance(raw_out, dict):
        for k in ("code", "generated_code", "source", "snippet", "text"):
            v = raw_out.get(k)
            if isinstance(v, str) and v.strip():
                if not blob.strip() or k == "code":
                    blob = v
                    break
        if not blob.strip():
            blob = _text_blob(raw_out)
    if not blob.strip():
        return field_lang

    body_lang: Optional[str] = None
    m = re.search(r"['\"]language['\"]\s*:\s*['\"](\w+)['\"]", blob, re.I)
    # Prefer file/fence evidence over a nested language string inside the code text.
    if re.search(r"(?i)##\s*FILE:\s*\S+\.(?:ts|tsx)\b|```(?:ts|tsx|typescript)\b", blob):
        body_lang = "typescript"
    elif re.search(r"(?i)##\s*FILE:\s*\S+\.(?:js|jsx)\b|```(?:js|jsx|javascript)\b", blob):
        body_lang = "javascript"
    elif re.search(r"(?i)##\s*FILE:\s*\S+\.py\b|```python\b", blob):
        body_lang = "python"
    elif m:
        low = m.group(1).lower()
        if low in _TS_LANG_FAMILY:
            body_lang = "typescript" if low in ("typescript", "ts", "tsx") else "javascript"
        elif low in _PY_LANG_FAMILY:
            body_lang = "python"
    else:
        has_py = bool(
            re.search(r"(?m)^\s*(?:async\s+)?def\s+\w+\s*\(|^\s*from\s+\w[\w.]*\s+import\b", blob)
        )
        has_ts = bool(
            re.search(
                r"\b(?:export\s+(?:default\s+)?(?:async\s+)?function|interface\s+\w+|type\s+\w+\s*=|"
                r"const\s+\w+\s*[:=])",
                blob,
            )
        )
        if has_py and not has_ts:
            body_lang = "python"
        elif has_ts and not has_py:
            body_lang = "typescript"

    if field_lang and body_lang and not _language_families_compatible(field_lang, body_lang):
        return body_lang
    return field_lang or body_lang


def _language_families_compatible(requested: str, produced: str) -> bool:
    r = str(requested or "").strip().lower()
    p = str(produced or "").strip().lower()
    if not r or not p:
        return True
    if r in _TS_LANG_FAMILY and p in _TS_LANG_FAMILY:
        return True
    if r in _PY_LANG_FAMILY and p in _PY_LANG_FAMILY:
        return True
    return r == p


def _stated_api_paths(input_text: str) -> List[str]:
    """Extract /api/... paths from task text (path: or METHOD prefix)."""
    t = str(input_text or "")
    found = re.findall(
        r"(?i)(?:path:\s*|method:\s*(?:GET|POST|PUT|DELETE|PATCH)\s*\n\s*path:\s*|"
        r"(?:GET|POST|PUT|DELETE|PATCH)\s+)(/[A-Za-z0-9_./\-{}]+)",
        t,
    )
    # Also bare path: lines under OpenAPI-ish yaml
    found += re.findall(r"(?im)^\s*path:\s*(/[A-Za-z0-9_./\-{}]+)\s*$", t)
    # Chinese smoke lines: `apiClient`：POST /api/v1/inspection/reports；
    found += re.findall(
        r"(?i)(?:apiClient|接口|路由)[^/\n]{0,40}(/(?:api/)[A-Za-z0-9_./\-{}]+)",
        t,
    )
    out: List[str] = []
    seen = set()
    for p in found:
        p = str(p).strip().rstrip("；;。,，）)]}\"'" )
        if not p.startswith("/"):
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _path_covered_in_output(path: str, blob: str) -> bool:
    """True if path appears literally or as base URL + leaf (common apiClient style).

    Example: task asks ``/api/v1/inspection/reports`` while code has
    ``const API_BASE_URL = '/api/v1/inspection'`` + ``axios.post(\`\${API_BASE_URL}/reports\`)``.
    """
    p = str(path or "").strip()
    b = str(blob or "")
    if not p or not b:
        return False
    if p in b:
        return True
    parts = [x for x in p.strip("/").split("/") if x]
    if len(parts) < 2:
        return False
    leaf = "/" + parts[-1]
    prefix = "/" + "/".join(parts[:-1])
    if leaf in b and prefix in b:
        return True
    # Template literal: `${API_BASE}/reports` with base defined as prefix
    if prefix in b and (
        re.search(rf"[`$]{{{{[^}}]+}}}}{re.escape(leaf)}", b)
        or re.search(rf"['\"]{re.escape(leaf)}['\"]", b)
        or re.search(rf"\+?\s*['\"]{re.escape(leaf.lstrip('/'))}['\"]", b)
    ):
        return True
    return False


def _output_has_placeholder_coding_shell(blob: str) -> bool:
    """Multi-file scaffold that fakes delivery (print DONE / placeholder autoreview)."""
    t = str(blob or "")
    if not t.strip():
        return False
    markers = (
        r'print\s*\(\s*[\'"]Autoreview called',
        r'print\s*\(\s*[\'"]Delivering code',
        r'print\s*\(\s*[\'"]DONE[\'"]\s*\)',
        r"Add review logic here",
        r"placeholders? for the actual",
        r"#\s*Add\s+.*\s+logic here",
    )
    hits = sum(1 for m in markers if re.search(m, t, re.I))
    if hits >= 2:
        return True
    if hits >= 1 and re.search(r"(?i)##\s*FILE:\s*autoreview\.py\b", t):
        return True
    return False


def _input_requires_auth_todo(input_text: str) -> bool:
    """Task explicitly requires marking auth as TODO (no fake SSO/钉钉)."""
    t = str(input_text or "")
    if not t.strip():
        return False
    return bool(
        re.search(
            r"(?:"
            r"鉴权未给出|"
            r"未给出的鉴权|"
            r"鉴权标\s*TODO|"
            r"鉴权细节\s*标\s*TODO|"
            r"鉴权.*?标\s*TODO|"
            r"标\s*TODO.*?鉴权|"
            r"禁止假实现|"
            r"auth(?:entication)?\s+(?:not\s+given|unknown|TODO)|"
            r"mark\s+TODO.*auth"
            r")",
            t,
            re.I | re.S,
        )
    )


def _extract_code_regions(blob: str) -> str:
    """Return only fenced / ## FILE code bodies — ignore trailing claim prose.

    run-62d703e7a69e greenwashed missing_auth_todo by writing
    「我们添加了 TODO: auth/鉴权」outside the typescript fence while the
    actual ApiClient had no auth TODO comment.
    """
    t = str(blob or "")
    if not t.strip():
        return ""
    parts: List[str] = []
    for m in re.finditer(r"```[\w+-]*\r?\n(.*?)```", t, re.S):
        body = (m.group(1) or "").strip()
        if body:
            parts.append(body)
    if parts:
        return "\n\n".join(parts)
    # Unfenced ## FILE: path blocks (until next ## FILE / EOF)
    file_blocks = re.split(r"(?m)^(?=##\s*FILE:\s*\S)", t)
    for block in file_blocks:
        if re.match(r"(?i)##\s*FILE:\s*\S", block or ""):
            parts.append(block)
    if parts:
        return "\n\n".join(parts)
    return t


def _output_has_auth_todo(blob: str) -> bool:
    """True when deliverable marks auth/SSO as TODO inside code (not claim prose)."""
    t = _extract_code_regions(blob)
    if not t.strip():
        return False
    # Prefer real comment forms so narrative「添加了 TODO」outside fences cannot pass.
    if re.search(
        r"(?m)^[ \t]*(?://|#|--)\s*TODO[^\n]{0,80}(?:auth|鉴权|authorization|bearer|token|登录|SSO|钉钉)",
        t,
        re.I,
    ):
        return True
    if re.search(
        r"(?m)^[ \t]*/\*[^*]*TODO[^\n*]{0,80}(?:auth|鉴权|authorization|bearer|token|登录|SSO|钉钉)",
        t,
        re.I,
    ):
        return True
    # Inline trailing comment on a code line
    if re.search(
        r"(?i)(?://|#)\s*TODO[^\n]{0,80}(?:auth|鉴权|authorization|bearer|token|登录|SSO|钉钉)",
        t,
    ):
        return True
    return False


def _ensure_auth_todo_comment(blob: str, *, language: str = "") -> str:
    """Deterministically insert ``// TODO: auth`` / ``# TODO: auth`` into code.

    Models often put ``### TODO: auth/鉴权`` in markdown or claim prose outside
    fences while apiClient has no line comment (run-91896f56fcd9). Gate only
    accepts a code-line TODO — patch the best apiClient/fetch fence instead of
    another LLM round-trip (avoids step_2 hang after skill fail).
    """
    text = str(blob or "")
    if not text.strip() or _output_has_auth_todo(text):
        return text

    lang = str(language or "").strip().lower()
    use_hash = lang in ("python", "py") or bool(
        re.search(r"(?im)^\s*##\s*FILE:\s*[^\n]+\.py\b", text)
    )
    if not use_hash and re.search(r"(?i)\b(?:typescript|tsx|javascript|jsx|ts|js)\b", lang):
        use_hash = False
    elif not use_hash and not lang:
        # Infer from fences / FILE headers
        if re.search(r"(?im)^\s*##\s*FILE:\s*[^\n]+\.py\b", text) and not re.search(
            r"(?im)^\s*##\s*FILE:\s*[^\n]+\.(?:ts|tsx|js|jsx)\b", text
        ):
            use_hash = True
    marker = "# TODO: auth" if use_hash else "// TODO: auth"

    fence_re = re.compile(r"(```[\w+-]*\r?\n)(.*?)(```)", re.S)
    matches = list(fence_re.finditer(text))
    if not matches:
        # Bare ## FILE body without fences — prepend after first FILE header
        m_file = re.search(r"(?im)^(\s*##\s*FILE:\s*[^\n]*apiClient[^\n]*\n)", text)
        if not m_file:
            m_file = re.search(r"(?im)^(\s*##\s*FILE:\s*[^\n]+\n)", text)
        if m_file:
            return text[: m_file.end()] + marker + "\n" + text[m_file.end() :]
        return marker + "\n" + text

    def _score(m: re.Match) -> int:
        body = m.group(2)
        # Look at preceding ~200 chars for FILE path hint
        start = max(0, m.start() - 220)
        head = text[start : m.start()] + body[:400]
        score = 0
        if re.search(r"(?i)apiClient|api/client|ApiClient", head):
            score += 50
        if re.search(r"(?i)\baxios\b|\bfetch\s*\(|create\(\s*\{", body):
            score += 30
        if re.search(r"(?i)Authorization|Bearer|headers\s*:", body):
            score += 10
        if re.search(r"(?i)\.tsx?\b|React|useState", body) and score < 50:
            score -= 5  # prefer client over page
        return score

    best = max(matches, key=_score)
    if _score(best) <= 0:
        best = matches[0]

    body = best.group(2)
    lines = body.splitlines(keepends=True)
    insert_at = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if (
            not s
            or s.startswith("import ")
            or s.startswith("from ")
            or s.startswith("// Import")
            or s.startswith("# Import")
            or s.startswith("// Define types")
            or s.startswith("// Import necessary")
        ):
            insert_at = i + 1
            continue
        break
    if any(marker in ln for ln in lines):
        return text
    lines.insert(insert_at, marker + "\n")
    new_body = "".join(lines)
    return text[: best.start()] + best.group(1) + new_body + best.group(3) + text[best.end() :]


def _delivered_file_paths(blob: str) -> List[str]:
    """Relative paths from ``## FILE:`` headers (normalized)."""
    paths: List[str] = []
    seen: set = set()
    t = _normalize_coding_blob(blob)
    for m in re.finditer(r"(?im)^\s*##\s*FILE:\s*([^\s`]+)", t):
        path = m.group(1).strip().strip("`\"'")
        if not path or path.lower() in seen:
            continue
        seen.add(path.lower())
        paths.append(path)
    if not paths:
        for m in re.finditer(r"##\s*FILE:\s*([^\s`]+)", t):
            path = m.group(1).strip().strip("`\"'")
            if not path or path.lower() in seen:
                continue
            seen.add(path.lower())
            paths.append(path)
    return paths


def _input_asks_tsx_frontend_pages(input_text: str) -> bool:
    """True when the task explicitly asks for FE pages/client files."""
    t = str(input_text or "")
    return bool(
        re.search(
            r"(?i)ApproveFaultPage|DispatchRepairPage|ReportFaultPage|"
            r"types\.ts|apiClient|pages/.*\.tsx|"
            r"##\s*FILE:\s*frontend/src/",
            t,
        )
    )


def _input_asks_backend_api_slice(input_text: str) -> bool:
    """Isolated FastAPI/Pydantic module — must not inherit FE page gates."""
    t = str(input_text or "")
    if not t.strip() or _input_asks_tsx_frontend_pages(t):
        return False
    return bool(
        re.search(
            r"(?i)Pydantic|APIRouter|测 API 模块|不是完整 uvicorn|"
            r"切片（routes|routes \+ schemas",
            t,
        )
    )


def _input_asks_frontend_module(input_text: str) -> bool:
    """True when the task asks for an assemblable FE module (types+client+page), not a toy fn."""
    t = str(input_text or "")
    if not t.strip():
        return False
    if _input_asks_backend_api_slice(t):
        return False
    # Explicit single-file toy smokes (add.ts only) — skip module gate
    if re.search(r"(?i)仅输出\s*`?##\s*FILE|只输出\s*`?##\s*FILE|only\s+(one\s+)?##\s*FILE", t):
        return False
    if re.search(r"(?i)\badd\s*\(\s*a\s*:\s*number|function\s+add\s*\(", t) and not re.search(
        r"(?i)apiClient|ReportFault|types\.ts|pages/", t
    ):
        return False
    if re.search(
        r"(?i)可组装|types\.ts|apiClient|ReportFaultPage|pages/.*\.tsx|"
        r"前端模块|表单页|至少\s*[23]\s*个\s*`?##\s*FILE|"
        r"##\s*FILE:\s*frontend/src/(types|api/apiClient|pages/)",
        t,
    ):
        return True
    # apiClient + page/component together
    if re.search(r"(?i)api[_ ]?client|/api/v?\d+/", t) and re.search(
        r"(?i)\.tsx\b|页面|组件|form\b|表单", t
    ):
        return True
    return False


def _frontend_module_incomplete(blob: str) -> bool:
    """True when FE module deliverable lacks client+page (or <2 FILE headers)."""
    paths = _delivered_file_paths(blob)
    if len(paths) < 2:
        return True
    joined = " ".join(paths).lower()
    has_client = bool(
        re.search(r"(?i)(apiclient|api/|types\.ts|/types\b)", joined)
        or any(p.lower().endswith(".ts") and not p.lower().endswith(".tsx") for p in paths)
    )
    has_page = bool(
        re.search(r"(?i)(\.tsx\b|/pages/|/components/)", joined)
        or any(p.lower().endswith((".tsx", ".jsx")) for p in paths)
    )
    return not (has_client and has_page)


def _input_asks_multi_flow_frontend(input_text: str) -> bool:
    """True when the task asks for a multi-step FE flow (not a single-page smoke).

    Triggers on explicit page names or the 上报/审批/派修 triad so single-POST
    greenwash cannot pass a full-PRD frontend task (run-c896745b).
    """
    t = str(input_text or "")
    if not t.strip():
        return False
    if _input_asks_backend_api_slice(t):
        return False
    # 上报/审批/派修 is domain language on PM/QA/architect prompts too.
    # Require an actual FE module / TSX ask before the 3-page gate.
    if not _input_asks_frontend_module(t) and not _input_asks_tsx_frontend_pages(t):
        return False
    # Explicit single-page / toy smoke — skip multi-flow gate.
    # Strip negated phrases first so 「不要写死成单页冒烟」 does NOT skip the gate.
    t_for_skip = re.sub(
        r"(?i)(?:不要|禁止|勿|别|并非|不是).{0,16}单页冒烟",
        " ",
        t,
    )
    if re.search(
        r"(?i)仅输出\s*`?##\s*FILE|只输出\s*`?##\s*FILE|only\s+(one\s+)?##\s*FILE|"
        r"只要\s*ReportFaultPage|仅\s*ReportFaultPage|"
        r"单页冒烟",
        t_for_skip,
    ):
        return False
    if re.search(r"(?i)ApproveFaultPage|DispatchRepairPage", t):
        return True
    # PRD triad
    cn = sum(1 for k in ("上报", "审批", "派修") if k in t)
    if cn >= 3:
        return True
    en = 0
    if re.search(r"(?i)\breport(?:fault|ing)?\b|报障", t):
        en += 1
    if re.search(r"(?i)\bapprov", t):
        en += 1
    if re.search(r"(?i)\bdispatch|派修", t):
        en += 1
    return en >= 3


def _frontend_flow_pages_incomplete(blob: str) -> bool:
    """True when multi-flow FE task has fewer than 3 page TSX files.

    Prefers ``frontend/src/pages/*.tsx``; falls back to any non-components TSX
    so path variants still count.
    """
    paths = _delivered_file_paths(blob)
    under_pages = [p for p in paths if "/pages/" in p.lower()]
    if under_pages:
        return len(under_pages) < 3
    pages = [
        p
        for p in paths
        if p.lower().endswith((".tsx", ".jsx")) and "/components/" not in p.lower()
    ]
    return len(pages) < 3


def _input_asks_isolated_coding_slice(input_text: str) -> bool:
    """True for isolated module smoke (any code Agent): not Vite/uvicorn boot, not hang-routes."""
    t = str(input_text or "")
    if not t.strip():
        return False
    if re.search(r"(?i)有脚手架挂路由|假定 Vite 骨架已存在|必须改 App\.tsx", t):
        return False
    if re.search(r"(?i)单独测[·・\-]?可组装切片", t):
        return True
    if re.search(r"(?i)不要用能否单独启动|不是完整 uvicorn", t):
        return True
    if re.search(r"(?i)不要生成\s*package\.json", t) and re.search(
        r"(?i)无\s*project_scaffold|不是\s*(?:完整\s*)?Vite", t
    ):
        return True
    return False


def _input_asks_isolated_frontend_slice(input_text: str) -> bool:
    """Alias — isolated slice is not FE-only; backend/programmer use the same recipe."""
    return _input_asks_isolated_coding_slice(input_text)


def _isolated_coding_extra_project_files(input_text: str, blob: str) -> bool:
    """True when an isolated coding slice shipped Vite/app entry files not requested."""
    paths = [str(p or "").strip().lower().replace("\\", "/") for p in _delivered_file_paths(blob)]
    if not paths:
        return False
    banned = (
        "package.json",
        "vite.config",
        "index.html",
        "/main.tsx",
        "/main.jsx",
        "/app.tsx",
        "/app.jsx",
    )
    extras = [p for p in paths if any(b in p for b in banned)]
    if not extras:
        return False
    requested = {
        str(p or "").strip().lower().replace("\\", "/")
        for p in _delivered_file_paths(input_text)
    }
    if not requested:
        return True
    for p in extras:
        if any(p.endswith(r) or r.endswith(p.split("/")[-1]) or r in p for r in requested):
            continue
        return True
    return False


def _isolated_fe_vite_files(blob: str) -> bool:
    """Legacy helper: Vite/app entries present (used by tests)."""
    return _isolated_coding_extra_project_files("", blob)


def _delivery_looks_startable_scaffold(blob: str) -> bool:
    """True when ## FILE list is a FastAPI + Vite project (not an isolated module slice)."""
    paths = [
        str(p or "").strip().replace("\\", "/").lstrip("./")
        for p in _delivered_file_paths(blob)
    ]
    if not paths:
        return False
    has_py = any(p == "main.py" or p.endswith("/main.py") for p in paths)
    has_fe = any(
        p.endswith("package.json") or "vite.config" in p.lower() for p in paths
    )
    return has_py and has_fe


def _input_asks_startable_scaffold(input_text: str) -> bool:
    """True when the task is project scaffold that must boot FE+BE.

    Isolated FE/BE agent recipes often *mention* scaffold / package.json / FastAPI
    in the negative (「无 project_scaffold」「不要生成 package.json」「禁止 FastAPI」).
    Those must not trigger the startable-scaffold gate.
    """
    t = str(input_text or "")
    if not t.strip():
        return False
    if re.search(
        r"(?i)仅输出\s*`?##\s*FILE|只输出\s*`?##\s*FILE|only\s+(one\s+)?##\s*FILE",
        t,
    ):
        return False
    # Curated smoke chip: 单独测·可启动骨架 — must persist, not treated as isolated slice.
    if re.search(r"(?i)单独测[·・\-]?可启动骨架|可启动(?:前后端)?骨架|可启动脚手架", t):
        if not _input_asks_isolated_coding_slice(t):
            return True
    # Isolated agent smoke: explicitly not a scaffold / Vite boot task.
    if re.search(
        r"(?i)单独测[·・\-]?(?:可组装切片|有脚手架)|"
        r"不是\s*(?:完整\s*)?(?:Vite|uvicorn)\s*工程|"
        r"不要用能否\s*`?npm\s+run\s+dev|"
        r"不要用能否单独启动",
        t,
    ):
        return False
    # Strip negated mentions before positive matching (same pattern as multi-flow).
    t_pos = re.sub(
        r"(?i)(?:无|没有|无需|不要|禁止|勿|别|并非|不是).{0,24}"
        r"(?:project_scaffold|scaffold_agent|工程脚手架|项目骨架|"
        r"package\.json|vite\.config|uvicorn|fastapi|npm\s+run\s+dev|脚手架)",
        " ",
        t,
    )
    t_pos = re.sub(
        r"(?i)(?:project_scaffold|scaffold_agent|工程脚手架|项目骨架|"
        r"package\.json|vite\.config|uvicorn|fastapi|npm\s+run\s+dev|脚手架)"
        r".{0,16}(?:不要|禁止|勿|别)",
        " ",
        t_pos,
    )
    if re.search(r"(?i)scaffold_agent|工程脚手架|项目骨架|project_scaffold", t_pos):
        return True
    if re.search(r"(?i)可启动", t_pos) and re.search(
        r"(?i)vite|fastapi|uvicorn|npm run dev|脚手架", t_pos
    ):
        return True
    if re.search(r"(?i)vite\.config|package\.json", t_pos) and re.search(
        r"(?i)main\.py|uvicorn|fastapi", t_pos
    ):
        return True
    return False


def _strip_one_outer_fence(body: str) -> str:
    s = str(body or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if len(lines) < 2:
        return s
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _iter_delivered_files(blob: str) -> List[Tuple[str, str]]:
    """``## FILE: path`` sections → (path, unfenced body)."""
    t = _normalize_coding_blob(blob)
    out: List[Tuple[str, str]] = []
    for part in re.split(r"(?m)(?=^##\s*FILE:\s*\S)", t):
        m = re.match(r"(?is)^##\s*FILE:\s*([^\s`]+)\s*\n?(.*)$", part.strip())
        if not m:
            continue
        path = m.group(1).strip().strip("`\"'")
        if not path:
            continue
        out.append((path, _strip_one_outer_fence(m.group(2) or "")))
    return out


def _python_triple_quotes_broken(body: str) -> bool:
    """True when a .py body cannot start (odd triple-quotes, or stray opener)."""
    src = str(body or "")
    if not src.strip():
        return False
    if src.count('"""') % 2 == 1 or src.count("'''") % 2 == 1:
        return True
    nonempty = [ln.strip() for ln in src.splitlines() if ln.strip()]
    if len(nonempty) < 2:
        return False
    first, second = nonempty[0], nonempty[1]
    if first in ('"""', "'''") and re.match(
        r"^(from\s+|import\s+|def\s+|class\s+|@|[A-Za-z_]\w*\s*=)",
        second,
    ):
        return True
    return False


def _delivered_python_quotes_broken(blob: str) -> bool:
    for path, body in _iter_delivered_files(blob):
        p = path.lower().replace("\\", "/")
        if p.endswith(".py") and _python_triple_quotes_broken(body):
            return True
    return False


def _scaffold_missing_tsconfig(blob: str) -> bool:
    """Vite + TypeScript skeleton without frontend/tsconfig*.json cannot typecheck."""
    paths = [str(p or "").strip().lower().replace("\\", "/") for p in _delivered_file_paths(blob)]
    has_vite = any(p.startswith("frontend/") and "vite.config" in p for p in paths)
    has_pkg = any(p.endswith("frontend/package.json") for p in paths)
    has_ts = any(p.endswith(".ts") or p.endswith(".tsx") for p in paths)
    if not (has_vite and has_pkg and has_ts):
        return False
    has_tsconfig = any(
        p.endswith("frontend/tsconfig.json")
        or p.endswith("frontend/tsconfig.app.json")
        or p.endswith("frontend/tsconfig.node.json")
        for p in paths
    )
    return not has_tsconfig


def _scaffold_startup_incomplete(blob: str) -> bool:
    """True when scaffold lacks a bootable FastAPI + Vite pair (incl. tsconfig / valid .py)."""
    paths = [str(p or "").strip().lower().replace("\\", "/") for p in _delivered_file_paths(blob)]
    if not paths:
        return True
    has_main_py = any(p == "main.py" or p.endswith("/main.py") for p in paths)
    has_reqs = any(p.endswith("requirements.txt") for p in paths)
    has_pkg = any(p.endswith("frontend/package.json") for p in paths)
    has_vite = any(p.startswith("frontend/") and "vite.config" in p for p in paths)
    has_html = any(p.endswith("frontend/index.html") for p in paths)
    has_main_ts = any(
        p.endswith("frontend/src/main.tsx")
        or p.endswith("frontend/src/main.jsx")
        or p.endswith("frontend/src/main.ts")
        for p in paths
    )
    has_app = any(
        p.endswith("frontend/src/app.tsx") or p.endswith("frontend/src/app.jsx") for p in paths
    )
    if not (has_main_py and has_reqs and has_pkg and has_vite and has_html and has_main_ts and has_app):
        return True
    if _scaffold_missing_tsconfig(blob):
        return True
    if _delivered_python_quotes_broken(blob):
        return True
    return False


def _delivered_file_basenames(blob: str) -> set:
    """Basenames (no extension) from ``## FILE:`` headers in a coding deliverable."""
    names: set = set()
    for m in re.finditer(r"(?im)^\s*##\s*FILE:\s*([^\s`]+)", _normalize_coding_blob(blob)):
        path = m.group(1).strip().strip("`\"'")
        base = path.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0] if "." in base else base
        if stem:
            names.add(stem.lower())
    return names


def _normalize_coding_blob(blob: str) -> str:
    """Turn python-repr ``\\n`` blobs into real newlines so ``## FILE`` anchors work."""
    t = str(blob or "")
    if not t.strip():
        return ""
    if "\\n" in t and t.count("\n") < 2 and ("## FILE:" in t or "FILE:" in t):
        t = t.replace("\\n", "\n").replace("\\t", "\t")
    return t


def _dangling_local_imports(blob: str) -> List[str]:
    """Relative imports (./x ../y) whose module is not among delivered ## FILE stems.

    Catches smoke greenwash like ``from './utils'`` when only apiClient.ts is shipped
    (run-1b2df4ffd82c).
    """
    t = _normalize_coding_blob(blob)
    if not t.strip():
        return []
    delivered = _delivered_file_basenames(t)
    if not delivered:
        # Fallback when FILE headers exist but were not line-anchored (repr leftovers).
        for m in re.finditer(r"##\s*FILE:\s*([^\s`]+)", t):
            path = m.group(1).strip().strip("`\"'")
            base = path.rsplit("/", 1)[-1]
            stem = base.rsplit(".", 1)[0] if "." in base else base
            if stem:
                delivered.add(stem.lower())
    if not delivered:
        return []
    dangling: List[str] = []
    seen: set = set()
    for m in re.finditer(
        r"""(?m)(?:from|import)\s+['"](\.\.?/[^'"]+)['"]"""
        r"""|require\(\s*['"](\.\.?/[^'"]+)['"]\s*\)""",
        t,
    ):
        rel = (m.group(1) or m.group(2) or "").strip()
        if not rel:
            continue
        # ./utils.ts → utils; ../helpers/foo → foo
        leaf = rel.rstrip("/").rsplit("/", 1)[-1]
        stem = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
        key = stem.lower()
        if not key or key in delivered or key in seen:
            continue
        # Index / package-style relative dirs without a file sibling are still dangling
        # for single-file smoke slices.
        seen.add(key)
        dangling.append(rel)
    return dangling


def _claims_no_api_inference(text: str) -> bool:
    """True when task/output forbids inventing API field shapes."""
    t = str(text or "")
    return bool(
        re.search(
            r"(?i)"
            r"不自行推断\s*API|不推断\s*API\s*格式|勿推断\s*API|"
            r"本文件不推断\s*API|字段以\s*api_contracts\s*为准|"
            r"do\s+not\s+infer\s+API|without\s+inferring\s+API|"
            r"no\s+invent(?:ing)?\s+API",
            t,
        )
    )


def _has_explicit_schema_assumption_marker(blob: str) -> bool:
    """Honest labeling that fields are provisional until real contracts arrive."""
    t = str(blob or "")
    return bool(
        re.search(
            r"(?i)"
            r"临时假设|临时最小切片|最小可运行切片|显式假设|ASSUMPTION|"
            # 「假设契约（…」「假设声明」「假设的 api_contracts」— not only bare 假设（因
            r"假设(?:契约|声明|字段)[（(:：]|"
            r"假设(?:契约|声明|字段)?[（(]因|"
            r"假设的?\s*api[_ ]?contracts?|"
            r"假设[（(]因|真实\s*contracts?\s*到位后|"
            r"以真实\s*contracts?\s*为唯一真相源|"
            r"contracts?\s*到位后必须覆盖",
            t,
        )
    )


def _invents_request_response_schema(blob: str) -> bool:
    """Heuristic: TS/Python DTO with multiple concrete fields looks like invented schema.

    Ignores ``import { type CreateReportRequest }`` — that is consumption, not invention
    (run-c896745b: apiClient falsely tripped undeclared_api_schema_assumption).
    """
    t = _normalize_coding_blob(blob)
    # Drop import / re-export lines so ``type FooRequest`` in imports does not count.
    t = re.sub(r"(?m)^\s*import\s+.+$", "", t)
    t = re.sub(r"(?m)^\s*export\s+\{\s*type\s+.+$", "", t)
    # Require a real definition site (not inline import type).
    if not re.search(
        r"(?im)^(?:export\s+)?(?:interface|class)\s+\w*(?:Request|Response|Payload|Body|Dto)\b"
        r"|^(?:export\s+)?type\s+\w*(?:Request|Response|Payload|Body|Dto)\s*=",
        t,
    ):
        return False
    # Property lines inside type blocks (title: string, location: string, …)
    props = re.findall(
        r"(?m)^\s+(?:readonly\s+)?([A-Za-z_]\w*)\s*[?:]?\s*:\s*"
        r"(?:string|number|boolean|Date|[A-Za-z_]\w*)",
        t,
    )
    noise = {"id", "code", "message", "data", "status", "error", "ok", "success"}
    concrete = [p for p in props if p.lower() not in noise]
    return len(concrete) >= 3


def _iter_file_blocks(blob: str) -> List[tuple]:
    """Yield ``(path, body)`` for each ``## FILE:`` section (prose overview excluded)."""
    t = _normalize_coding_blob(blob)
    if not t.strip():
        return []
    out: List[tuple] = []
    for block in re.split(r"(?m)^(?=##\s*FILE:\s*\S)", t):
        m = re.match(r"(?im)##\s*FILE:\s*([^\s`]+)\s*\n?(.*)", block or "", re.S)
        if not m:
            continue
        path = (m.group(1) or "").strip().strip("`\"'")
        body = m.group(2) or ""
        if path:
            out.append((path, body))
    return out


def _schema_fields_covered_by_input(input_text: str, schema_blob: str) -> bool:
    """True when invented DTO fields mostly appear in the task text (declared, not guessed)."""
    t = _normalize_coding_blob(schema_blob)
    props = re.findall(
        r"(?m)^\s+(?:readonly\s+)?([A-Za-z_]\w*)\s*[?:]?\s*:\s*"
        r"(?:string|number|boolean|Date|[A-Za-z_]\w*)",
        t,
    )
    noise = {"id", "code", "message", "data", "status", "error", "ok", "success"}
    uniq = list(dict.fromkeys(p for p in props if p.lower() not in noise))
    if len(uniq) < 3:
        return True
    inp = str(input_text or "")
    inp_fold = re.sub(r"[\s_-]+", "", inp.lower())
    hits = 0
    for p in uniq:
        pl = p.lower()
        if pl in inp.lower() or re.sub(r"[_-]+", "", pl) in inp_fold:
            hits += 1
    return hits >= 3 and hits / len(uniq) >= 0.5


def _undeclared_api_schema_assumption(input_text: str, blob: str) -> bool:
    """Claimed「不推断 API」but shipped Request/Response fields without ASSUMPTION labels.

    Overview prose ``假设（因…）`` must NOT absolve types/apiClient FILE bodies
    (run-c66b5f6533fe greenwash: 步骤4 ASSUMPTION + types.ts「本文件不推断」+ invented fields).
    """
    joined = f"{input_text or ''}\n{blob or ''}"
    if not _claims_no_api_inference(joined):
        return False

    blocks = _iter_file_blocks(blob)
    if blocks:
        for _path, body in blocks:
            if not _invents_request_response_schema(body):
                continue
            if _schema_fields_covered_by_input(input_text, body):
                continue
            if _has_explicit_schema_assumption_marker(body):
                continue
            return True
        return False

    # No ## FILE headers — only count markers inside fenced code, not claim prose.
    code = _extract_code_regions(blob)
    check = code if code.strip() else str(blob or "")
    if not _invents_request_response_schema(check):
        return False
    if _schema_fields_covered_by_input(input_text, check):
        return False
    if _has_explicit_schema_assumption_marker(code if code.strip() else ""):
        return False
    return True


def _output_claims_fake_dingtalk(blob: str) -> bool:
    """True when code/prose claims DingTalk already integrated (forbidden fake)."""
    t = str(blob or "")
    if not t.strip():
        return False
    # Honest TODO / 待确认 must not trip this.
    if re.search(r"(?i)(?:TODO|待确认|暂未|未对接).{0,24}钉钉|钉钉.{0,24}(?:TODO|待确认|暂未)", t):
        return False
    return bool(
        re.search(
            r"(?i)已对接钉钉|钉钉(?:已|完成)对接|DingTalk\s+(?:SDK|integrated|connected)",
            t,
        )
    )


def _coding_contract_fail_codes(
    input_text: str,
    output_text: str,
    raw_out: Any = None,
    *,
    hints: str = "",
    skill_trace: Any = None,
    run_id: str = "",
) -> List[str]:
    """Hard coding-contract failures: wrong language, off-spec shell, incomplete autoreview."""
    # Agent rows often store ``{text: "{'code': '...\\n...'}"``} — unwrap before
    # line-anchored FILE / import checks (run-1b2df4ffd82c greenwash).
    envelope: Any = raw_out if raw_out is not None else {"text": str(output_text or "")}
    # Preserve lock metadata before unwrap — ``_unwrap_output`` may return a bare
    # string when both ``code`` and ``text`` are present (skill gate), dropping
    # preferred_language / _language_locked (FE agent Python greenwash).
    _lock_meta: Dict[str, Any] = {}
    if isinstance(envelope, dict):
        if envelope.get("_language_locked"):
            _lock_meta["_language_locked"] = True
        _el = str(envelope.get("language") or "").strip()
        if _el:
            _lock_meta["language"] = _el
    try:
        unwrapped = _unwrap_output(envelope)
    except Exception:
        unwrapped = envelope
    blob = _text_blob(unwrapped) if unwrapped is not None else ""
    if not blob.strip():
        blob = str(output_text or "")
        if not blob.strip() and raw_out is not None:
            blob = _text_blob(raw_out)
    blob = _normalize_coding_blob(blob)
    if not blob.strip():
        return []
    if unwrapped is not None:
        envelope = unwrapped
    # Re-attach lock onto envelope used for language_mismatch checks.
    if _lock_meta:
        if isinstance(envelope, dict):
            for k, v in _lock_meta.items():
                envelope.setdefault(k, v)
        else:
            envelope = {
                "text": blob if blob else str(envelope),
                "code": blob if blob else str(envelope),
                **_lock_meta,
            }

    asks = _input_asks_coding_delivery(input_text) if input_text else False
    req_lang = _detect_requested_code_language(input_text)
    # Locked envelope language is the authoritative ask (inject already applied
    # task > preferred). Do not let a false-positive detect (e.g. 「禁止 Python」)
    # override the lock.
    env_lang = ""
    locked = False
    if isinstance(envelope, dict):
        env_lang = str(envelope.get("language") or "").strip().lower()
        locked = bool(envelope.get("_language_locked"))
    if locked and env_lang:
        if env_lang in ("typescript", "ts", "tsx"):
            req_lang = "typescript"
        elif env_lang in ("javascript", "js", "jsx"):
            req_lang = "javascript"
        elif env_lang in ("python", "py"):
            req_lang = "python"
        else:
            req_lang = env_lang
    if not asks and not req_lang:
        return []

    codes: List[str] = []
    got_lang = _detect_output_code_language(blob, envelope)
    if req_lang and got_lang and not _language_families_compatible(req_lang, got_lang):
        codes.append("language_mismatch")
    # Envelope language vs body — only when language was locked by
    # preferred_language / task inject. Unlocked ``language=python`` defaults
    # must not fail a real TS body (run-2e2d49539faf).
    if (
        locked
        and env_lang
        and got_lang
        and not _language_families_compatible(env_lang, got_lang)
        and "language_mismatch" not in codes
    ):
        codes.append("language_mismatch")

    if _output_has_placeholder_coding_shell(blob):
        codes.append("off_spec_coding")
    else:
        paths = _stated_api_paths(input_text)
        if (
            len(paths) >= 1
            and re.search(r"(?i)api[_ ]?client|/api/", input_text or "")
            and _code_body_has_substance(blob)
        ):
            if not any(_path_covered_in_output(p, blob) for p in paths):
                codes.append("off_spec_coding")

    if _input_requires_auth_todo(input_text) and _code_body_has_substance(blob):
        if not _output_has_auth_todo(blob):
            codes.append("missing_auth_todo")
        if _output_claims_fake_dingtalk(blob):
            codes.append("fake_integration_claim")

    if _code_body_has_substance(blob) and _dangling_local_imports(blob):
        codes.append("dangling_local_import")

    if (
        _code_body_has_substance(blob)
        and _undeclared_api_schema_assumption(input_text, blob)
    ):
        codes.append("undeclared_api_schema_assumption")

    if (
        _input_asks_frontend_module(input_text)
        and _code_body_has_substance(blob)
        and _frontend_module_incomplete(blob)
    ):
        codes.append("frontend_module_incomplete")

    if (
        _input_asks_multi_flow_frontend(input_text)
        and _code_body_has_substance(blob)
        and _frontend_flow_pages_incomplete(blob)
    ):
        codes.append("frontend_flow_pages_incomplete")

    if (
        _input_asks_isolated_coding_slice(input_text)
        and _code_body_has_substance(blob)
        and _isolated_coding_extra_project_files(input_text, blob)
    ):
        codes.append("isolated_fe_vite_files")

    if _input_asks_startable_scaffold(input_text) and (
        _code_body_has_substance(blob) or _delivered_file_paths(blob)
    ):
        # Mixed FastAPI + Vite is the contract — do not fail language_mismatch
        # just because FILE list includes both .py and .tsx.
        codes[:] = [c for c in codes if c != "language_mismatch"]
        if _scaffold_startup_incomplete(blob):
            codes.append("scaffold_startup_incomplete")
        hints_s = str(hints or "")
        root = ""
        if isinstance(raw_out, dict):
            root = str(raw_out.get("persisted_root") or raw_out.get("persist_root") or "").strip()
        persisted_ok = (
            bool(root)
            or bool(re.search(r"disk_persist=ok\b", hints_s))
            or _workspace_delivery_on_disk(run_id, raw_out)
        )
        if not persisted_ok:
            codes.append("scaffold_not_on_disk")

    if _delivered_python_quotes_broken(blob) and "scaffold_startup_incomplete" not in codes:
        codes.append("broken_python_quotes")

    needs_ar = bool(re.search(r"(?i)\bautoreview\b", f"{input_text or ''} {hints or ''}"))
    if needs_ar:
        ar_ok = False
        if isinstance(skill_trace, (list, tuple)):
            for ev in skill_trace:
                if not isinstance(ev, dict):
                    continue
                name = str(ev.get("name") or ev.get("skill") or ev.get("skill_name") or "").strip().lower()
                if name != "autoreview":
                    continue
                st = str(ev.get("status") or ev.get("state") or "").strip().lower()
                if st in ("success", "completed", "ok", "passed", "pass", "clean"):
                    ar_ok = True
                    break
            if not ar_ok:
                codes.append("autoreview_incomplete")
        elif re.search(r"(?i)##\s*FILE:\s*autoreview\.py\b", blob) or _output_has_placeholder_coding_shell(
            blob
        ):
            # No trace: fabricated autoreview.py / placeholder shell is not a real review.
            codes.append("autoreview_incomplete")

    # unique, stable order
    seen: set = set()
    out: List[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _output_misses_stated_contracts(
    input_text: str,
    output_text: str,
    raw_out: Any = None,
    *,
    hints: str = "",
    skill_trace: Any = None,
) -> bool:
    """True when coding output violates language / contract / autoreview rules."""
    return bool(
        _coding_contract_fail_codes(
            input_text,
            output_text,
            raw_out,
            hints=hints,
            skill_trace=skill_trace,
        )
    )


def is_non_deliverable_coding_output(
    *,
    input_text: str = "",
    output_text: str = "",
    raw_out: Any = None,
    hints: str = "",
    skill_trace: Any = None,
    scope: str = "full",
) -> bool:
    """True when a coding task's skill/agent output is clarify-only, thin stub, or off-contract.

    ``scope``:
    - ``full`` (default): post-run / loop veto — includes off_spec + autoreview_incomplete
    - ``skill``: inside ``code_generation`` only — substance + language; do **not** fail the
      skill on path-split / follow-up contracts (that force false retries + nested LLM,
      see run-054f7ace3a17). Those stay for post-run QR.
    """
    envelope: Any = raw_out if raw_out is not None else {"text": str(output_text or "")}
    try:
        unwrapped = _unwrap_output(envelope)
    except Exception:
        unwrapped = envelope
    blob = _text_blob(unwrapped) if unwrapped is not None else ""
    if not blob.strip():
        blob = str(output_text or "")
        if not blob.strip() and raw_out is not None:
            blob = _text_blob(raw_out)
    blob = _normalize_coding_blob(blob)
    # Runtime/LLM failures are never a deliverable — check before deliverable-ask gate
    # so skill timeout seals still flip to failed (run-e1bd45).
    if _output_is_model_runtime_failure(blob):
        return True
    if blob.lstrip().lower().startswith("skill error:") and (
        "timed out" in blob.lower()
        or "llm_timeout" in blob.lower()
        or "timeout after" in blob.lower()
    ):
        return True
    asks = _input_asks_coding_delivery(input_text) if input_text else False
    req_lang = _detect_requested_code_language(input_text) if input_text else None
    if not asks and not req_lang:
        return False
    if _output_is_clarification_only(blob):
        return True
    if unwrapped is not None:
        envelope = unwrapped
    if _output_is_thin_code_stub(blob, envelope):
        return True
    # Prefer original raw_out so preferred_language / _language_locked survive
    # unwrap (skill gate passes both code+text → unwrap may return a bare string).
    contract_raw = raw_out if raw_out is not None else envelope
    codes = _coding_contract_fail_codes(
        input_text, blob, contract_raw, hints=hints, skill_trace=skill_trace
    )
    if str(scope or "full").lower() == "skill":
        # Fail skill early on clear contract breaches so nested LLM can retry;
        # path-split off_spec / autoreview stay post-run only (run-054f7ace3a17).
        return bool(
            set(codes)
            & {
                "language_mismatch",
                "missing_auth_todo",
                "dangling_local_import",
                "fake_integration_claim",
                "frontend_module_incomplete",
                "frontend_flow_pages_incomplete",
                "broken_python_quotes",
            }
        )
    # Post-run / finalize: only hard product failures seal as failed.
    # Soft warns (undeclared_api_schema_assumption) stay in quality review as warn
    # — must not flip a real 3-FILE deliverable to failed (run-c896745b).
    return bool(set(codes) & _HARD_CODING_FAIL_CODES)


def _output_is_model_runtime_failure(text: str) -> bool:
    """True when the 'deliverable' is actually an LLM/runtime error string.

    Prevents false-green completed runs that auto_done on
    ``Model error: local_llm_inflight: acquire timed out...`` (no skill called).
    """
    t = str(text or "").strip()
    if not t:
        return False
    low = t.lower()
    markers = (
        "model error:",
        "local_llm_inflight",
        "acquire timed out",
        "llm_timeout",
        "llm timeout",
        "max_inflight",
        "connection refused",
        "openaierror",
        "apiconnectionerror",
        "read timed out",
        "deadline exceeded",
        "skill execution timed out",
        "timed out after",
        "side_effect_unrealized",
    )
    return any(m in low for m in markers)


def _output_is_canned_sop_failure(text: str) -> bool:
    """LLM echoed SOP 错误处理 as if a real tool rejected the job."""
    t = str(text or "").strip()
    if not t:
        return False
    markers = (
        "文件格式不支持",
        "不支持的文件格式",
        "不支持该格式",
        "SIDE_EFFECT_UNREALIZED",
        "prompt-only skills may emit text",
    )
    return any(m in t for m in markers)


# Hard coding-product failures: must not leave Agent/Skill execution as status=completed.
_HARD_CODING_FAIL_CODES = frozenset(
    {
        "thin_code_stub",
        "clarification_only",
        "off_spec_coding",
        "language_mismatch",
        "autoreview_incomplete",
        "missing_auth_todo",
        "dangling_local_import",
        "fake_integration_claim",
        "frontend_module_incomplete",
        "frontend_flow_pages_incomplete",
        "scaffold_startup_incomplete",
        "scaffold_not_on_disk",
        "broken_python_quotes",
        "empty_output",
        "model_runtime_error",
        "canned_sop_failure",
        "runtime_failed",
        "runtime_timeout",
    }
)

def quality_review_blocks_success(review: Any) -> bool:
    """True when quality review has hard coding failures — UI must not stay green completed.

    Soft architecture/PRD warnings stay advisory (status may remain completed + warn).
    Thin stubs / clarify-only / empty output flip the run to failed.
    """
    if not isinstance(review, dict):
        return False
    if str(review.get("verdict") or "").lower() != "fail":
        return False
    for i in review.get("issues") or []:
        if not isinstance(i, dict):
            continue
        if str(i.get("severity") or "") != "error":
            continue
        code = str(i.get("code") or i.get("category") or "").strip()
        if code in _HARD_CODING_FAIL_CODES:
            return True
    return False


def _input_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        parts: List[str] = []
        for k in (
            "user_requirement",
            "message",
            "query",
            "input",
            "requirement",
            "text",
            "content",
        ):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v)
            elif isinstance(v, dict):
                # Nested execute envelopes: {input: {user_requirement: "..."}}
                nested = _input_text(v)
                if nested.strip():
                    parts.append(nested)
        if parts:
            return "\n".join(parts)
        # Empty dict / no known keys → treat as missing input (do NOT dump "{}")
        if not payload:
            return ""
        return _text_blob(payload)
    return _text_blob(payload)


def _repair_llm_json(text: str) -> str:
    """Fix common local-LLM JSON mistakes so review can see nested fields.

    Known pattern: object values that are bare string lists without keys, e.g.
    ``"上报": { "步骤一", "步骤二" }`` → ``"上报": [ "步骤一", "步骤二" ]``.
    """
    s = (text or "").strip()
    if not s:
        return s
    # Trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r":\s*\{\s*((?:"
            r'"[^"\\]*(?:\\.[^"\\]*)*"\s*,\s*)*'
            r'"[^"\\]*(?:\\.[^"\\]*)*"\s*)\}',
            lambda m: ": [" + m.group(1).strip() + "]",
            s,
        )
    return s


def _try_parse_jsonish(s: str) -> Any:
    """json.loads → repair → balanced-slice reload. Returns parsed value or None."""
    if not s or not (s.startswith("{") or s.startswith("[")):
        return None
    try:
        return json.loads(s)
    except Exception:
        pass  # noqa: cleanup-best-effort
    repaired = _repair_llm_json(s)
    if repaired != s:
        try:
            return json.loads(repaired)
        except Exception:
            pass  # noqa: cleanup-best-effort
    # Balanced extract from first brace (handles trailing prose)
    start = s.find("{") if s.startswith("{") or "{" in s[:8] else s.find("[")
    if start < 0:
        return None
    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                end = i
                break
    if end <= start:
        return None
    chunk = s[start : end + 1]
    try:
        return json.loads(chunk)
    except Exception:
        pass  # noqa: cleanup-best-effort
    try:
        return json.loads(_repair_llm_json(chunk))
    except Exception:
        return None


def _looks_python_dict_repr(s: str) -> bool:
    """True when *s* looks like a Python dict/list literal (single-quoted keys)."""
    t = (s or "").lstrip()
    if not (t.startswith("{") or t.startswith("[")):
        return False
    return bool(re.search(r"""[\{\[,]\s*'[^']+'\s*:""", t[:800]))


def _arch_field_empty(val: Any) -> bool:
    if val is None or val == "" or val == [] or val == {}:
        return True
    if isinstance(val, (list, dict)) and len(val) == 0:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _arch_field_as_text(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        parts = [str(x).strip() for x in val if str(x).strip()]
        return "；".join(parts)
    if isinstance(val, dict):
        try:
            return json.dumps(val, ensure_ascii=False)
        except Exception:
            return str(val)
    return str(val).strip()


def _architecture_output_is_lone_api(output: Any) -> bool:
    """True when product is a single API endpoint object, not a full architecture draft.

    Seen after fail-constraint rerun when the model echoes the API example
    (run-30e6314a1bd3: only method/path/request/response).
    """
    if not isinstance(output, dict):
        return False
    keys = {str(k) for k in output.keys()}
    if not ({"method", "path"} <= keys or {"method", "url"} <= keys):
        return False
    arch_markers = {
        "title",
        "overview",
        "components",
        "folder_structure",
        "api_contracts",
        "api_design",
        "apis",
        "data_flow",
        "context",
        "assumptions",
        "security",
        "rollout_and_risks",
    }
    return not (keys & arch_markers)


def ensure_architecture_section_fields(output: Any) -> Any:
    """Fill missing review-critical architecture keys from local-LLM aliases.

    Small local models often put 上下文 into ``overview`` and security into
    ``security_and_compliance``. Without this normalize, quality review keeps
    failing ``architecture_sections_thin`` even after SOP 一键修复 + re-run.
    """
    if not isinstance(output, dict):
        return output
    # Only touch architecture-shaped products
    markers = (
        "overview",
        "folder_structure",
        "data_flow",
        "api_design",
        "components",
        "architecture_mode",
        "document_type",
        "rollout_and_risks",
        "security_and_compliance",
    )
    if not any(k in output for k in markers):
        return output

    out = dict(output)

    if _arch_field_empty(out.get("context")):
        for alias in (
            "assumptions",
            "context_and_assumptions",
            "hypothesis",
            "上下文与假设",
            "业务上下文",
        ):
            if not _arch_field_empty(out.get(alias)):
                out["context"] = _arch_field_as_text(out.get(alias))
                break
        else:
            overview = out.get("overview")
            if isinstance(overview, str) and len(overview.strip()) >= 20:
                out["context"] = overview.strip()

    if _arch_field_empty(out.get("security")):
        for alias in (
            "security_and_compliance",
            "compliance",
            "安全与合规",
            "安全",
        ):
            if not _arch_field_empty(out.get(alias)):
                out["security"] = _arch_field_as_text(out.get(alias))
                break

    if _arch_field_empty(out.get("rollout_and_risks")) and _arch_field_empty(out.get("risks")):
        for k, v in list(out.items()):
            if not isinstance(k, str) or _arch_field_empty(v):
                continue
            if re.search(r"分期|风险|试点|6\s*周|rollout|phase", k, re.I):
                out["rollout_and_risks"] = _arch_field_as_text(v)
                break

    return out


def sanitize_architecture_third_party(
    output: Any,
    input_text: str = "",
) -> Any:
    """Rewrite invented DingTalk / third-party claims when input forbids inventing.

    Local models often echo「对接钉钉开放平台」despite「暂无 API 文档」. Normalize
    to the SOP-approved pending placeholder so delivery + quality review stay aligned.
    """
    if not isinstance(output, dict) or not input_text:
        return output
    if not re.search(
        r"暂无\s*API|无\s*API\s*文档|API\s*未开放|禁止编造|不编造|暂无钉钉",
        input_text,
    ):
        return output

    replacements = [
        (re.compile(r"DingTalk\s*SDK|钉钉\s*SDK", re.I), "通知通道（钉钉·待确认）"),
        (re.compile(r"与钉钉进行交互，?实现[^。；\n]{0,24}"), "钉钉通知待对接（暂无 API 文档）"),
        (re.compile(r"负责对接钉钉实现[^。；\"'}\]\n]{0,24}"), "钉钉通知通道待确认（暂无 API 文档）"),
        (re.compile(r"对接钉钉实现[^。；\"'}\]\n]{0,24}"), "钉钉通知待对接（暂无 API 文档）"),
        (re.compile(r"通过钉钉通知通道实现[^。；\n]{0,40}"), "钉钉通知通道（待对接，暂无 API 文档）"),
        (re.compile(r"对接钉钉开放平台"), "通知通道（钉钉·待确认）"),
        (re.compile(r"通知钉钉开放平台"), "通知通道（钉钉·待确认）"),
        (re.compile(r"钉钉开放平台"), "通知通道（钉钉·待确认）"),
        (re.compile(r"调用钉钉\S{0,12}(?:接口|API)"), "待对接钉钉通知通道"),
        (re.compile(r"钉钉(?:审批|派修|看板)接口"), "钉钉业务接口（待确认）"),
    ]

    def _rewrite(obj: Any) -> Any:
        if isinstance(obj, str):
            s = obj
            for pat, rep in replacements:
                s = pat.sub(rep, s)
            return s
        if isinstance(obj, list):
            return [_rewrite(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _rewrite(v) for k, v in obj.items()}
        return obj

    return _rewrite(dict(output))


def _unwrap_output(output: Any) -> Any:
    cur = output
    for _ in range(8):
        if cur is None:
            return None
        if isinstance(cur, str):
            s = cur.strip()
            if not s:
                return s
            original = s
            # Python dict/list repr MUST be evaluated before fence strip.
            # Fence regex on unevaluated repr captures literal `\n` escapes inside
            # the quoted profile value → JSON parse fails → false section gaps.
            if _looks_python_dict_repr(s):
                try:
                    import ast

                    lit = ast.literal_eval(s)
                    if isinstance(lit, (dict, list)):
                        cur = lit
                        continue
                except Exception:
                    pass  # noqa: cleanup-best-effort
            # Markdown fence (closed or open-ended) — only keep inner if it parses
            fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.I)
            if fence:
                inner = fence.group(1).strip()
                if inner:
                    parsed = _try_parse_jsonish(inner)
                    if parsed is not None:
                        cur = parsed
                        continue
                    unesc = (
                        inner.replace("\\n", "\n")
                        .replace("\\t", "\t")
                        .replace('\\"', '"')
                    )
                    parsed = _try_parse_jsonish(unesc)
                    if parsed is not None:
                        cur = parsed
                        continue
                    # Unusable fence — do not replace *s* with broken escaped inner
                    s = original
            elif "```" in s:
                open_fence = re.search(r"```(?:json)?\s*([\s\S]+)", s, re.I)
                if open_fence:
                    inner = open_fence.group(1).strip()
                    if inner.endswith("```"):
                        inner = inner[:-3].strip()
                    if inner:
                        parsed = _try_parse_jsonish(inner)
                        if parsed is not None:
                            cur = parsed
                            continue
                        s = original
            if s.startswith("{") or s.startswith("["):
                parsed = _try_parse_jsonish(s)
                if parsed is not None:
                    cur = parsed
                    continue
                # Python dict/list repr (single quotes) — common local-LLM artifact
                try:
                    import ast

                    lit = ast.literal_eval(s)
                    if isinstance(lit, (dict, list)):
                        cur = lit
                        continue
                except Exception:
                    pass  # noqa: cleanup-best-effort
            # Display-profile / embedded JSON with double-quoted keys
            if "x-display-profile" in s or '"title"' in s or '"overview"' in s:
                m = re.search(r"\{\s*\"", s)
                if m:
                    chunk = s[m.start() :]
                    parsed = _try_parse_jsonish(chunk)
                    if parsed is not None:
                        cur = parsed
                        continue
            # JSON fenced or embedded PRD
            m = re.search(r"\{[\s\S]*\"functional_requirements\"[\s\S]*\}", s)
            if m:
                parsed = _try_parse_jsonish(m.group(0))
                if parsed is not None:
                    return parsed
            return s
        if isinstance(cur, dict):
            if "prd" in cur and isinstance(cur.get("prd"), (dict, str)):
                return _unwrap_output(cur.get("prd"))
            profile = cur.get("x-display-profile")
            if isinstance(profile, dict) and profile:
                return _unwrap_output(profile)
            if isinstance(profile, str) and profile.strip() and (
                profile.strip().startswith("{")
                or "```" in profile
                or '"title"' in profile
                or "folder_structure" in profile
            ):
                return _unwrap_output(profile)
            if "output" in cur:
                cur = cur.get("output")
                continue
            if "result" in cur and isinstance(cur.get("result"), (dict, str)):
                cur = cur.get("result")
                continue
            # Common skill envelopes: markdown / content / text holding JSON or prose.
            # Do NOT dive into ``response`` on an API-contract object (method/path/request/
            # response) — that wrongly collapses a lone endpoint into {status,body}
            # and misses architecture_output_is_lone_api (run-30e6314a1bd3).
            envelope_keys = ("markdown", "content", "text", "answer")
            if not (
                {"method", "path"} <= set(str(k) for k in cur.keys())
                or {"method", "url"} <= set(str(k) for k in cur.keys())
            ):
                envelope_keys = envelope_keys + ("response",)
            for key in envelope_keys:
                v = cur.get(key)
                if isinstance(v, str) and v.strip() and (
                    "functional_requirements" in v
                    or "open_questions" in v
                    or "folder_structure" in v
                    or "data_flow" in v
                    or "components" in v
                    or '"title"' in v
                    or "'method'" in v
                    or '"method"' in v
                    or v.strip().startswith("{")
                    or "```" in v
                ):
                    return _unwrap_output(v)
                if isinstance(v, dict) and v:
                    return _unwrap_output(v)
            return cur
        return cur
    return cur


def _collect_architecture_apis(output: Any) -> List[Dict[str, Any]]:
    """Gather API contract dicts from top-level or nested folder_structure/components/data_flows."""
    if not isinstance(output, dict):
        return []
    apis: List[Dict[str, Any]] = []
    for key in ("api_contracts", "api_design", "apis", "endpoints"):
        v = output.get(key)
        if isinstance(v, list):
            apis.extend([x for x in v if isinstance(x, dict)])
    for nest_key in ("folder_structure", "components", "modules", "services"):
        nest = output.get(nest_key)
        if not isinstance(nest, list):
            continue
        for item in nest:
            if not isinstance(item, dict):
                continue
            for ik in ("interfaces", "api", "apis", "endpoints"):
                iv = item.get(ik)
                if isinstance(iv, list):
                    apis.extend([x for x in iv if isinstance(x, dict)])
    # Models often nest method/path under data_flow(s) details (run-5eb7)
    for flow_key in ("data_flow", "data_flows", "flows"):
        flows = output.get(flow_key)
        if isinstance(flows, dict):
            flows = [flows]
        if not isinstance(flows, list):
            continue
        for flow in flows:
            if not isinstance(flow, dict):
                continue
            for dk in ("details", "steps", "apis", "endpoints", "api_contracts"):
                details = flow.get(dk)
                if isinstance(details, list):
                    apis.extend([x for x in details if isinstance(x, dict) and ("method" in x or "path" in x)])
                elif isinstance(details, dict) and ("method" in details or "path" in details):
                    apis.append(details)
            # flow itself may be an endpoint-shaped object
            if "method" in flow and "path" in flow:
                apis.append(flow)
    return apis


def _invented_third_party_api_hits(input_text: str, output_text: str) -> List[str]:
    """When input forbids inventing APIs / says docs missing, flag concrete third-party calls."""
    if not input_text or not output_text:
        return []
    if not re.search(
        r"暂无\s*API|无\s*API\s*文档|API\s*未开放|禁止编造|不编造|暂无钉钉",
        input_text,
    ):
        return []
    hits: List[str] = []
    patterns = [
        (r"发送至钉钉\S{0,8}接口", "钉钉…接口调用"),
        (r"钉钉(?:审批|派修|看板)接口", "钉钉业务接口"),
        (r"对接钉钉\S{0,8}API(?!\s*[（(]?待确认)", "钉钉 API 对接细节"),
        (r"DingTalk\s*SDK|钉钉\s*SDK", "DingTalk/钉钉 SDK"),
        (r"与钉钉进行交互，?实现", "与钉钉交互实现审批派修"),
    ]
    for pat, label in patterns:
        if re.search(pat, output_text):
            hits.append(label)
    # 「调用钉钉…API/接口」— skip negated forms like「不实际调用钉钉 API」
    for m in re.finditer(r"调用钉钉\S{0,12}(?:接口|API)", output_text):
        pre = output_text[max(0, m.start() - 10) : m.start()]
        if re.search(r"(不|未|勿|禁|无需|不用|实际不)\s*$", pre) or "不实际" in pre:
            continue
        hits.append("调用钉钉接口")
        break
    return list(dict.fromkeys(hits))


_SECURITY_IN_PERFORMANCE = [
    r"不上公网",
    r"不能传到公网",
    r"不传到公网",
    r"照片不外传",
    r"不外传",
    r"加密",
]
_PENDING_AC = [
    r"待确认",
    r"未开放",
    r"是否开放",
    r"暂时没有",
    r"集成待确认",
]
_VERIFIABLE_AC = [
    r"status\s*[=＝变为]",
    r"非空",
    r"字段",
    r"ticket_count",
    r"avg_close",
    r"接口返回",
    r"repair_task_id",
]


def _constraint_performance_blob(output: Any) -> str:
    if not isinstance(output, dict):
        return ""
    cons = output.get("constraints")
    if isinstance(cons, dict):
        return _text_blob(cons.get("performance"))
    return ""


def _iter_ac_texts(output: Any) -> List[str]:
    texts: List[str] = []
    if not isinstance(output, dict):
        return texts
    for key in ("functional_requirements", "user_stories"):
        items = output.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            acs = item.get("acceptance_criteria")
            if isinstance(acs, str) and acs.strip():
                texts.append(acs.strip())
            elif isinstance(acs, list):
                for ac in acs:
                    if isinstance(ac, str) and ac.strip():
                        texts.append(ac.strip())
                    elif isinstance(ac, dict):
                        s = str(ac.get("description") or ac.get("text") or "").strip()
                        if s:
                            texts.append(s)
    return texts


def _fr_without_ac_hits(output: Any) -> List[str]:
    """FR entries whose acceptance_criteria is missing or empty."""
    if not isinstance(output, dict):
        return []
    frs = output.get("functional_requirements")
    if not isinstance(frs, list):
        return []
    hits: List[str] = []
    for i, fr in enumerate(frs):
        if not isinstance(fr, dict):
            continue
        acs = fr.get("acceptance_criteria")
        ok = False
        if isinstance(acs, str) and acs.strip():
            ok = True
        elif isinstance(acs, list):
            for ac in acs:
                if isinstance(ac, str) and ac.strip():
                    ok = True
                    break
                if isinstance(ac, dict) and str(
                    ac.get("description") or ac.get("text") or ac.get("label") or ""
                ).strip():
                    ok = True
                    break
        if not ok:
            hits.append(str(fr.get("id") or fr.get("name") or fr.get("label") or f"FR-{i + 1}"))
    return hits


def _missing_required_ac_tokens(input_text: str, output: Any) -> List[str]:
    """When input spells concrete AC tokens, require them inside acceptance_criteria."""
    if not input_text:
        return []
    ac_blob = "\n".join(_iter_ac_texts(output))
    if not ac_blob and not _fr_count(output):
        return []
    tokens = [
        ("pending_approval", r"pending_approval"),
        ("repair_task_id", r"repair_task_id"),
        ("ticket_count", r"ticket_count"),
        ("avg_close_hours", r"avg_close_hours"),
    ]
    missing: List[str] = []
    for label, pat in tokens:
        if re.search(pat, input_text, re.I) and not re.search(pat, ac_blob, re.I):
            missing.append(label)
    return missing


def _constraint_bucket_hits(output: Any) -> List[str]:
    blob = _constraint_performance_blob(output)
    if not blob:
        return []
    hits: List[str] = []
    for p in _SECURITY_IN_PERFORMANCE:
        if re.search(p, blob):
            hits.append(p)
    return hits


def _pending_ac_hits(output: Any) -> List[str]:
    hits: List[str] = []
    for ac in _iter_ac_texts(output):
        if any(re.search(p, ac) for p in _PENDING_AC) and not any(
            re.search(p, ac) for p in _VERIFIABLE_AC
        ):
            hits.append(ac[:80])
    return hits


def _soft_ac_hits(text: str) -> List[str]:
    patterns = [
        r"可以.{0,16}查看",
        r"能通过.{0,12}查看",
        r"可以通过.{0,12}查看",
        r"通过看板查看",
        r"查看结果正确",
        r"上传成功",
        r"能正确上传",
        r"返回成功提示",
        r"审批成功提示",
        r"成功提示",
        r"清晰可见",
        r"实际操作测试",
        r"操作成功",
        r"功能正常",
        r"能正常使用",
        r"能成功上报",
        r"能成功审批",
        r"正确无误",
    ]
    hits: List[str] = []
    for p in patterns:
        m = re.search(p, text)
        if m:
            hits.append(m.group(0))
    return hits


def _fr_item_blob(fr: Any) -> str:
    if isinstance(fr, dict):
        parts = [
            fr.get("id"),
            fr.get("name"),
            fr.get("label"),
            fr.get("description"),
            fr.get("title"),
        ]
        for ac in fr.get("acceptance_criteria") or []:
            if isinstance(ac, dict):
                parts.extend([ac.get("description"), ac.get("label"), ac.get("text"), ac.get("name")])
            else:
                parts.append(ac)
        return " ".join(str(p) for p in parts if p)
    return str(fr or "")


def _constraint_as_fr_hits(output: Any) -> List[str]:
    """FR that only restate security/performance/out-of-scope — not real features."""
    if not isinstance(output, dict):
        return []
    frs = output.get("functional_requirements")
    if not isinstance(frs, list):
        return []
    constraint_pat = re.compile(
        r"不上公网|不能传到公网|照片不外传|不上传到公网|不外传|"
        r"明确不做|6\s*周内试点|待压测"
    )
    feature_pat = re.compile(
        r"上报|拍照|审批|派修|看板|ticket_count|avg_close|pending_approval|"
        r"repair_task|status\s*="
    )
    hits: List[str] = []
    for i, fr in enumerate(frs):
        blob = _fr_item_blob(fr)
        if not blob or not constraint_pat.search(blob):
            continue
        if feature_pat.search(blob):
            continue
        label = ""
        if isinstance(fr, dict):
            label = str(fr.get("id") or fr.get("name") or fr.get("label") or f"FR-{i + 1}")
        else:
            label = f"FR-{i + 1}"
        hits.append(label)
    return hits


def _missing_core_flow_fr(input_text: str, output: Any) -> List[str]:
    """When input names main flows, require matching FR coverage."""
    if not input_text or not isinstance(output, dict):
        return []
    frs = output.get("functional_requirements")
    if not isinstance(frs, list) or not frs:
        return []
    fr_blob = " ".join(_fr_item_blob(fr) for fr in frs)
    checks = [
        (r"拍照|上报", r"拍照|上报|pending_approval", "拍照上报"),
        (r"审批|派修", r"审批|派修|assigned|repair_task", "审批派修"),
        (r"看板|报障量|闭环时长", r"看板|ticket_count|avg_close|报障量|闭环", "管理看板"),
    ]
    missing: List[str] = []
    for in_pat, out_pat, label in checks:
        if re.search(in_pat, input_text) and not re.search(out_pat, fr_blob, re.I):
            missing.append(label)
    return missing


def _fr_count(output: Any) -> int:
    if not isinstance(output, dict):
        return 0
    items = output.get("functional_requirements")
    return len(items) if isinstance(items, list) else 0


def _excluded_capabilities(input_text: str) -> List[str]:
    """Parse customer '明确不做' items from draft or finalize wording."""
    if not input_text:
        return []
    chunks: List[str] = []
    for m in re.finditer(r"明确不做[:：]?\s*([^\n]+)", input_text):
        chunks.append(m.group(1))
    # 「OCR、语音转写：明确不做」/ 「…明确不做（勿再列入…）」
    for m in re.finditer(
        r"([^\n：:]{2,48})[:：]\s*明确不做|"
        r"([^\n]{0,48}(?:OCR|ocr|语音|转写)[^\n]{0,24})明确不做",
        input_text,
    ):
        chunks.append(m.group(1) or m.group(2) or "")
    excluded: List[str] = []
    for chunk in chunks:
        for part in re.split(r"[、,，;/；]|以及|和", chunk):
            p = part.strip()
            if not p or len(p) < 2:
                continue
            if re.search(r"OCR|ocr", p):
                excluded.append("OCR")
            if "语音" in p or "转写" in p:
                excluded.append("语音转写")
    return list(dict.fromkeys(excluded))


def _out_of_scope_oq_hits(input_text: str, output: Any) -> List[str]:
    """Flag open_questions that reopen items the customer explicitly excluded."""
    excluded = _excluded_capabilities(input_text)
    if not excluded:
        return []
    oq_blob = ""
    if isinstance(output, dict):
        oq_blob = _text_blob(output.get("open_questions"))
    hits: List[str] = []
    for ex in excluded:
        if re.search(re.escape(ex), oq_blob, re.I):
            hits.append(ex)
    return hits


def _out_of_scope_feature_hits(input_text: str, output: Any) -> List[str]:
    """Flag FR/AC that implement capabilities the customer excluded."""
    excluded = _excluded_capabilities(input_text)
    if not excluded or not isinstance(output, dict):
        return []
    feat_blob = _text_blob(
        {
            k: output.get(k)
            for k in ("functional_requirements", "user_stories")
            if k in output
        }
    )
    # Only treat as positive feature when not framed as exclusion in the same FR.
    hits: List[str] = []
    for ex in excluded:
        if not re.search(re.escape(ex), feat_blob, re.I):
            continue
        # Allow 「不做语音转写」「明确不做 OCR」 as decision wording inside FR desc.
        if re.search(
            rf"(?:明确)?不做.{{0,12}}{re.escape(ex)}|"
            rf"{re.escape(ex)}.{{0,12}}(?:不做|不在范围|范围外|不支持)",
            feat_blob,
            re.I,
        ) and not re.search(
            rf"(?:实现|支持|生成|进行|通过).{{0,16}}{re.escape(ex)}|"
            rf"{re.escape(ex)}.{{0,24}}(?:功能|以便|生成)",
            feat_blob,
            re.I,
        ):
            continue
        hits.append(ex)
    return hits


def _is_finalize_round(input_text: str) -> bool:
    """True when caller explicitly asked to close open_questions / emit PRD_READY."""
    t = str(input_text or "")
    return bool(
        re.search(
            r"【\s*定稿|定稿｜|定稿轮|请输出定稿|关闭待确认|"
            r"open_questions\s*=\s*\[\s*\]|"
            r"可加\s*<!--\s*PRD_READY|"
            r"open_questions\s*必须为空|open_questions\s*为\s*\[\s*\]",
            t,
            re.I,
        )
    )


def _is_draft_round(input_text: str, output: Any = None) -> bool:
    """True when the caller asked for a draft / non-PRD_READY acceptance round.

    Prefer restoring run input via ``resolve_review_io_from_store`` / status ``input``
    before relying on this. Empty-input + open_questions shape is a last-resort
    fallback so assess_prd.open_questions_present does not hard-fail drafts when
    the client forgot execution_id and the store also has no input.

    Explicit finalize wording wins over leftover「未开放/预算」phrases in the same input.
    """
    t = str(input_text or "").strip()
    # Empty JSON / null-ish payloads from lost stream input
    if t in ("{}", "[]", "null", "None", '""', "''"):
        t = ""
    if _is_finalize_round(t):
        return False
    if re.search(
        r"不要\s*PRD_READY|勿.*PRD_READY|可验收草稿|客户口述|草稿轮|"
        r"不要输出\s*<!--\s*PRD_READY|请做可验收草稿",
        t,
        re.I,
    ):
        return True
    if t:
        return False
    # Last resort: no/empty input — infer draft from output shape only.
    if not isinstance(output, dict):
        return False
    oq = output.get("open_questions")
    if not (isinstance(oq, list) and len(oq) > 0):
        return False
    blob = _text_blob(output)
    if re.search(r"PRD_READY", blob):
        return False
    return True


# Draft vs finalize semantics live in assess_prd(assessment_round=...); do not
# re-filter gate codes here.


def _must_keep_phrases(input_text: str) -> List[Tuple[str, List[str]]]:
    """Return (label, alternative_needles) that output should retain when input has them."""
    rules: List[Tuple[str, List[str], List[str]]] = [
        (
            "照片不上公网 / 不能传到公网",
            [r"不上公网", r"不能传到公网", r"不传到公网", r"不能.*公网", r"照片不外传"],
            [
                r"不上公网",
                r"不能传到公网",
                r"不传到公网",
                r"照片不外传",
                r"不外传",
                r"内网",
                r"私有化",
                r"不出网",
            ],
        ),
        (
            "钉钉 API 未开放 / 待确认",
            [
                r"钉钉.*API",
                r"没有开放 API",
                r"未开放.*API",
                r"API\s*仍未开放",
                r"暂无\s*API",
                r"钉钉.*暂无",
                r"对接钉钉",
            ],
            [
                r"钉钉.*API",
                r"API.*未",
                r"待确认.*钉钉",
                r"钉钉.*待确认",
                r"pending_api",
                r"暂无.*API",
                r"没有.*API.*文档",
                r"API.*文档",
                r"钉钉.*pending",
                r"钉钉.*待",
            ],
        ),
    ]
    out: List[Tuple[str, List[str]]] = []
    for label, in_needles, out_needles in rules:
        if any(re.search(n, input_text) for n in in_needles):
            out.append((label, out_needles))
    return out


def _looks_prd_skill(skill_id: str, skill_name: str, output: Any) -> bool:
    sid = f"{skill_id} {skill_name}".lower()
    if any(
        k in sid
        for k in (
            "requirement_analysis",
            "需求分析",
            "prd",
            "pm_agent",
            "产品经理",
            "product manager",
        )
    ):
        return True
    if isinstance(output, dict) and (
        "functional_requirements" in output
        or "open_questions" in output
        or "user_stories" in output
    ):
        return True
    blob = _text_blob(output)
    return "functional_requirements" in blob or "acceptance_criteria" in blob


def _looks_architecture(asset_id: str, asset_name: str, output: Any, hints: str = "") -> bool:
    sid = f"{asset_id} {asset_name} {hints}".lower()
    if any(
        k in sid
        for k in (
            "architecture",
            "architect",
            "架构",
            "系统架构师",
            "architecture_design",
        )
    ):
        return True
    if not isinstance(output, dict):
        return False
    if str(output.get("document_type") or "") == "architecture_design":
        return True
    if str(output.get("architecture_mode") or "") in ("agent", "code"):
        return True
    keys = set(output.keys())
    return bool(
        keys
        & {
            "components",
            "folder_structure",
            "api_contracts",
            "api_design",
            "tech_stack",
            "design_decisions",
            "skill_routing",
            "data_flow",
            "rollout_and_risks",
        }
    )


_PUBLIC_CLOUD_STORE = re.compile(
    r"阿里云(?:OSS|对象存储|存储)?|腾讯云(?:COS|对象存储|存储)?|七牛|"
    r"AWS\s*S3|Amazon\s*S3|公有云(?:对象)?存储|对象存储|"
    r"\bOSS\b|\bS3\b",
    re.I,
)


def _public_cloud_photo_storage_hits(input_text: str, output_text: str) -> List[str]:
    """When input forbids public-net photos, flag public-cloud object storage in output."""
    if not input_text or not output_text:
        return []
    if not re.search(
        r"不上公网|不可上公网|不能传到公网|不传到公网|照片不外传|不外传",
        input_text,
    ):
        return []
    hits: List[str] = []
    for m in _PUBLIC_CLOUD_STORE.finditer(output_text):
        token = m.group(0)
        # Allow explicit private/self-hosted MinIO / VPC private bucket wording nearby
        # only when the hit itself is generic「对象存储」and private framing is clear.
        start = max(0, m.start() - 48)
        end = min(len(output_text), m.end() + 48)
        ctx = output_text[start:end]
        if re.search(r"私有化|内网|专有云|VPC|私有桶|自建|本地", ctx) and not re.search(
            r"阿里云|腾讯云|七牛|AWS|Amazon|公有云", token, re.I
        ):
            continue
        hits.append(token)
    return list(dict.fromkeys(hits))


def _architecture_section_gaps(input_text: str, output: Any, output_text: str) -> List[str]:
    """If the prompt asked for review sections, require them in the product.

    Accept either Chinese prose headings or structured JSON keys used by
    architecture_design / architect_agent templates.
    """
    if not input_text:
        return []
    blob = output_text or ""
    if isinstance(output, dict):
        blob = f"{blob}\n{_text_blob(output)}"
    # Dedicated security body (do not rely on overview「安全性」alone)
    security_blob = ""
    if isinstance(output, dict):
        for k in ("security", "security_and_compliance", "compliance", "安全与合规", "安全"):
            if not _arch_field_empty(output.get(k)):
                security_blob = _arch_field_as_text(output.get(k))
                break
    checks = [
        (
            # 勿用整篇 JSON 里偶然出现的「待确认/open_questions」冒充本章节
            r"上下文|假设",
            r"(?:^|\n)\s*#{1,4}\s*[^\n]*(?:上下文|假设)|(?:^|\n)\s*上下文与假设\s*[:：]",
            "上下文与假设",
            ("context", "assumptions", "context_and_assumptions", "hypothesis", "上下文与假设"),
            r"假设|上下文",
        ),
        (
            r"数据流",
            r"数据流|data_flow|上报.{0,12}审批|审批.{0,12}派修",
            "数据流",
            ("data_flow", "data_flows", "flows"),
            r"数据流|data_flow",
        ),
        (
            r"安全|合规",
            # Prefer dedicated security field; fall back to strong themes outside overview fluff
            r"(?:照片落地|落地存储|脱敏|内网边界|私有化|不上公网|不外传|私有桶|MinIO)",
            "安全与合规",
            ("security", "compliance", "security_and_compliance", "安全与合规", "安全"),
            r"安全|合规|security",
        ),
        (
            r"分期|6\s*周|风险",
            r"分期|里程碑|风险|试点|week|slice|phase|rollout",
            "分期切片与风险",
            ("rollout", "risks", "phases", "pilot", "rollout_and_risks", "milestones", "timeline"),
            r"分期|风险|试点|6\s*周|里程碑|rollout|phase",
        ),
    ]
    gaps: List[str] = []
    for in_pat, out_pat, label, struct_keys, key_pat in checks:
        if not re.search(in_pat, input_text):
            continue
        if label == "安全与合规":
            # overview「以确保系统的安全性」must not satisfy this section
            sec_src = security_blob or ""
            if sec_src and re.search(
                r"落地|脱敏|内网|私有化|不上公网|不外传|私有桶|MinIO|专有云|VPC",
                sec_src,
                re.I,
            ):
                continue
            if not sec_src and re.search(out_pat, blob, re.I):
                # Strong theme exists somewhere — only OK if not solely from a thin overview
                overview = ""
                if isinstance(output, dict):
                    overview = str(output.get("overview") or "")
                rest = blob
                if overview:
                    rest = blob.replace(overview, " ", 1)
                if re.search(out_pat, rest, re.I):
                    continue
            # struct keys with empty/weak values still gap
            if isinstance(output, dict):
                weak = True
                for k in struct_keys:
                    val = output.get(k)
                    if _arch_field_empty(val):
                        continue
                    txt = _arch_field_as_text(val)
                    if re.search(
                        r"落地|脱敏|内网|私有化|不上公网|不外传|私有桶|MinIO|专有云|VPC",
                        txt,
                        re.I,
                    ):
                        weak = False
                        break
                if not weak:
                    continue
            gaps.append(label)
            continue
        if re.search(out_pat, blob, re.I):
            continue
        if isinstance(output, dict):
            hit = False
            for k in struct_keys:
                val = output.get(k)
                if val in (None, "", [], {}):
                    continue
                if isinstance(val, (list, dict)) and len(val) == 0:
                    continue
                hit = True
                break
            if not hit:
                # Local-LLM often uses Chinese key names (e.g. 「6周试点的分期切片与风险」)
                for k, val in output.items():
                    if not isinstance(k, str) or not re.search(key_pat, k, re.I):
                        continue
                    if val in (None, "", [], {}):
                        continue
                    if isinstance(val, (list, dict)) and len(val) == 0:
                        continue
                    hit = True
                    break
            if hit:
                continue
        gaps.append(label)
    return gaps


_API_PLACEHOLDER_BODY = re.compile(
    r"^(处理结果|审批结果|派修结果|照片数据|看板数据|报障ID|审批状态|派修人员|"
    r"照片上传成功|审批通过|派修任务完成|string|xxx|TODO|待定)$",
    re.I,
)
# Label-like leaves: 「班组长ID」「照片ID」「派修人员ID」「…数据」「…成功」
_API_PLACEHOLDER_LEAF = re.compile(
    r"(ID|id|数据|成功|通过|完成|待定|TODO|string|xxx)$|"
    r"^(照片|报障|审批|派修|看板|用户|人员|状态)",
    re.I,
)


def _api_payload_is_placeholder(val: Any) -> bool:
    """True when request/response body is an empty shell or label-only placeholder."""
    if val is None:
        return True
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return False  # example scalars (ticket_count: 10) are not empty shells
    if isinstance(val, str):
        s = val.strip()
        if (not s) or len(s) < 4:
            # Numeric example leaves from walk(str(10)) → "10" — keep as rich
            if s.isdigit() or re.fullmatch(r"-?\d+(\.\d+)?", s or ""):
                return False
            return True
        if _API_PLACEHOLDER_BODY.match(s):
            return True
        # Short Chinese labels without schema shape
        if len(s) <= 12 and _API_PLACEHOLDER_LEAF.search(s):
            return True
        return False
    if isinstance(val, dict):
        if not val:
            return True
        # {"headers":{},"body":"处理结果"} or {"body":{"image":"照片数据"}}
        body = val.get("body") if "body" in val else val
        if body is None:
            body = {k: v for k, v in val.items() if k not in ("headers", "status")}
        if isinstance(body, str):
            return _api_payload_is_placeholder(body)
        if isinstance(body, dict):
            if not body:
                return True
            # Nested object with only placeholder leaves → still thin
            leaves: List[str] = []

            def _walk(obj: Any) -> None:
                if isinstance(obj, dict):
                    if not obj:
                        leaves.append("")
                        return
                    for v in obj.values():
                        _walk(v)
                elif isinstance(obj, list):
                    if not obj:
                        leaves.append("")
                    else:
                        for x in obj[:8]:
                            _walk(x)
                elif isinstance(obj, (int, float, bool)):
                    leaves.append(obj)  # keep typed scalar
                else:
                    leaves.append(str(obj).strip())

            _walk(body)
            if not leaves:
                return True
            return all(_api_payload_is_placeholder(x) or x == "" for x in leaves)
        return False
    return False


def _architecture_api_item_rich(item: Dict[str, Any]) -> bool:
    """One endpoint is rich only if request AND response look like a draft contract."""
    if not isinstance(item, dict):
        return False
    method = str(item.get("method") or "").strip().upper()
    path = str(item.get("path") or item.get("url") or "").strip()
    if not method or not path.startswith("/"):
        return False
    req = item.get("request") or item.get("request_body")
    res = item.get("response") or item.get("response_body")
    if req is None and res is None:
        desc = str(item.get("description") or "")
        return len(desc) >= 40 and bool(re.search(r"请求|响应|body|status|参数", desc, re.I))
    # GET may have empty request body, but response must be structured (not「看板数据」)
    if method == "GET":
        return not _api_payload_is_placeholder(res)
    req_ok = not _api_payload_is_placeholder(req)
    res_ok = not _api_payload_is_placeholder(res)
    if req_ok and res_ok:
        return True
    # Draft-grade (local models): rich request + HTTP status + non-empty object body
    # even if body is only {message:「审批成功」} (run-fc50ccc06b56).
    if req_ok and isinstance(res, dict):
        st = res.get("status")
        body = res.get("body") if "body" in res else None
        if body is None:
            body = {k: v for k, v in res.items() if k not in ("headers", "status")}
        if st is not None and isinstance(body, dict) and body:
            return True
    return False


def _architecture_api_thin(input_text: str, output: Any) -> bool:
    """True when input asked for API contracts but items lack request/response detail."""
    if not input_text or not re.search(r"API|端点|契约", input_text):
        return False
    if not isinstance(output, dict):
        # Prose-only: require method+path + 请求/响应 cues
        blob = _text_blob(output)
        if not re.search(r"(GET|POST|PUT|PATCH|DELETE)\s+/[\w\-/{}$]+", blob, re.I):
            return True
        if not re.search(r"请求|响应|request|response|body|status", blob, re.I):
            return True
        return False
    apis = _collect_architecture_apis(output)
    if not apis:
        return True
    rich = sum(1 for item in apis if isinstance(item, dict) and _architecture_api_item_rich(item))
    # Need majority rich, and at least 2 when 3+ endpoints present
    if len(apis) >= 3:
        return rich < max(2, (len(apis) + 1) // 2)
    return rich == 0


def _architecture_security_thin(input_text: str, output: Any) -> bool:
    """Input asked for 安全与合规 with 落地/脱敏/内网 but security body is a slogan."""
    if not input_text or not re.search(r"安全|合规", input_text):
        return False
    if not re.search(r"落地|脱敏|内网", input_text):
        return False
    if not isinstance(output, dict):
        return not re.search(r"落地|脱敏|内网|私有化|私有桶|MinIO|VPC", _text_blob(output), re.I)
    sec = ""
    for k in ("security", "security_and_compliance", "compliance", "安全与合规", "安全"):
        if not _arch_field_empty(output.get(k)):
            sec = _arch_field_as_text(output.get(k))
            break
    if not sec.strip():
        return True
    themes = sum(
        1
        for p in (r"落地|存储|私有桶|MinIO|本地盘", r"脱敏", r"内网|私有化|VPC|专有云")
        if re.search(p, sec, re.I)
    )
    # Need ≥2 of 落地/脱敏/内网 themes in the dedicated security field
    return themes < 2


def _architecture_rollout_thin(input_text: str, output: Any) -> bool:
    """6周试点 asked but rollout has no week slices (only generic 车间/风险)."""
    if not input_text or not re.search(r"6\s*周|分期|试点", input_text):
        return False
    blob = ""
    if isinstance(output, dict):
        for k in ("rollout_and_risks", "rollout", "phases", "risks", "milestones", "timeline"):
            if not _arch_field_empty(output.get(k)):
                blob = _text_blob(output.get(k))
                break
        if not blob:
            for k, v in output.items():
                if isinstance(k, str) and re.search(r"分期|风险|试点|6\s*周|rollout|phase", k, re.I):
                    blob = _text_blob(v)
                    break
    else:
        blob = _text_blob(output)
    if not blob.strip():
        return True
    has_week = bool(re.search(r"(W\s*[1-6]|第[一二三四五六1-6]周|周次|week\s*[1-6]|6\s*周)", blob, re.I))
    return not has_week


def ensure_architecture_rollout_weeks(output: Any, input_text: str = "") -> Any:
    """When input asks for a 6-week pilot but rollout lacks W1–W6, fill a deterministic plan.

    Local models often emit ``phase: 1 / 试点一个车间`` without week slices
    (run-4c35b853ce52). Delivery + quality review share this normalize so
    re-runs are not stuck on ``architecture_sections_thin`` after SOP already
    requires weekly slices.
    """
    if not isinstance(output, dict):
        return output
    if not input_text or not re.search(r"6\s*周|分期|试点", input_text):
        return output
    if not _architecture_rollout_thin(input_text, output):
        return output

    flow = f"{_text_blob(output.get('data_flow'))} {input_text}"
    slices: List[str] = []
    for needle, label in (
        ("上报", "W1 上报闭环（拍照入库）"),
        ("审批", "W2 审批闭环"),
        ("派修", "W3 派修闭环"),
        ("看板", "W4 看板可见"),
    ):
        if needle in flow:
            slices.append(label)
    if len(slices) < 2:
        slices = [
            "W1 核心上报闭环",
            "W2 审批闭环",
            "W3 派修闭环",
            "W4 看板可见",
        ]
    used = {
        m.group(1)
        for s in slices
        for m in [re.search(r"W\s*([1-6])", s, re.I)]
        if m
    }
    if "5" not in used:
        slices.append("W5 内网存储与通知通道加固")
    if "6" not in used:
        slices.append("W6 单车间试点验收与风险复盘")

    prior = ""
    for k in ("rollout_and_risks", "rollout", "phases", "risks"):
        if not _arch_field_empty(output.get(k)):
            prior = _text_blob(output.get(k))
            break
    risks = "风险：通知通道（钉钉·待确认）对接延误；内网存储权限与容量。"
    m = re.search(r"风险[：:]?[^\n]{0,100}", prior) if prior else None
    if m:
        risks = m.group(0).strip()
        if not risks.startswith("风险"):
            risks = f"风险：{risks}"

    out = dict(output)
    body = "；".join(slices) + "。" + risks
    if "车间" in prior or "车间" in input_text:
        body += " 范围：单车间试点。"
    out["rollout_and_risks"] = body
    return out


def _dingtalk_invented_integration(input_text: str, output: Any) -> bool:
    """Input says no DingTalk API docs, but product claims concrete DingTalk SDK/通知接口.

    Do NOT flag honest prose like「对接钉钉平台，但暂无明确的 API 文档」— that is
    compliance wording, not inventing an SDK (run-e86a7bee9828 false positive).
    Also allow SOP placeholders「对接钉钉通知通道」and open_questions asking how to
    integrate (run-5eb7d4547159 false positive).
    """
    if not input_text or not output:
        return False
    if not re.search(r"暂无\s*API|无\s*API\s*文档|API\s*未开放|禁止编造|暂无钉钉", input_text):
        return False
    blob = _text_blob(output)
    # Concrete invent — always fail.
    # Do NOT treat「不实际调用钉钉 / 未调用钉钉」as invent (run-4c35b853ce52 FP).
    if re.search(r"DingTalk\s*SDK|钉钉\s*SDK", blob, re.I):
        return True
    if re.search(
        r"钉钉(?:审批|派修|通知)接口|与钉钉进行交互，实现|对接钉钉实现|对接钉钉完成",
        blob,
        re.I,
    ):
        return True
    for m in re.finditer(r"调用钉钉", blob):
        pre = blob[max(0, m.start() - 10) : m.start()]
        if re.search(r"(不|未|勿|禁|无需|不用|实际不)\s*$", pre) or "不实际" in pre:
            continue
        return True
    # Bare「对接钉钉」only fails when nearby text does NOT acknowledge pending/no-API
    # or the SOP-approved「通知通道」placeholder.
    pending = (
        r"待确认|暂无|未开放|未提供|禁止编造|待对接|API\s*文档|通知通道|"
        r"如何对接|怎样对接|\?"
    )
    for m in re.finditer(r"对接钉钉", blob):
        window = blob[max(0, m.start() - 24) : min(len(blob), m.start() + 72)]
        if re.search(pending, window):
            continue
        return True
    return False


def _architecture_data_flow_incomplete(input_text: str, output: Any) -> List[str]:
    """When input lists 上报/审批/派修/看板, require each theme in data_flow content."""
    if not input_text or not re.search(r"数据流", input_text):
        return []
    themes = []
    for label, pat in (
        ("上报", r"上报|拍照|采集|capture|upload"),
        ("审批", r"审批|approve|approval"),
        ("派修", r"派修|派单|distribute|dispatch|assignee"),
        ("看板", r"看板|dashboard|汇总|统计"),
    ):
        if re.search(label, input_text):
            themes.append((label, pat))
    if len(themes) < 2:
        return []
    flow_blob = ""
    if isinstance(output, dict):
        for k in ("data_flow", "data_flows", "flows", "数据流"):
            if not _arch_field_empty(output.get(k)):
                flow_blob = _text_blob(output.get(k))
                break
    if not flow_blob:
        flow_blob = _text_blob(output)
    missing = [lab for lab, pat in themes if not re.search(pat, flow_blob, re.I)]
    return missing


def _architecture_pending_markers_missing(input_text: str, output: Any) -> bool:
    """Input asked to mark 待确认 but product has none in context / OQ / component tech."""
    if not input_text or not re.search(r"待确认|标明待确认|open_questions", input_text):
        return False
    blob_parts: List[str] = []
    if isinstance(output, dict):
        for k in (
            "context",
            "assumptions",
            "context_and_assumptions",
            "open_questions",
            "hypothesis",
            "上下文与假设",
        ):
            if not _arch_field_empty(output.get(k)):
                blob_parts.append(_text_blob(output.get(k)))
        # overview alone is weak — only count if it has explicit pending markers
        ov = output.get("overview")
        if isinstance(ov, str) and re.search(r"待确认|未开放|暂无|待定|无法确认", ov):
            blob_parts.append(ov)
        # SOP puts 钉钉 pending on component tech: 「通知通道（钉钉·待确认）」
        comps = output.get("components") or output.get("folder_structure")
        if isinstance(comps, list):
            for c in comps:
                if isinstance(c, dict):
                    blob_parts.append(
                        _text_blob(
                            {
                                "tech": c.get("tech"),
                                "responsibility": c.get("responsibility"),
                                "name": c.get("name"),
                            }
                        )
                    )
                elif isinstance(c, str):
                    blob_parts.append(c)
    else:
        blob_parts.append(_text_blob(output))
    blob = "\n".join(blob_parts)
    if not blob.strip():
        return True
    return not re.search(r"待确认|未开放|暂无|待定|无法确认|open_question", blob, re.I)


def _architecture_missing_dashboard_api(input_text: str, output: Any) -> bool:
    """Input asked for 看板 flow + API contracts but no dashboard/list/stats endpoint."""
    if not input_text:
        return False
    if not (re.search(r"看板", input_text) and re.search(r"API|端点|契约", input_text)):
        return False
    apis = _collect_architecture_apis(output) if isinstance(output, dict) else []
    if not apis:
        return False  # covered by api_thin
    blob = _text_blob(apis)
    return not re.search(r"看板|dashboard|stats|summary|list|汇总|/board|/kanban", blob, re.I)

def _sop_fix(kind: str, asset_label: str) -> Dict[str, str]:
    if kind == "agent":
        return {
            "where": "edit_agent_sop",
            "where_label": f"编辑 Agent「{asset_label}」→ SOP / 高级",
            "how": "在 AGENT.md / System Prompt / SOP 中写明输出铁律（保留口述硬约束、禁编造、草稿轮 open_questions 非空），保存后用同一用例再执行。",
        }
    if kind == "tool":
        return {
            "where": "edit_tool_schema",
            "where_label": f"编辑 Tool「{asset_label}」→ description / parameters（AI 审核）",
            "how": "对照 error 补齐必填参数与 schema；用「AI 审核」一键补描述/parameters，勿套用 Skill SOP 一键修复。",
        }
    return {
        "where": "edit_skill_sop",
        "where_label": f"编辑 Skill「{asset_label}」→ SOP / 输出铁律",
        "how": "在 SKILL.md 的「输出铁律 / 反模式 / completion_criterion」中加固约束，保存并重新加载 Skill 后，用同一测试用例再跑一轮对照。",
    }


def _architecture_sop_fix(kind: str, asset_label: str) -> Dict[str, str]:
    """Architecture product issues live in Skill SOP (architecture_design), not Agent chat SOP."""
    if kind == "agent":
        return {
            "where": "edit_skill_sop",
            "where_label": "编辑 Skill「architecture_design」→ SOP / 输出铁律",
            "how": (
                "在 architecture_design 的 SKILL.md「输出铁律」写明须覆盖上下文与假设 / 数据流 / 安全与合规 / 分期与风险；"
                "禁止编造未给定第三方接口。一键修复会写入绑定 Skill（并镜像 AGENT.md）。保存后用同一用例再执行。"
            ),
        }
    return _sop_fix(kind, asset_label or "architecture_design")


def review_execution_output(
    *,
    kind: str = "skill",
    asset_id: str = "",
    asset_name: str = "",
    input_payload: Any = None,
    output: Any = None,
    status: str = "completed",
    hints: str = "",
    skill_trace: Any = None,
    execution_id: str = "",
) -> Dict[str, Any]:
    """Rule-based review of a finished skill/agent run.

    Returns AssetAudit-compatible ``issues`` + ``summary``, plus ``fix_guide``.
    Does not fail the run — advisory only (callers use ``quality_review_blocks_success``
    to flip completed→failed for hard coding fails).
    """
    issues: List[Dict[str, Any]] = []
    label = (asset_name or asset_id or "当前资产").strip()
    sop = _sop_fix(kind, label)
    in_text = _input_text(input_payload)
    persist_envelope = output
    raw_out = sanitize_architecture_third_party(
        ensure_architecture_rollout_weeks(
            ensure_architecture_section_fields(_unwrap_output(output)),
            in_text,
        ),
        in_text,
    )
    out_text = _text_blob(raw_out)
    st = str(status or "").lower()

    def _pack(verdict_hint: str = "") -> Dict[str, Any]:
        summary = summarize_audit_issues(issues)
        ok_runtime = st in ("completed", "ok", "success", "")
        content_ok = summary.get("errors", 0) == 0
        verdict = (
            "pass"
            if content_ok and not summary.get("warnings")
            else ("warn" if content_ok else "fail")
        )
        if verdict_hint:
            verdict = verdict_hint
        headline = {
            "pass": "流程已完成，产物未发现明显质量问题",
            "warn": "流程已完成，但产物有待改进项",
            "fail": "流程已完成，产物未达可验收质量（勿当作冒烟通过）",
        }.get(verdict, "流程已完成，产物未达可验收质量（勿当作冒烟通过）")
        if st in ("timeout", "failed", "error", "cancelled", "canceled"):
            headline = {
                "timeout": "执行超时，未形成可验收产物（勿当作冒烟通过）",
                "failed": "执行失败，未形成可验收产物（勿当作冒烟通过）",
                "error": "执行失败，未形成可验收产物（勿当作冒烟通过）",
                "cancelled": "执行已取消",
                "canceled": "执行已取消",
            }.get(st, headline)
            if verdict == "pass":
                verdict = "fail"
        fixable_codes = [
            str(i.get("code"))
            for i in issues
            if i.get("fix_available") and isinstance(i.get("fix"), dict) and i.get("code")
        ]
        fix_guide = {
            "primary_where": sop["where"],
            "primary_label": sop["where_label"],
            "primary_how": sop["how"],
            "steps": [
                "1. 优先点「一键修复」：自动把对应铁律写入 SKILL.md（幂等，可重复点）。",
                f"2. 或手动打开：{sop['where_label']}",
                f"3. {sop['how']}",
                "4. 保存/重载后，用同一测试用例再执行对照（旧产物不会自动变绿）。",
            ],
        }
        # Architecture product issues: primary guidance → Skill SOP (not Agent chat)
        if any(str(i.get("code") or "") in _ARCH_QUALITY_CODES for i in issues):
            arch_guide = _architecture_sop_fix(kind, label)
            fix_guide = {
                "primary_where": arch_guide["where"],
                "primary_label": arch_guide["where_label"],
                "primary_how": arch_guide["how"],
                "steps": [
                    "1. 优先点「一键修复」：自动把对应铁律写入 architecture_design 的 SKILL.md（幂等）。",
                    f"2. 或手动打开：{arch_guide['where_label']}",
                    f"3. {arch_guide['how']}",
                    "4. 保存/重载后，用同一测试用例再执行对照（旧产物不会自动变绿）。",
                ],
            }
        primary_action = "apply_sop_fix"
        # Empty/timeout: SOP 一键修复帮不上忙 — 引导看运行态
        if any(
            str(i.get("code") or "")
            in (
                "empty_output",
                "runtime_timeout",
                "runtime_failed",
                "canned_sop_failure",
                "clarification_only",
                "thin_code_stub",
                "language_mismatch",
                "off_spec_coding",
                "autoreview_incomplete",
                "scaffold_not_on_disk",
            )
            for i in issues
        ):
            primary_action = "check_runtime"
            fix_guide = {
                "primary_where": "check_runtime",
                "primary_label": "诊断详情 / 执行轨迹",
                "primary_how": (
                    "先确认本轮是否真的产出了结果（非空输出、非超时）。"
                    "空输出或超时时点「一键修复 SOP」只会显示「已写入」（幂等），不会让本轮产物变绿。"
                ),
                "steps": [
                    "1. 看执行轨迹是否有 Skill 观察结果与最终输出。",
                    "2. 若超时/卡死：检查模型是否响应、是否 LLM stalled。",
                    "3. 有真实产物后再用质量复核；若仍缺章节/硬约束，再点一键修复并重跑对照。",
                ],
            }
        if any(
            str(i.get("code") or "")
            in (
                "missing_auth_todo",
                "dangling_local_import",
                "fake_integration_claim",
            )
            for i in issues
        ):
            primary_action = "check_runtime"
        sop_iron = probe_quality_sop_markers(
            kind=kind,
            asset_id=asset_id,
            hints=hints,
            issue_codes=fixable_codes,
        )
        rerun_overlay = ""
        if (
            primary_action != "check_runtime"
            and sop_iron.get("all_present")
            and fixable_codes
            and not content_ok
        ):
            primary_action = "rerun_with_fail_constraints"
            rerun_overlay = build_fail_constraint_overlay(issues)
            fix_guide = {
                **fix_guide,
                "primary_how": (
                    "相关 SOP 铁律已在 Skill/Agent 中；再点「一键修复」只会显示已写入。"
                    "请点「按失败点重跑」——会把本轮失败约束注入同一用例，强制模型遵守。"
                ),
                "steps": [
                    "1. 优先点「按失败点重跑」：同一用例 + 失败点约束叠加（不改 SKILL.md）。",
                    "2. 若重跑仍失败：核对模型是否在遵守约束，或点「去改 SOP」手工加严。",
                    "3. 「一键修复 SOP」此时多为幂等 noop，可忽略。",
                ],
            }
        elif primary_action == "apply_sop_fix" and sop_iron.get("missing_codes"):
            # Partial: keep apply for missing; note present ones
            present_n = len(sop_iron.get("present_codes") or [])
            if present_n:
                fix_guide = {
                    **fix_guide,
                    "steps": [
                        f"1. 已有 {present_n} 类铁律在 SOP 中；缺 {len(sop_iron['missing_codes'])} 类 → 点「一键修复」补齐。",
                        "2. 补齐后点「按失败点重跑」对照（旧产物不会自动变绿）。",
                        f"3. 或手动打开：{fix_guide.get('primary_label') or sop['where_label']}",
                    ],
                }
        return {
            "ok": content_ok and ok_runtime,
            "runtime_ok": ok_runtime,
            "verdict": verdict,
            "headline": headline,
            "issues": issues,
            "summary": summary,
            "fix_guide": fix_guide,
            "asset": {"kind": kind, "id": asset_id, "name": label},
            "fixable_issue_codes": fixable_codes,
            "primary_action": primary_action,
            "sop_iron": {
                "present_codes": sop_iron.get("present_codes") or [],
                "missing_codes": sop_iron.get("missing_codes") or [],
                "all_present": bool(sop_iron.get("all_present")),
                "skill_ids": sop_iron.get("skill_ids") or [],
            },
            "rerun_constraint_overlay": rerun_overlay,
        }

    if st in ("timeout", "failed", "error", "cancelled", "canceled"):
        code = "runtime_timeout" if st == "timeout" else "runtime_failed"
        issues.append(
            _issue(
                code,
                f"执行状态为 {st}，无可用产物",
                severity="error",
                suggestion="先修复运行问题（超时/模型卡住/Skill 失败），再谈 SOP 铁律与产物章节。",
                where="check_runtime",
                where_label="诊断详情 / 执行轨迹",
                how="查看 orphan_watchdog / LLM stall / Skill 错误 span；勿反复点一键修复期望空产物变绿。",
            )
        )
        return _pack("fail")

    if st in ("completed", "ok", "success", "") and not (out_text or "").strip():
        empty_hint = (
            "检查 Tool handler 是否返回了结果，或参数是否触发了空分支。"
            if kind == "tool"
            else "检查 Skill handler / prompt 是否真的产出结果；或看诊断详情中的错误 span。"
        )
        issues.append(
            _issue(
                "empty_output",
                "状态为完成，但输出为空",
                severity="error",
                suggestion=empty_hint,
                where="check_runtime",
                where_label="诊断详情 / 执行轨迹",
                how="空产物与 SOP 铁律无关：先确认 Skill 是否返回正文，再重跑；勿只点一键修复。",
            )
        )
        return _pack("fail")

    # Completed with a Model error / LLM stall string — not a real deliverable.
    if st in ("completed", "ok", "success", "") and _output_is_model_runtime_failure(out_text):
        issues.append(
            _issue(
                "model_runtime_error",
                "状态为完成，但输出是模型/运行时错误（超时、inflight 占槽等），无真实产物",
                severity="error",
                suggestion="先解除本地 LLM 排队/超时，再重跑；勿把 Model error 当代码交付。",
                where="check_runtime",
                where_label="诊断详情 / 执行轨迹",
                how="查看 llm_timeout / local_llm_inflight；降低并发或换模型后重试。",
            )
        )
        return _pack("fail")

    if st in ("completed", "ok", "success", "") and _output_is_canned_sop_failure(out_text):
        issues.append(
            _issue(
                "canned_sop_failure",
                "状态为完成，但输出是 SOP 错误处理套话或 SIDE_EFFECT_UNREALIZED，不是真实副作用结果",
                severity="error",
                suggestion=(
                    "prompt Skill 不能假装上传/写盘。补 handler.py 并走已有 tool/syscall，"
                    "或把 effects 改为 emit。"
                ),
                where="check_runtime",
                where_label="Skill 执行结果 / SKILL.md",
                how="看是否未调用 Tool；声明 write 却无 handler 会被执行门拒绝。",
            )
        )
        return _pack("fail")

    # Task asked for a concrete deliverable, but model only asked the user to confirm.
    # Common false-green on coding Agents (auto_done after a planning/clarify turn).
    if (
        st in ("completed", "ok", "success", "")
        and (
            _input_asks_coding_delivery(in_text)
            or _detect_requested_code_language(in_text)
        )
        and _output_is_clarification_only(out_text)
    ):
        issues.append(
            _issue(
                "clarification_only",
                "任务要求交付产物，但输出只在追问/确认，未给出可验收代码或接口实现",
                severity="error",
                suggestion=(
                    "禁止用「请确认是否准备好」结束本轮；应直接调用绑定 Skill/Tool 产出代码，"
                    "或输出 ## FILE: / curl 示例。缺上游 api_contracts 时写清假设并仍交付最小可运行切片。"
                ),
                where="check_runtime",
                where_label="执行轨迹 / Agent SOP",
                how=(
                    "看轨迹是否只有 LLM generate + auto_done、无 skill_call；"
                    "在 AGENT.md 收紧「禁止澄清式收尾」或为单主技能设 skill_delivery=once。"
                ),
            )
        )

    # Coding deliverable asked, but output is DONE + empty ## FILE / thin {code,language} stub.
    if (
        st in ("completed", "ok", "success", "")
        and (
            _input_asks_coding_delivery(in_text)
            or _detect_requested_code_language(in_text)
        )
        and _output_is_thin_code_stub(out_text, raw_out)
    ):
        issues.append(
            _issue(
                "thin_code_stub",
                "任务要求可运行代码，但产物只有 DONE/## FILE 空壳（无路由/模型/函数体）",
                severity="error",
                suggestion=(
                    "禁止仅输出 DONE 或空 ## FILE 头；须含完整实现（如 FastAPI 路由 + Pydantic model）"
                    "以及至少 1 个成功/失败示例与 curl 验证说明。鉴权未给出时标 TODO，禁止假实现。"
                ),
                where="check_runtime",
                where_label="执行轨迹 / code_generation 产物",
                how=(
                    "看 skill_call(code_generation) 观察结果是否只有 header；"
                    "弱模型常把 DONE\\n 写成 DONEn——应拒绝并重试，不要把空壳当 skill_delivery 成功。"
                ),
            )
        )

    # Wrong language / placeholder shell / autoreview not really done (run-da9cc25d).
    if st in ("completed", "ok", "success", ""):
        for code in _coding_contract_fail_codes(
            in_text,
            out_text,
            persist_envelope if persist_envelope is not None else raw_out,
            hints=hints,
            skill_trace=skill_trace,
            run_id=str(execution_id or ""),
        ):
            if code == "language_mismatch":
                req_l = _detect_requested_code_language(in_text) or "?"
                got_l = _detect_output_code_language(out_text, raw_out) or "?"
                issues.append(
                    _issue(
                        "language_mismatch",
                        f"任务要求 {req_l}，但产物语言为 {got_l}",
                        severity="error",
                        suggestion=(
                            f"必须用任务指定语言交付（{req_l}）；禁止用 {got_l} 占位文件或错误 language 字段收口。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how=(
                            "核对输入中的 TypeScript/Python 要求与 ## FILE 扩展名、```fence、"
                            "以及 {code,language} 信封是否一致；不一致须重跑，不得假绿。"
                        ),
                    )
                )
            elif code == "off_spec_coding":
                issues.append(
                    _issue(
                        "off_spec_coding",
                        "编码产物未覆盖任务契约（缺约定 API 路径，或仅为 print/占位脚手架）",
                        severity="error",
                        suggestion=(
                            "按输入中的 endpoints/models 生成可调用实现；禁止用 print('DONE') / "
                            "空 autoreview.py 冒充交付。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how=(
                            "对照输入 path（如 /api/tasks）与模型名是否出现在产物中；"
                            "多文件脚手架若只有 print/placeholder，按失败重跑。"
                        ),
                    )
                )
            elif code == "autoreview_incomplete":
                issues.append(
                    _issue(
                        "autoreview_incomplete",
                        "任务要求调用 autoreview，但未真正通过审查（approval_required / 占位文件）",
                        severity="error",
                        suggestion=(
                            "在 code_generation 产出实质代码后调用绑定的 autoreview Skill，"
                            "并以审查通过后再 DONE；禁止生成假 autoreview.py。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / autoreview",
                        how=(
                            "看 skill 序列是否含 status=success 的 autoreview；"
                            "approval_required / 跳过 / 产物内嵌 print Autoreview 均不算通过。"
                        ),
                    )
                )
            elif code == "missing_auth_todo":
                issues.append(
                    _issue(
                        "missing_auth_todo",
                        "任务要求鉴权未给出时标 TODO，但产物未标注鉴权 TODO",
                        severity="error",
                        suggestion=(
                            "在代码注释或请求头旁写明 `// TODO: auth/鉴权`；"
                            "禁止假实现「已对接钉钉」。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how=(
                            "搜索产物是否含 TODO+鉴权/auth；仅有 axios 调用而无 TODO 视为未达标。"
                        ),
                    )
                )
            elif code == "dangling_local_import":
                dang = _dangling_local_imports(
                    out_text if out_text.strip() else _text_blob(raw_out)
                )
                shown = ", ".join(dang[:4]) if dang else "./…"
                issues.append(
                    _issue(
                        "dangling_local_import",
                        f"编码产物引用了未交付的相对模块（{shown}）",
                        severity="error",
                        suggestion=(
                            "冒烟切片禁止 `from './utils'` 等悬空导入；"
                            "辅助逻辑内联，或另起 ## FILE 一并交付。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how=(
                            "对照 ## FILE 列表与相对 import/require；"
                            "同批交付的 types/apiClient 之间可互相 import；"
                            "外部包（axios 等）允许，未交付的 ./utils 等不允许。"
                        ),
                    )
                )
            elif code == "undeclared_api_schema_assumption":
                issues.append(
                    _issue(
                        "undeclared_api_schema_assumption",
                        "任务要求不自行推断 API，但产物定义了请求/响应字段且未标注临时假设",
                        severity="warning",
                        suggestion=(
                            "在 types/Request 旁显式写「临时假设 / ASSUMPTION，"
                            "以真实 api_contracts 覆盖」；禁止写「本文件不推断」"
                            "同时又编造完整字段。"
                        ),
                        where="edit_skill_sop",
                        where_label="编辑 Skill「code_generation」→ SOP",
                        how=(
                            "补铁律：无字段级 contracts 时允许最小切片，"
                            "但必须标注临时假设；禁止自相矛盾的「不推断」表述。"
                        ),
                    )
                )
            elif code == "frontend_module_incomplete":
                issues.append(
                    _issue(
                        "frontend_module_incomplete",
                        "前端任务要求可组装模块，但产物缺少类型/apiClient + 页面（.tsx）",
                        severity="error",
                        suggestion=(
                            "至少交付 2 个 ## FILE：frontend/src/types.ts 或 apiClient.ts，"
                            "以及 frontend/src/pages/*.tsx；页面只调 apiClient，不要只交单函数。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how="统计 ## FILE 路径；须同时含 .ts 客户端/类型与 .tsx 页面。",
                    )
                )
            elif code == "frontend_flow_pages_incomplete":
                issues.append(
                    _issue(
                        "frontend_flow_pages_incomplete",
                        "多流程前端任务被压成单页冒烟，缺少按流程拆分的页面",
                        severity="error",
                        suggestion=(
                            "PRD 含上报/审批/派修时，至少交付 3 个 "
                            "`## FILE: frontend/src/pages/*.tsx`；"
                            "apiClient 覆盖契约每个 endpoint；缺接口标 BLOCKED。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how=(
                            "对照输入是否含多流程关键词/页面名；"
                            "统计 /pages/ 下 ## FILE 数量须 ≥ 3。"
                        ),
                    )
                )
            elif code == "isolated_fe_vite_files":
                issues.append(
                    _issue(
                        "isolated_fe_vite_files",
                        "单独测切片不应交付 App.tsx / main.tsx / Vite 工程文件（任意 code Agent）",
                        severity="warning",
                        suggestion=(
                            "只交任务列出的模块文件（前端 types+apiClient+pages，后端 routes+schemas）。"
                            "App.tsx / main.tsx / package.json 留给「有脚手架挂路由」或 scaffold_agent。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how="输入含「单独测·可组装切片」时，## FILE 不得含 App.tsx、main.tsx、package.json、vite.config。",
                    )
                )
            elif code == "scaffold_startup_incomplete":
                issues.append(
                    _issue(
                        "scaffold_startup_incomplete",
                        "脚手架缺少可启动的 FastAPI + Vite 入口链（含 tsconfig；Python 三引号须成对）",
                        severity="error",
                        suggestion=(
                            "后端至少 `main.py` + `requirements.txt`（三引号成对，禁止开头孤立 `\"\"\"`）；"
                            "前端至少 `frontend/package.json`、`vite.config.ts`、"
                            "`index.html`、`src/main.tsx`、`src/App.tsx`、`frontend/tsconfig.json`。"
                            "根 README 写清 uvicorn 与 npm run dev。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how=(
                            "统计 ## FILE 是否构成入口链；Vite+TS 须有 tsconfig；"
                            "每个 .py 的三引号须成对。"
                        ),
                    )
                )
            elif code == "scaffold_not_on_disk":
                issues.append(
                    _issue(
                        "scaffold_not_on_disk",
                        "可启动脚手架没有落到磁盘（仅有 ## FILE 观察正文）",
                        severity="error",
                        suggestion=(
                            "确认 `AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS` 包含 `$AIPLAT_HOME`；"
                            "产物应出现在 `~/.aiplat/run_workspaces/{run_id}/`。"
                            "不要把仓库根当输出目录。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / 运行工作区",
                        how="finalize 在 startable scaffold 任务上把 ## FILE 写入 run_workspaces；失败则本码。",
                    )
                )
            elif code == "broken_python_quotes":
                issues.append(
                    _issue(
                        "broken_python_quotes",
                        "交付的 .py 三引号不成对，文件无法被 Python 解析",
                        severity="error",
                        suggestion=(
                            "闭合所有三引号；不要在文件第一行留下孤立 `\"\"\"` 再写 import。"
                        ),
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how="对每个 ## FILE: *.py 统计三引号个数；奇数或「开引号后直接 import」即失败。",
                    )
                )
            elif code == "fake_integration_claim":
                issues.append(
                    _issue(
                        "fake_integration_claim",
                        "产物声称已对接钉钉/SSO，但任务禁止假实现",
                        severity="error",
                        suggestion="删除假对接声明；鉴权未给出时只标 TODO。",
                        where="check_runtime",
                        where_label="执行轨迹 / code_generation 产物",
                        how="搜索「已对接钉钉」等字样；有 TODO/待确认 的诚实标注除外。",
                    )
                )

    # Tool-style envelope: success false under completed status
    if isinstance(raw_out, dict) and raw_out.get("success") is False:
        err = raw_out.get("error") or raw_out.get("message") or "未知错误"
        issues.append(
            _issue(
                "logical_failure",
                f"流程显示完成，但产物标记失败：{err}",
                severity="error",
                suggestion="修正测试输入（缺参/空 query 等），或在 Tool 描述与 parameters 中写清必填项。",
                where="edit_input_or_schema",
                where_label="执行弹窗 → 修正输入；或编辑 Tool → parameters / description",
                how="对照 error 补齐必填参数后重跑；若 schema 不清，到工具库编辑源码补 parameters。",
            )
        )

    is_prd = _looks_prd_skill(
        f"{asset_id} {hints}",
        f"{asset_name} {hints}",
        raw_out,
    )

    if is_prd:
        # Missing hard constraints from input
        for phrase_label, needles in _must_keep_phrases(in_text):
            if not any(re.search(n, out_text) for n in needles):
                issues.append(
                    _issue(
                        "missing_hard_constraint",
                        f"客户口述硬约束未在产物中保留：{phrase_label}",
                        severity="error",
                        suggestion=f"输出的 constraints / decisions 须原词保留「{phrase_label}」，禁止弱化为笼统「合规检查」。",
                        **sop,
                    )
                )

        # Soft AC — only scan real acceptance_criteria (not FR titles)
        ac_texts = _iter_ac_texts(raw_out)
        soft = _soft_ac_hits("\n".join(ac_texts)) if ac_texts else []
        if soft:
            issues.append(
                _issue(
                    "soft_acceptance_criteria",
                    f"验收标准偏软（命中：{' / '.join(soft[:4])}）",
                    severity="warning",
                    suggestion="AC 须可验证（能量化尽量量化）；禁止「可以查看 / 通过看板查看 / 上传成功」类软表述。",
                    **sop,
                )
            )

        fr_no_ac = _fr_without_ac_hits(raw_out)
        if fr_no_ac:
            issues.append(
                _issue(
                    "fr_without_ac",
                    f"功能需求缺少 acceptance_criteria（命中：{' / '.join(fr_no_ac[:6])}）",
                    severity="error",
                    suggestion="每条 FR 必须有非空 acceptance_criteria；勿把 AC 只写在 name/description。",
                    **sop,
                )
            )

        missing_ac_tok = _missing_required_ac_tokens(in_text, raw_out)
        if missing_ac_tok:
            issues.append(
                _issue(
                    "missing_required_ac_tokens",
                    f"验收标准未包含输入要求的可判定字段（缺：{' / '.join(missing_ac_tok)}）",
                    severity="error",
                    suggestion="把 pending_approval / repair_task_id / ticket_count / avg_close_hours 写入对应 FR 的 acceptance_criteria。",
                    **sop,
                )
            )

        bucket = _constraint_bucket_hits(raw_out)
        if bucket:
            issues.append(
                _issue(
                    "constraint_bucket_mismatch",
                    f"constraints.performance 混入安全/合规项（命中：{' / '.join(bucket[:4])}）",
                    severity="error",
                    suggestion="「不上公网 / 照片不外传」写入 constraints.security；performance 只写时延/吞吐/试点节奏（可标待压测）。",
                    **sop,
                )
            )

        pending_ac = _pending_ac_hits(raw_out)
        if pending_ac:
            issues.append(
                _issue(
                    "pending_as_acceptance_criteria",
                    f"待确认项被写成验收标准（命中：{' / '.join(pending_ac[:3])}）",
                    severity="error",
                    suggestion="「钉钉 API 未开放 / 集成待确认」放入 open_questions 或 decisions=pending；AC 须可判定通过/失败。",
                    **sop,
                )
            )

        n_fr = _fr_count(raw_out)
        if n_fr > 0 and n_fr < 3:
            issues.append(
                _issue(
                    "insufficient_functional_requirements",
                    f"functional_requirements 仅 {n_fr} 条，至少需要 3 条",
                    severity="error",
                    suggestion="拆出上报、审批派修、管理看板等独立 FR，每条含可验证 AC。",
                    **sop,
                )
            )

        constraint_fr = _constraint_as_fr_hits(raw_out)
        if constraint_fr:
            issues.append(
                _issue(
                    "constraint_as_functional_requirement",
                    f"约束/不做项被写成功能需求（命中：{' / '.join(constraint_fr[:4])}）",
                    severity="error",
                    suggestion="「不上公网 / 试点周期 / 明确不做」放入 constraints/decisions；FR 只写上报、审批派修、管理看板等能力。",
                    **sop,
                )
            )

        missing_flow = _missing_core_flow_fr(in_text, raw_out)
        if missing_flow:
            issues.append(
                _issue(
                    "missing_core_flow_fr",
                    f"主流程 FR 缺失（命中：{' / '.join(missing_flow)}）",
                    severity="error",
                    suggestion="按输入补齐拍照上报 / 审批派修 / 管理看板等独立 FR，勿用安全约束条顶替。",
                    **sop,
                )
            )

        scope_hits = _out_of_scope_oq_hits(in_text, raw_out)
        if scope_hits:
            issues.append(
                _issue(
                    "out_of_scope_reopened",
                    f"客户明确不做的能力又被列入待确认（命中：{' / '.join(scope_hits)}）",
                    severity="error",
                    suggestion="明确不做项写入 decisions（不做），不要放进 open_questions 再问「是否需要」。",
                    **sop,
                )
            )

        feat_hits = _out_of_scope_feature_hits(in_text, raw_out)
        if feat_hits:
            issues.append(
                _issue(
                    "out_of_scope_as_feature",
                    f"客户明确不做的能力被写成功能需求（命中：{' / '.join(feat_hits)}）",
                    severity="error",
                    suggestion="明确不做项写入 decisions（不做），禁止出现在 functional_requirements / 正向 AC。",
                    **sop,
                )
            )

        draft_round = _is_draft_round(in_text, raw_out)
        finalize_round = _is_finalize_round(in_text)

        # Empty review input: prefer store restore via resolve_review_io_from_store.
        # Still surface the gap — silent draft inference alone hides broken wiring.
        if not (in_text or "").strip():
            issues.append(
                _issue(
                    "review_input_missing",
                    "复核时缺少执行输入（无法对照客户口述硬约束/域 pack）",
                    severity="warning",
                    suggestion="调用 review-output 时传 execution_id，或确认 status/execution store 已持久化 input。",
                    **sop,
                )
            )

        # Invented magnitude / SLA / encryption not in input.
        # Only scan "confirmed" sections — open_questions may legitimately mention
        # 加密存储 as 待确认 without counting as invented NFR.
        # Without input, every output phrase would look "invented" — skip this rule.
        confirmed_blob = out_text
        if isinstance(raw_out, dict):
            confirmed_parts = {
                k: raw_out.get(k)
                for k in (
                    "constraints",
                    "decisions",
                    "non_functional",
                    "functional_requirements",
                    "user_stories",
                    "title",
                    "status",
                )
                if k in raw_out
            }
            if confirmed_parts:
                confirmed_blob = _text_blob(confirmed_parts)
        invented = []
        if (in_text or "").strip():
            invent_patterns = [
                (r"100\s*条", "100条"),
                (r"至少\s*100\s*个|100\s*个设备", "100个量级"),
                (r"本地服务器", "本地服务器"),
                (r"P95|p95", "P95 SLA"),
                (r"1\s*秒|一秒", "1秒响应"),
                (r"[≤<=]?\s*5\s*秒|5\s*秒内|响应时间.{0,8}5\s*秒", "5秒响应"),
                (r"多语言", "多语言"),
                (r"加密存储|加密传输", "加密存储/传输方案"),
            ]
            for pat, name in invent_patterns:
                if re.search(pat, confirmed_blob) and not re.search(pat, in_text):
                    invented.append(name)
        if invented:
            issues.append(
                _issue(
                    "invented_nfr",
                    f"疑似编造未口述内容：{', '.join(invented)}",
                    severity="error",
                    suggestion="未口述信息写入 open_questions 或标「待确认」，禁止写成正式 NFR/方案。",
                    **sop,
                )
            )

        # open_questions empty while input still has unknowns — draft only.
        # Finalize rounds may keep「API 仍未开放」as decisions.pending_api with OQ=[].
        oq_empty = False
        if isinstance(raw_out, dict):
            oq = raw_out.get("open_questions")
            if isinstance(oq, list) and len(oq) == 0:
                oq_empty = True
            elif oq is None and "open_questions" in raw_out:
                oq_empty = True
        if re.search(r'"open_questions"\s*:\s*\[\s*\]', out_text):
            oq_empty = True
        unknown_signals = bool(
            re.search(r"未定|未开放|希望|预算|编制未|暂时没有|待确认", in_text)
        )
        if not finalize_round and oq_empty and unknown_signals:
            issues.append(
                _issue(
                    "empty_open_questions_on_draft",
                    "输入仍有未决信息，但 open_questions 为空",
                    severity="error",
                    suggestion="草稿轮 open_questions 禁止空数组；至少列入钉钉 API、预算/编制等待确认项。",
                    **sop,
                )
            )

        if not finalize_round and re.search(r"PRD_READY", out_text) and unknown_signals:
            issues.append(
                _issue(
                    "premature_prd_ready",
                    "仍有未决信息却输出了 PRD_READY",
                    severity="error",
                    suggestion="草稿轮禁止 PRD_READY；待 open_questions 可关闭后再定稿。",
                    **sop,
                )
            )

        # Platform PRD gate when structured (draft/finalize + input-domain packs)
        if isinstance(raw_out, dict):
            try:
                from core.harness.execution.prd_quality_gate import assess_prd, looks_like_prd

                if looks_like_prd(raw_out):
                    gate_round = "finalize" if finalize_round else ("draft" if draft_round else "finalize")
                    report = assess_prd(
                        raw_out,
                        assessment_round=gate_round,
                        input_text=in_text,
                    )
                    for it in report.get("issues") or []:
                        if not isinstance(it, dict):
                            continue
                        code = str(it.get("code") or "prd_gate")
                        sev = str(it.get("severity") or "warning")
                        msg = str(it.get("message") or code or "PRD 门禁问题")
                        issues.append(
                            _issue(
                                code,
                                msg,
                                severity=sev,
                                suggestion=(
                                    "草稿轮：未决项保留在 open_questions；勿把未确认方案写入 decisions/constraints。"
                                    if gate_round == "draft"
                                    else "对照平台 PRD 质量门禁补全 constraints / decisions / FR+AC。"
                                ),
                                **sop,
                            )
                        )
            except Exception:
                pass  # noqa: cleanup-best-effort

    is_arch = _looks_architecture(
        f"{asset_id} {hints}",
        f"{asset_name} {hints}",
        raw_out,
        hints=hints,
    )
    if is_arch:
        arch_sop = _architecture_sop_fix(kind, label)
        if _architecture_output_is_lone_api(raw_out):
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    "产物只是单个 API 端点对象，不是完整架构草稿（缺 title/components/data_flow/api_contracts 等）",
                    severity="error",
                    suggestion=(
                        "输出完整架构 JSON：title、context、components、data_flow、"
                        "api_contracts（数组 3～5 端点）、security、rollout_and_risks；"
                        "禁止把失败点里的单端点示意当成整份答案。"
                    ),
                    **arch_sop,
                )
            )
        # Skill echoed its own schema/example instead of a real architecture draft
        # Also: CoT dumped into x-display-profile (run-cadf97 — parse-fail wrap / bad keys)
        _cot_in_profile = (
            "x-display-profile" in out_text
            and re.search(r"步骤\s*[123]|解决方案\s*[123]|###\s*步骤", out_text)
            and not re.search(r'"title"\s*:\s*"[^"]{2,}"', out_text)
        )
        if (
            "x-display-profile" in out_text
            and (
                "架构目标1" in out_text
                or "'properties'" in out_text
                or '"properties"' in out_text
                or _cot_in_profile
            )
        ):
            issues.append(
                _issue(
                    "architecture_template_echo",
                    "产物像是输出 schema / 占位模板 / 推理步骤，不是真实架构草稿",
                    severity="error",
                    suggestion="只输出完整架构 JSON（title/context/components/…）；禁止把正文塞进 x-display-profile，禁止「步骤1/解决方案」链式推理当交付物。",
                    where="check_runtime",
                    where_label="Skill「architecture_design」执行轨迹",
                    how="看 Observation 是否为真实 JSON（含 context/data_flow/security 等正文）；若是 schema 回显或步骤推理，修 Skill prompt/handler 后再跑。",
                )
            )
        cloud_hits = _public_cloud_photo_storage_hits(in_text, out_text)
        if cloud_hits:
            issues.append(
                _issue(
                    "public_cloud_photo_storage",
                    f"输入要求照片不上公网，但架构选用了公有云/公网存储（命中：{' / '.join(cloud_hits[:4])}）",
                    severity="error",
                    suggestion="改为内网/私有化存储（私有桶、VPC 内 MinIO、本地盘等）；禁止阿里云 OSS / 公有云对象存储。",
                    **arch_sop,
                )
            )
        api_invent = _invented_third_party_api_hits(in_text, out_text)
        if api_invent:
            issues.append(
                _issue(
                    "invented_third_party_api",
                    f"输入要求不编造第三方接口，但产物写了具体调用（命中：{' / '.join(api_invent[:4])}）",
                    severity="error",
                    suggestion="钉钉等无文档项写入 open_questions / 假设待确认；数据流用「待对接通知通道」占位，禁止「发送至钉钉××接口」。",
                    **arch_sop,
                )
            )
        section_gaps = _architecture_section_gaps(in_text, raw_out, out_text)
        if section_gaps and "architecture_template_echo" not in {str(i.get("code")) for i in issues}:
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    f"架构草稿缺少输入要求的评审章节（缺：{' / '.join(section_gaps)}）",
                    severity="error",
                    suggestion="补齐上下文与假设、数据流、安全与合规、6 周分期与风险等章节后再评审。",
                    **arch_sop,
                )
            )
        if _architecture_api_thin(in_text, raw_out):
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    "API 契约过薄：缺少可评审的请求/响应要点（禁止 body=「处理结果」等空壳）",
                    severity="error",
                    suggestion="每个端点补充方法/路径/关键字段与响应要点；勿编造未给定的第三方接口细节。",
                    **arch_sop,
                )
            )
        flow_miss = _architecture_data_flow_incomplete(in_text, raw_out)
        if flow_miss:
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    f"数据流未覆盖输入要求的业务段（缺：{' / '.join(flow_miss)}）",
                    severity="error",
                    suggestion="按上报→审批→派修→看板写清端到端数据流与存储落点（含照片落地）。",
                    **arch_sop,
                )
            )
        if _architecture_pending_markers_missing(in_text, raw_out):
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    "输入要求标明待确认，但上下文/假设/open_questions 缺少待确认表述",
                    severity="error",
                    suggestion="在 context/assumptions 中显式写「待确认」项（如钉钉 API 文档）；未知勿编造。",
                    **arch_sop,
                )
            )
        if _architecture_missing_dashboard_api(in_text, raw_out):
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    "输入含看板流程，但 API 契约缺少看板/汇总类端点",
                    severity="warning",
                    suggestion="补 1 个看板/汇总查询端点（方法/路径/响应要点）；勿编造钉钉接口。",
                    **arch_sop,
                )
            )
        if _architecture_security_thin(in_text, raw_out):
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    "安全与合规过薄：未同时覆盖照片落地/脱敏/内网边界（口号式「不外传」不够）",
                    severity="error",
                    suggestion="写清照片落地介质（私有桶/MinIO/本地盘）、脱敏范围、内网/私有化边界；禁止仅「确保照片不外传」。",
                    **arch_sop,
                )
            )
        if _architecture_rollout_thin(in_text, raw_out):
            issues.append(
                _issue(
                    "architecture_sections_thin",
                    "6 周试点分期过薄：缺少按周切片（W1–W6 / 第N周）与对应风险",
                    severity="error",
                    suggestion="按周给出可交付切片（如 W1 上报闭环、W2 审批…）并单列试点风险；勿只写「一个车间」。",
                    **arch_sop,
                )
            )
        if _dingtalk_invented_integration(in_text, raw_out):
            issues.append(
                _issue(
                    "invented_third_party_api",
                    "输入写明钉钉暂无 API 文档，但产物宣称 DingTalk SDK / 与钉钉交互实现审批派修",
                    severity="error",
                    suggestion="钉钉标为待确认假设；通知通道用「待对接」占位，禁止写 SDK 调用或具体审批/派修接口。",
                    **arch_sop,
                )
            )

    return _pack()


_PIPELINE_SKIP_NODE_TYPES = frozenset(
    {"start", "end", "human", "condition", "assigner", "list"}
)


def resolve_pipeline_stage_review_binding(stage: Any) -> Optional[Dict[str, str]]:
    """Map a PipelineStageConfig-like object to review kind/asset (or None to skip)."""
    if stage is None:
        return None
    node_type = str(getattr(stage, "node_type", None) or "").strip().lower() or "agent"
    if node_type in _PIPELINE_SKIP_NODE_TYPES:
        return None
    cfg = getattr(stage, "node_config", None)
    if not isinstance(cfg, dict):
        cfg = {}
    skill_name = str(getattr(stage, "skill_name", None) or "").strip()
    required = list(getattr(stage, "required_skills", None) or [])
    agent_id = str(getattr(stage, "agent_id", None) or "").strip()
    agent_name = str(getattr(stage, "agent_name", None) or "").strip()
    tool_name = str(cfg.get("tool_name") or cfg.get("toolName") or "").strip()

    if node_type == "tool" and tool_name:
        return {"kind": "tool", "asset_id": tool_name, "asset_name": tool_name, "hints": tool_name}
    if skill_name:
        return {
            "kind": "skill",
            "asset_id": skill_name,
            "asset_name": agent_name or skill_name,
            "hints": skill_name,
        }
    if required:
        sid = str(required[0]).strip()
        if sid:
            return {
                "kind": "skill",
                "asset_id": sid,
                "asset_name": agent_name or sid,
                "hints": " ".join(str(x) for x in required[:8]),
            }
    if node_type in ("agent", "llm") and agent_id and agent_id not in ("llm", "agent", "code", "http"):
        return {
            "kind": "agent",
            "asset_id": agent_id,
            "asset_name": agent_name or agent_id,
            "hints": f"{agent_id} {' '.join(str(x) for x in required[:6])}",
        }
    # Generic stage with tangible output — still review empty/soft failures without PRD hints
    if node_type in ("llm", "code", "http", "knowledge", "tool", "template", "aggregator", "algorithm", "plan", "agent"):
        return {
            "kind": "skill",
            "asset_id": str(getattr(stage, "id", None) or node_type),
            "asset_name": agent_name or node_type,
            "hints": f"workflow_stage:{getattr(stage, 'id', '')}",
        }
    return None


def review_pipeline_stage(
    *,
    stage: Any,
    artifact: Any,
    input_payload: Any = None,
    status: str = "completed",
) -> Optional[Dict[str, Any]]:
    """Advisory product-quality review for one pipeline/workflow stage.

    PRD-specific rules stay gated by ``_looks_prd_skill`` on this stage's output —
    not applied to the whole workflow. Returns None when the stage should be skipped.
    """
    binding = resolve_pipeline_stage_review_binding(stage)
    if not binding:
        return None
    # Skip trivial empty non-failed control outputs
    if artifact is None and str(status or "").lower() not in ("failed", "error", "timeout"):
        return None
    try:
        review = review_execution_output(
            kind=binding["kind"],
            asset_id=binding["asset_id"],
            asset_name=binding["asset_name"],
            input_payload=input_payload,
            output=artifact,
            status=status,
            hints=binding.get("hints") or "",
        )
    except Exception as e:
        logger.warning("review_pipeline_stage failed: %s", e, exc_info=True)
        return None
    if not isinstance(review, dict):
        return None
    # Compact for pipeline_events state_json (avoid bloating every emit)
    issues = review.get("issues") or []
    if not issues and str(review.get("verdict") or "") == "pass":
        return {
            "verdict": "pass",
            "headline": review.get("headline"),
            "summary": review.get("summary"),
            "asset": review.get("asset"),
            "stage_id": str(getattr(stage, "id", "") or ""),
        }
    return {
        "verdict": review.get("verdict"),
        "headline": review.get("headline"),
        "ok": review.get("ok"),
        "runtime_ok": review.get("runtime_ok"),
        "issues": issues[:12],
        "summary": review.get("summary"),
        "fix_guide": review.get("fix_guide"),
        "asset": review.get("asset"),
        "fixable_issue_codes": (review.get("fixable_issue_codes") or [])[:8],
        "primary_action": review.get("primary_action"),
        "sop_iron": review.get("sop_iron"),
        "rerun_constraint_overlay": review.get("rerun_constraint_overlay") or "",
        "stage_id": str(getattr(stage, "id", "") or ""),
    }


def _input_missing(payload: Any) -> bool:
    if payload is None:
        return True
    if isinstance(payload, str) and not payload.strip():
        return True
    if isinstance(payload, (dict, list)) and len(payload) == 0:
        return True
    return False


def _output_missing(payload: Any) -> bool:
    """True when review body has no usable product text (incl. {"text":""})."""
    if _input_missing(payload):
        return True
    if isinstance(payload, dict):
        only = set(payload.keys())
        if only <= {"text", "output", "answer", "content", "response", "markdown"}:
            if not (_text_blob(payload) or "").strip():
                return True
    return False


def pick_embedded_quality_review(
    *,
    embedded: Optional[Dict[str, Any]],
    body_output: Any,
    resolved_output: Any,
    prefer_embedded: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return stored quality_review when safe; None → caller should re-review.

    Race fix: frontend often POSTs ``output: ""`` / ``{"text":""}`` after graph-done
    before the agent row upserts. Prefer metadata.quality_review (or re-review with
    store-restored output) instead of a false empty_output.
    """
    if not isinstance(embedded, dict):
        return None
    issues = embedded.get("issues") if isinstance(embedded.get("issues"), list) else []
    codes = {str(i.get("code") or "") for i in issues if isinstance(i, dict)}
    resolved_ok = not _output_missing(resolved_output)
    # Stale empty_output while store now has payload → force re-review
    if "empty_output" in codes and resolved_ok:
        return None
    body_empty = _output_missing(body_output)
    # Store has product + caller is not in the empty-body race → do not lock a
    # stored A/pass (gates may have tightened; run-b44072c24c3a). Fail/warn
    # embedded still reused so empty POST body does not flash empty_output.
    if (
        resolved_ok
        and not prefer_embedded
        and str(embedded.get("verdict") or "").lower() == "pass"
    ):
        return None
    # Caller already has real product body → never lock onto a stored pass.
    # prefer_embedded exists for empty-body races; using it with a full body
    # greenwashes after gates tighten (run-1b2df4ffd82c: UI kept A while
    # missing_auth_todo + dangling_local_import).
    if (
        not body_empty
        and resolved_ok
        and str(embedded.get("verdict") or "").lower() == "pass"
    ):
        return None
    if prefer_embedded or body_empty:
        if embedded.get("verdict") is not None or issues:
            return embedded
    return None


def _workspace_delivery_on_disk(run_id: str, raw_out: Any = None) -> bool:
    """True when startable scaffold files exist under run_workspaces/{run_id}."""
    if isinstance(raw_out, dict):
        root = str(raw_out.get("persisted_root") or raw_out.get("persist_root") or "").strip()
        files = raw_out.get("persisted_files")
        if root and os.path.isdir(root):
            return True
        if isinstance(files, list) and files and root:
            return True
    rid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_id or "").strip())[:80]
    if not rid:
        return False
    home = os.path.realpath(os.path.expanduser(os.environ.get("AIPLAT_HOME") or "~/.aiplat"))
    path = os.path.join(home, "run_workspaces", rid)
    try:
        return os.path.isdir(path) and any(os.scandir(path))
    except OSError:
        return False


def _attach_persist_fields(
    body_out: Any,
    store_out: Any,
    meta: Any,
    *,
    execution_id: str = "",
) -> Any:
    """Keep ## FILE text from the POST body, but never drop store persist paths.

    Frontend unwrap often sends a bare markdown string; without persisted_root
    a second review-output call false-fails ``scaffold_not_on_disk``.
    """
    root = ""
    files: Any = None
    if isinstance(store_out, dict):
        root = str(store_out.get("persisted_root") or store_out.get("persist_root") or "").strip()
        files = store_out.get("persisted_files")
    if isinstance(meta, dict):
        if not root:
            root = str(meta.get("persisted_root") or meta.get("persist_root") or "").strip()
        if not files:
            files = meta.get("persisted_files")
        if not root and str(meta.get("disk_persist") or "") == "ok" and execution_id:
            home = os.path.realpath(
                os.path.expanduser(os.environ.get("AIPLAT_HOME") or "~/.aiplat")
            )
            cand = os.path.join(home, "run_workspaces", str(execution_id).strip())
            if os.path.isdir(cand):
                root = cand
    if not root:
        return body_out
    if isinstance(body_out, dict):
        if str(body_out.get("persisted_root") or "").strip():
            return body_out
        merged = dict(body_out)
        merged["persisted_root"] = root
        if files:
            merged["persisted_files"] = files
        return merged
    if isinstance(body_out, str) and body_out.strip():
        packed: Dict[str, Any] = {"text": body_out, "persisted_root": root}
        if files:
            packed["persisted_files"] = files
        return packed
    if body_out is None or _output_missing(body_out):
        if isinstance(store_out, dict):
            return store_out
        packed = {"text": str(store_out or ""), "persisted_root": root}
        if files:
            packed["persisted_files"] = files
        return packed
    return body_out


async def resolve_review_io_from_store(
    *,
    execution_id: Optional[str] = None,
    kind: str = "skill",
    body_input: Any = None,
    body_output: Any = None,
    body_status: Optional[str] = None,
) -> Tuple[Any, Any, str, Optional[Dict[str, Any]]]:
    """Prefer body fields; fill gaps from skill/agent execution row.

    Returns ``(input, output, status, embedded_quality_review)``.
    Embedded review comes from ``metadata.quality_review`` when present (stream path).
    """
    inp = body_input
    out = body_output
    st = str(body_status or "completed")
    embedded: Optional[Dict[str, Any]] = None
    eid = str(execution_id or "").strip()
    if not eid:
        return inp, out, st, None
    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
        record = None
        k = str(kind or "skill").lower()
        if k == "agent" and hasattr(store, "get_agent_execution"):
            record = await store.get_agent_execution(eid)
        elif hasattr(store, "get_skill_execution"):
            record = await store.get_skill_execution(eid)
            if record is None and hasattr(store, "get_agent_execution"):
                record = await store.get_agent_execution(eid)
        if not isinstance(record, dict):
            return inp, out, st, None
        if _input_missing(inp) and not _input_missing(record.get("input")):
            inp = record.get("input")
        # Treat "" / {"text":""} as missing — frontend race often sends these
        if _output_missing(out) and not _output_missing(record.get("output")):
            out = record.get("output")
        if not body_status:
            rst = str(record.get("status") or "").strip()
            if rst:
                st = rst
        meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        out = _attach_persist_fields(out, record.get("output"), meta, execution_id=eid)
        qr = meta.get("quality_review")
        if isinstance(qr, dict):
            embedded = qr
    except Exception as e:
        logger.debug("resolve_review_io_from_store failed eid=%s: %s", eid, e, exc_info=True)
    return inp, out, st, embedded
