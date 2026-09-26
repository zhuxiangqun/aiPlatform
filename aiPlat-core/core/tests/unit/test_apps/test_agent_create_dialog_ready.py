"""Agent create-dialog readiness heuristics (no LLM)."""

from __future__ import annotations

from core.apps.common.create_dialog_utils import (
    agent_create_corpus_ready,
    guess_agent_display_name,
    join_user_corpus,
)


PPT_CORPUS = """
我希望创建一个PPT制作数字员工，该员工可以根据用户描述的内容要点（不一定是标题/章节/每页要点），自动做成相应模版的ppt文档（如有现成模版，就按照选择模版制作）

1、模版可以是用户上传 pptx 模版文件，也可以是从系统内置模版库中挑选
2、内容要点是文字描述加上附带文档/图片等素材
3、严格只用用户给的信息、不编造

1. 没有可用模版时停下来问用户
2、生成的 pptx 直接下载给用户同时保存到指定目录/项目空间
3、要点与素材的对应关系自动判断
""".strip()


def test_ppt_single_shot_with_answers_is_ready():
    assert agent_create_corpus_ready(PPT_CORPUS)
    assert "PPT" in guess_agent_display_name(PPT_CORPUS)


def test_thin_goal_not_ready():
    assert not agent_create_corpus_ready("做一个帮我写摘要的助手")


def test_join_user_corpus_merges_history():
    corpus = join_user_corpus(
        "停下来问用户；保存并下载；自动判断对应关系",
        [
            {"role": "assistant", "content": "还差细节"},
            {"role": "user", "content": "做一个PPT数字员工，用要点和素材生成pptx，不编造"},
        ],
    )
    assert "PPT" in corpus or "pptx" in corpus.lower()
    assert agent_create_corpus_ready(corpus)
