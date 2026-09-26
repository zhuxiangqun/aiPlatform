"""Least-privilege permission / external-intent helpers for agent create."""

from __future__ import annotations

from core.apps.common.boundary_hints import mentions_external_system, wants_outbound_network


def test_no_network_when_user_says_bu_lianwang():
    assert not wants_outbound_network(
        tools=["file_operations", "code"],
        text="严格只用用户给的信息、不联网、不编造；生成 pptx 并保存下载",
    )


def test_network_when_explicit_need():
    assert wants_outbound_network(tools=[], text="需要联网搜索最新政策；允许联网后抓取网页摘要")


def test_network_when_net_tool_bound():
    assert wants_outbound_network(tools=["web_search"], text="不联网也要绑搜索工具时仍放行")


def test_pptx_write_hint_still_local():
    # write path is separate; this only asserts network stays off
    assert not wants_outbound_network(
        tools=["file_operations"],
        text="输出 pptx 文件，既直接下载给用户，同时保存到指定目录",
    )


def test_external_content_negation_not_mcp():
    desc = "严格只用用户给的信息、不联网、不编造、不补充外部内容；模版可上传或内置库挑选"
    assert not mentions_external_system(desc)


def test_feishu_is_external():
    assert mentions_external_system("对接飞书文档同步到知识库")
