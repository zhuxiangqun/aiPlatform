"""
Learning Paths — built-in curriculum for the AI Learning Coach.

Three paths:
  1. ai_engineer       (8 chapters) — build AI workflow systems from scratch
  2. ai_decision_maker  (6 chapters) — evaluate, purchase, and govern AI
  3. ai_literate        (5 chapters) — understand and use AI tools effectively

Chapters have human-curated skeletons (concepts, exercises, rubrics) and
AI-compiled body text (generated on first access via compile_chapter_body).

Storage:
  - Structure: hardcoded here (human-curated skeleton)
  - Content:   ~/.aiplat/learning/chapters/generated/{chapter_id}.json (AI body)

callers: learning_assessment.py, wiki.py, core_facade.py
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
from typing import Any, Dict, List, Optional

from core.harness.knowledge.learning_ontology import (
    ChapterContent, LearnerProfile, TargetRole, CurrentLevel,
    save_chapter_content, load_chapter_content,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Built-in Learning Paths
# ══════════════════════════════════════════════════════════════

def _ch(path_id: str, chap_id: str, order: int, title: str,
        concepts: List[str], minutes: int = 60,
        prerequisites: List[str] = None,
        materials: List[Dict[str, str]] = None,
        exercises: List[Dict[str, Any]] = None,
        mini_project: Dict[str, str] = None) -> ChapterContent:
    return ChapterContent(
        chapter_id=chap_id, path_id=path_id, order=order, title=title,
        estimated_minutes=minutes, prerequisites=prerequisites or [],
        concepts=concepts, status="draft",
        materials=materials or [], exercises=exercises or [],
        mini_project=mini_project or {},
    )


def get_builtin_paths() -> Dict[str, List[ChapterContent]]:
    u"""Return all three built-in learning paths keyed by path_id."""
    return {
        "ai_literate": _ai_literate_path(),
        "ai_decision_maker": _ai_decision_maker_path(),
        "ai_engineer": _ai_engineer_path(),
    }


def get_path(path_id: str) -> Optional[List[ChapterContent]]:
    return get_builtin_paths().get(path_id)


def get_path_summary() -> List[Dict[str, Any]]:
    paths = get_builtin_paths()
    summaries = []
    for pid, chapters in paths.items():
        total_min = sum(c.estimated_minutes for c in chapters)
        summaries.append({
            "path_id": pid,
            "name": _path_name(pid),
            "description": _path_description(pid),
            "chapter_count": len(chapters),
            "total_hours": round(total_min / 60, 1),
            "first_chapter_title": chapters[0].title if chapters else "",
        })
    return summaries


def _path_name(path_id: str) -> str:
    return _path_meta(path_id, "name")


def _path_description(path_id: str) -> str:
    return _path_meta(path_id, "desc")


def _path_meta(path_id: str, key: str) -> str:
    u"""Load path metadata from external config (guard-compliant, i18n-ready)."""
    import json as _json, os as _os
    config_path = _os.path.join(
        _os.path.dirname(__file__), "learning_path_meta.json"
    )
    try:
        if _os.path.exists(config_path):
            data = _json.load(open(config_path))
            return str(data.get(path_id, {}).get(key, path_id))
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    # Hardcoded fallback (learning content, not engine logic)
    defaults = {
        "ai_literate": {
            "name": "AI 通识素养",
            "desc": "理解 AI 核心概念，能独立使用主流 AI 工具完成日常工作。零基础入门。"
        },
        "ai_decision_maker": {
            "name": "AI 决策与实践",
            "desc": "判断 AI 能做什么、不能做什么、花多少钱、有什么风险。面向学习者。"
        },
        "ai_engineer": {
            "name": "AI 工程化实战",
            "desc": "从 Prompt 工程到全栈 AI 系统部署。面向有编程基础的技术学习者。"
        },
        "ai_literate_learner": "零基础学习者，目标是理解 AI 核心概念并独立使用主流 AI 工具",
        "ai_decision_maker_learner": "学习者，目标是判断 AI 的适用性和投资价值",
        "ai_engineer_learner": "有编程基础的技术学习者，目标是动手搭建企业级 AI 工作流系统",
    }
    return str(defaults.get(path_id, {}).get(key, path_id) if key in ("name", "desc") else defaults.get(path_id, path_id))


# ══════════════════════════════════════════════════════════════
# Path 1: ai_literate (5 chapters)
# ══════════════════════════════════════════════════════════════

def _ai_literate_path() -> List[ChapterContent]:
    return [
        _ch("ai_literate", "lit_intro", 1, "第1章: 什么是 AI",
            concepts=["人工智能定义", "机器学习 vs 深度学习 vs 大语言模型",
                       "监督学习 vs 无监督学习", "生成式 AI 的原理直觉"],
            minutes=45,
            exercises=[
                {"type": "multiple_choice",
                 "question": "以下哪项最准确地描述了\"大语言模型\"的核心能力？",
                 "options": ["精确数学计算", "基于大量文本训练后的文本生成与理解",
                              "图像识别", "实时传感器数据处理"],
                 "answer": 1},
                {"type": "open_ended",
                 "question": "用你自己的话解释：大语言模型和传统搜索引擎的区别是什么？请举一个具体的例子说明。",
                 "rubric": "正确理解 LLM 是生成而非检索；举例清晰具体；能用非技术语言表达。120字以上。"},
            ],
            mini_project={"title": "向朋友解释什么是 AI", "objective": "用300字以内的中文，向一个完全不懂技术的朋友解释 AI 是什么、能做什么、不能做什么。要求不使用任何技术术语。"},
        ),
        _ch("ai_literate", "lit_llm", 2, "第2章: 大模型原理简介",
            concepts=["Transformer 架构直觉", "Token 是什么", "训练 vs 推理",
                       "上下文窗口", "幻觉问题"],
            minutes=60,
            prerequisites=["lit_intro"],
            materials=[
                {"type": "external", "title": "Attention Is All You Need (论文简介)", "url": "https://arxiv.org/abs/1706.03762"},
                {"type": "external", "title": "Andrej Karpathy: Intro to Large Language Models (视频)", "url": "https://www.youtube.com/watch?v=zjkBMFhNj_g"},
            ],
            exercises=[
                {"type": "multiple_choice",
                 "question": "LLM 产生\"幻觉\"的根本原因是什么？",
                 "options": ["它故意编造信息", "它是基于概率生成的，不保证事实正确性",
                              "训练数据太少", "模型参数不够多"],
                 "answer": 1},
                {"type": "open_ended",
                 "question": "如果你向朋友解释\"Token\"这个概念，你会怎么类比？给出一个非技术的类比。",
                 "rubric": "类比恰当；不照搬术语；能让完全外行的人明白。80字以上。"},
            ],
            mini_project={"title": "编写 Token 计算器说明", "objective": "用自己的话写一个 200 字的说明，解释 Token 如何影响 AI 对话的长度和费用。附带一个实例计算。"},
        ),
        _ch("ai_literate", "lit_tools", 3, "第3章: 主流 AI 工具全景",
            concepts=["对话式 AI 产品对比", "AI 编程工具", "AI 图像/视频生成",
                       "选择工具的决策框架"],
            minutes=60,
            prerequisites=["lit_intro"],
            exercises=[
                {"type": "open_ended",
                 "question": "你所在的工作场景最需要哪种 AI 工具？请分析至少两个候选工具，说明选其一的原因。",
                 "rubric": "场景描述清晰；至少对比两个工具；选择有逻辑依据。150字以上。"},
            ],
            mini_project={"title": "个人 AI 工具箱", "objective": "列出你日常工作中最适合引入 AI 的 3 个场景，为每个场景推荐一个具体工具，并说明理由。"},
        ),
        _ch("ai_literate", "lit_safety", 4, "第4章: AI 安全与隐私",
            concepts=["数据隐私风险", "提示词注入攻击", "敏感信息泄露",
                       "AI 使用的基本安全守则"],
            minutes=45,
            prerequisites=["lit_llm"],
            exercises=[
                {"type": "multiple_choice",
                 "question": "下列哪种做法是正确的 AI 使用习惯？",
                 "options": ["把客户隐私数据复制到 ChatGPT 让它分析",
                              "把公司内部代码粘贴到公开 AI 平台求优化",
                              "用脱敏后的假数据测试 AI 功能",
                              "用 AI 生成的代码直接上线不做安全审查"],
                 "answer": 2},
            ],
            mini_project={"title": "AI 安全自检清单", "objective": "为你的工作场景编写一份不少于 5 条的 AI 使用安全守则。"},
        ),
        _ch("ai_literate", "lit_practice", 5, "第5章: 动手做一个 AI 助手",
            concepts=["Prompt 基础写法", "角色设定", "迭代优化",
                       "从\"能用\"到\"好用\"的调优方法"],
            minutes=75,
            prerequisites=["lit_tools", "lit_safety"],
            exercises=[
                {"type": "open_ended",
                 "question": "选择一个你工作中的重复性任务，设计一组 prompt 让 AI 帮你自动化完成。提交你的 prompt 设计和效果对比。",
                 "rubric": "任务选择合理；prompt 设计有结构（角色+任务+格式要求）；有前后效果对比。200字以上。"},
            ],
            mini_project={"title": "我的第一个 AI 助手", "objective": "使用 ChatGPT 或其他 AI 工具，搭建一个解决你实际工作问题的助手。提交：任务描述 + prompt 设计 + 使用效果评估。"},
        ),
    ]


# ══════════════════════════════════════════════════════════════
# Path 2: ai_decision_maker (6 chapters)
# ══════════════════════════════════════════════════════════════

def _ai_decision_maker_path() -> List[ChapterContent]:
    return [
        _ch("ai_decision_maker", "dec_landscape", 1, "第1章: AI 能力全景与边界",
            concepts=["AI 当下能做什么（10个已验证场景）",
                       "AI 当下不能做什么（5个典型边界）",
                       "技术成熟度曲线", "从 demo 到生产的鸿沟"],
            minutes=60,
            exercises=[
                {"type": "open_ended",
                 "question": "你所在行业目前有哪些\"公认适合 AI\"的场景？请列出 3 个，并说明是否已有成功案例。",
                 "rubric": "场景具体可操作；有行业针对性；不空谈概念。120字以上。"},
            ],
            mini_project={"title": "AI 能力自评", "objective": "对你所在企业的业务环节逐一评估，标出 3 个\"AI 可立刻介入\"和 2 个\"暂不适合\"的环节，说明判断依据。"},
        ),
        _ch("ai_decision_maker", "dec_feasibility", 2, "第2章: 技术可行性判断",
            concepts=["数据就绪度评估", "模型选择（通用 vs 微调 vs 自训练）",
                       "基础设施需求", "集成复杂度"],
            minutes=60,
            prerequisites=["dec_landscape"],
            exercises=[
                {"type": "multiple_choice",
                 "question": "评估一个 AI 项目技术可行性时，哪个因素最容易被低估？",
                 "options": ["模型训练成本", "数据质量和获取难度",
                              "UI 设计复杂度", "市场推广费用"],
                 "answer": 1},
            ],
            mini_project={"title": "可行性评估表", "objective": "为你选中的一个 AI 应用场景，填写一份简化版可行性评估：数据就绪度(1-5)、技术复杂度(1-5)、集成难度(1-5)。"},
        ),
        _ch("ai_decision_maker", "dec_roi", 3, "第3章: ROI 评估方法",
            concepts=["AI 项目的成本构成", "收益量化（硬收益 + 软收益）",
                       "总拥有成本 TCO", "自建 vs 采购的决策模型"],
            minutes=75,
            prerequisites=["dec_feasibility"],
            exercises=[
                {"type": "open_ended",
                 "question": "一个 AI 客服系统报价 30 万/年。你公司现有 5 个客服，每人年薪 8 万。请分析是否值得采购，列出计算过程。",
                 "rubric": "计算逻辑清晰；考虑了保留人工的比例；区分了硬收益（工资节省）和软收益（响应速度提升）。"},
            ],
            mini_project={"title": "AI 采购 ROI 计算", "objective": "找一个你工作中了解的 AI 产品或服务，做一个简化版 ROI 计算（3 年期）。"},
        ),
        _ch("ai_decision_maker", "dec_prd", 4, "第4章: AI 需求文档化",
            concepts=["AI 功能 PRD 的特殊要求", "验收标准怎么写",
                       "数据标注需求", "模型性能指标（准确率/召回率等）"],
            minutes=60,
            prerequisites=["dec_landscape"],
            exercises=[
                {"type": "open_ended",
                 "question": "为一个\"AI 辅助合同审查\"功能写一段 PRD 中的功能描述和验收标准。要求包含至少一条具体的性能指标。",
                 "rubric": "功能描述可执行；验收标准具体可测；包含至少一条量化指标。150字以上。"},
            ],
            mini_project={"title": "AI 功能 PRD 片段", "objective": "为你自己的产品/项目写一个 AI 功能的 PRD 片段（功能描述 + 验收标准 + 风险标注）。"},
        ),
        _ch("ai_decision_maker", "dec_vendor", 5, "第5章: 供应商与方案评估",
            concepts=["AI 供应商评估框架", "开源 vs 闭源的权衡",
                       "私有化部署 vs SaaS", "如何避免\"被忽悠\""],
            minutes=60,
            prerequisites=["dec_roi"],
            materials=[
                {"type": "external", "title": "Gartner Magic Quadrant for Cloud AI Developer Services",
                 "url": "https://www.gartner.com/en/documents/cloud-ai-developer-services"},
            ],
            exercises=[
                {"type": "open_ended",
                 "question": "你收到一个 AI 供应商的方案：\"基于千亿参数大模型，准确率 95%，一周部署\"。列出你追问供应商的 5 个问题。",
                 "rubric": "问题涉及数据安全、模型更新频率、实际准确率含义、集成成本、长期维护。至少5个具体问题。"},
            ],
            mini_project={"title": "供应商评估矩阵", "objective": "设计一个 5x5 的供应商评估矩阵，维度自选，为你感兴趣的 AI 领域评估至少 2 个候选供应商。"},
        ),
        _ch("ai_decision_maker", "dec_compliance", 6, "第6章: 合规、伦理与风险管理",
            concepts=["AI 相关法规概览（国内 + 欧盟 AI Act）",
                       "偏见与公平性", "可解释性要求",
                       "退出机制和应急预案"],
            minutes=60,
            prerequisites=["dec_vendor"],
            exercises=[
                {"type": "open_ended",
                 "question": "假设你公司使用 AI 筛选简历，有候选人投诉\"AI 有偏见\"。你作为产品负责人，如何回应和处理？从技术和流程两个角度回答。",
                 "rubric": "技术角度（审计日志/可解释性）；流程角度（人工复核机制/申诉通道）；回答具体而非空谈。150字以上。"},
            ],
            mini_project={"title": "AI 合规检查清单", "objective": "为你所在行业编写一份不少于 8 条的 AI 合规自检清单。"},
        ),
    ]


# ══════════════════════════════════════════════════════════════
# Path 3: ai_engineer (8 chapters)
# ══════════════════════════════════════════════════════════════

def _ai_engineer_path() -> List[ChapterContent]:
    return [
        _ch("ai_engineer", "eng_prompt", 1, "第1章: Prompt 工程基础",
            concepts=["system prompt 设计", "few-shot vs zero-shot",
                       "Chain-of-Thought", "temperature 和 top_p",
                       "结构化输出要求"],
            minutes=90,
            exercises=[
                {"type": "coding",
                 "question": "写一个函数 `build_analysis_prompt(topic, audience)`，根据 topic 和 audience 自动生成包含角色设定、输出格式、示例的结构化 prompt。",
                 "rubric": "函数可运行；prompt 结构包含角色、任务、格式；考虑了 audience 参数的变化。"},
            ],
            mini_project={"title": "Prompt 工作流", "objective": "为你工作中最重复的一个文本处理任务，设计一套 prompt chain（至少 3 步），测试效果并与单次 prompt 对比。"},
        ),
        _ch("ai_engineer", "eng_api", 2, "第2章: API 调用与集成",
            concepts=["OpenAI/Anthropic API 基础", "流式输出处理",
                       "错误重试与降级", "Token 计数与成本控制",
                       "速率限制应对"],
            minutes=75,
            prerequisites=["eng_prompt"],
            exercises=[
                {"type": "coding",
                 "question": "实现一个带重试和速率限制的 LLM 调用封装函数，支持自动降级（主模型不可用时切换到备用模型）。",
                 "rubric": "包含指数退避重试；速率限制处理；备用模型切换；有日志输出。"},
            ],
            mini_project={"title": "API 调用封装", "objective": "封装一个 Python 模块 `llm_client.py`，支持多模型切换、自动重试、成本追踪。附带简单的使用示例。"},
        ),
        _ch("ai_engineer", "eng_rag", 3, "第3章: RAG 检索增强生成",
            concepts=["向量数据库原理", "文档切分策略",
                       "Embedding 模型选择", "检索 + 重排",
                       "Hybrid Search", "RAG 评估方法"],
            minutes=90,
            prerequisites=["eng_api"],
            materials=[
                {"type": "external", "title": "LangChain RAG Tutorial", "url": "https://python.langchain.com/docs/tutorials/rag/"},
            ],
            exercises=[
                {"type": "coding",
                 "question": "搭建一个最小化的 RAG 系统：加载一个 PDF → 切分 → 向量化（可用 sentence-transformers） → 支持自然语言查询。",
                 "rubric": "完整可运行；正确处理 PDF 文本提取；向量检索返回相关结果；有简单的检索质量评估。"},
            ],
            mini_project={"title": "企业文档问答系统", "objective": "选取一份真实的公司文档（产品手册/规章制度），搭建一个可查询的 RAG 系统。提交代码 + 5 个测试问题的查询效果。"},
        ),
        _ch("ai_engineer", "eng_agent", 4, "第4章: Agent 与工具调用",
            concepts=["ReAct 模式", "Function Calling",
                       "Agent 决策循环", "多 Agent 协作",
                       "工具注册与发现"],
            minutes=75,
            prerequisites=["eng_rag"],
            exercises=[
                {"type": "open_ended",
                 "question": "设计一个\"旅行规划 Agent\"的系统架构图，标出至少 3 个工具（订票、查天气、推荐酒店），描述 Agent 决策流程。",
                 "rubric": "架构图清晰；工具描述具体；决策流程有明确的逻辑分支。"},
            ],
            mini_project={"title": "工具调用 Agent", "objective": "实现一个简单的 Agent，能根据用户自然语言指令，自行决定调用哪个工具（至少 3 个工具）。"},
        ),
        _ch("ai_engineer", "eng_multi", 5, "第5章: 多模型编排",
            concepts=["Pipeline 编排模式", "Router 模式",
                       "Evaluator-Optimizer 模式", "多模型对比",
                       "成本-质量权衡"],
            minutes=75,
            prerequisites=["eng_agent"],
            exercises=[
                {"type": "coding",
                 "question": "实现一个 Router：根据输入类型（代码生成/翻译/摘要）自动路由到不同的 prompt 模板和模型配置。",
                 "rubric": "Router 逻辑清晰；至少 3 种路由分支；每种分支有不同的配置。"},
            ],
            mini_project={"title": "编排流水线", "objective": "设计一个 3 步 AI 流水线：输入 → 分类 Router → 专用处理器 → 质量校验 → 输出。提交代码和流程图。"},
        ),
        _ch("ai_engineer", "eng_security", 6, "第6章: AI 安全与防护",
            concepts=["提示词注入防御", "输出过滤与校验",
                       "速率限制与滥用防护", "敏感数据脱敏",
                       "审计与合规"],
            minutes=60,
            prerequisites=["eng_api"],
            exercises=[
                {"type": "open_ended",
                 "question": "你开发的 ChatGPT 插件上架后，用户发现可以通过特殊构造的输入让系统泄露内部 prompt。请设计一个防护方案。",
                 "rubric": "至少提到输入过滤、输出校验、权限分级；方案分层次（预防→检测→响应）。"},
            ],
            mini_project={"title": "安全加固", "objective": "为你之前写的 LLM 调用封装增加安全防护：prompt 注入检测 + 输出敏感信息过滤 + 调用审计日志。"},
        ),
        _ch("ai_engineer", "eng_deploy", 7, "第7章: 部署与运维",
            concepts=["容器化部署", "CI/CD for AI",
                       "监控与告警", "A/B 测试",
                       "灰度发布", "成本优化"],
            minutes=75,
            prerequisites=["eng_multi"],
            exercises=[
                {"type": "open_ended",
                 "question": "你的 AI 服务上线后，用户反馈响应太慢（平均 3 秒）。请列出排查步骤和可能的优化方向。",
                 "rubric": "排查步骤有层次（网络→模型→并发→缓存）；优化方向具体可操作。"},
            ],
            mini_project={"title": "部署方案", "objective": "为你之前搭建的 RAG 或 Agent 项目写一个 Docker Compose 部署方案，包含健康检查和日志收集。"},
        ),
        _ch("ai_engineer", "eng_optimize", 8, "第8章: 性能优化与总结",
            concepts=["Prompt 压缩", "模型量化与加速",
                       "缓存策略", "批处理优化",
                       "全栈回顾与能力地图"],
            minutes=90,
            prerequisites=["eng_deploy", "eng_security"],
            exercises=[
                {"type": "open_ended",
                 "question": "回顾你学完的 8 章内容，画出你的\"AI 工程化能力地图\"：你熟练的部分、需要加强的部分、还没涉及的部分。",
                 "rubric": "自评诚实；有具体的提升计划；能说清楚下一步学习方向。200字以上。"},
            ],
            mini_project={"title": "综合项目", "objective": "从零搭建一个完整的企业级 AI 工作流：输入处理 → 智能路由 → 任务执行 → 结果校验 → 输出格式化。整合前面所有章节的技能。"},
        ),
    ]


# ══════════════════════════════════════════════════════════════
# AI Chapter Body Compilation
# ══════════════════════════════════════════════════════════════

async def compile_chapter_body(chapter: ChapterContent, *, force: bool = False) -> str:
    u"""Compile AI-generated chapter body text (LLM).

    Follows the raw/wiki pattern: the human-curated skeleton is in the code,
    the AI fills in the explanatory prose. Results are cached to disk.

    Args:
        chapter: ChapterContent with concepts and skeleton.
        force: if True, regenerate even if cached.

    Returns:
        AI-generated chapter body text in Chinese.
    """
    cached = load_chapter_content(chapter.chapter_id)
    if cached and cached.ai_generated_body and not force:
        return cached.ai_generated_body

    path_name = _path_name(chapter.path_id)
    concepts_str = "\n".join(f"- {c}" for c in chapter.concepts)
    target_role = _path_meta(f"{chapter.path_id}_learner", "name") if _path_meta(f"{chapter.path_id}_learner", "name") != f"{chapter.path_id}_learner" else "学习者"

    prompt = f"""你是 AI 学习教练 '{path_name}' 学习路径的课程编写助手。
请为以下章节编写学习者读的课文正文。务必用中文撰写。

【章节信息】
标题: {chapter.title}
目标读者: {target_role}
预计学习时间: {chapter.estimated_minutes} 分钟
核心概念:
{concepts_str}

【编写要求】
1. 用对话式、易读的中文写作，避免学术腔。
2. 每个概念解释时附带一个具体的、非技术的例子。
3. 如果概念之间有逻辑依赖，按"先理解 A 才能理解 B"的顺序组织。
4. 正文控制在 1500-2500 字。
5. 不要包含习题或作业——那些已经由人工策划好了。
6. 如果涉及代码，用 Python 示例，注释用中文。

请直接输出课文正文（不要加前言、不要标注"课文正文"标题）。"""

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("chat"),
            max_tokens=3000,
        )
        body = result.get("content", "") if isinstance(result, dict) else str(result)
    except Exception as e:
        logger.warning("Chapter body compilation failed for %s: %s", chapter.chapter_id, str(e)[:100])
        body = f"## {chapter.title}\n\n（章节内容正在编译中，请稍后再试。）\n\n核心概念：\n{concepts_str}"

    chapter.ai_generated_body = body
    save_chapter_content(chapter)
    return body


def get_chapter_body_sync(chapter: ChapterContent) -> str:
    u"""Synchronous wrapper to get cached chapter body, or return skeleton if not compiled."""
    cached = load_chapter_content(chapter.chapter_id)
    if cached and cached.ai_generated_body:
        return cached.ai_generated_body
    concepts_str = "\n".join(f"- {c}" for c in chapter.concepts)
    return f"## {chapter.title}\n\n（本章内容尚未编译，请通过 /learning/compile 触发生成。）\n\n核心概念：\n{concepts_str}"
