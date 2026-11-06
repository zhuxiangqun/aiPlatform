/**
 * Workspace Tools glossary — Layer A for 小朱 (XIAOZHU.md §1.2–1.4).
 */
export type ToolsGlossEntry = {
  term: string;
  aliases?: string[];
  meaning: string;
};

export const TOOLS_GLOSSARY: ToolsGlossEntry[] = [
  {
    term: '应用库 Tool',
    aliases: ['Tool 库', '/workspace/tools'],
    meaning: '管理 ~/.aiplat/tools 原子操作/脚本；真副作用出口，不是 Skill SOP 正文',
  },
  {
    term: 'Tool',
    aliases: ['工具'],
    meaning: '可被 Skill/Agent 调用的副作用单元；与 MCP 类似但是本地 Tool 定义',
  },
  {
    term: 'Skill',
    aliases: ['/workspace/skills'],
    meaning: '可复用 SOP；可声明绑定 Tool。本页改 Tool 不等于改 Skill 生命周期',
  },
  {
    term: 'MCP',
    aliases: ['/workspace/mcp'],
    meaning: '外部工具服务协议；与本地 Tool 并列，勿混为一谈',
  },
  {
    term: 'AI 审核',
    aliases: ['AssetAudit', 'audit'],
    meaning: '对 Tool 定义做审核（含未实现副作用等）；一键修不一定能消全部 issue',
  },
  {
    term: 'unrealized_side_effect',
    aliases: ['未实现副作用'],
    meaning: '宣称会副作用（如上传）但未绑真实 Tool/MCP；需改声明或真接线',
  },
  {
    term: '执行',
    aliases: ['Execute Tool'],
    meaning: '本机试跑该 Tool；不等于生产调度或已审批上架',
  },
  {
    term: '对话创建',
    aliases: ['chat create tool'],
    meaning: '对话辅助生成 Tool 草稿，仍须保存与审核',
  },
  {
    term: '签名',
    aliases: ['批量签名', '验签'],
    meaning: '治理签名线；与资产审批通过不同；未签名一般仍可本机执行',
  },
  {
    term: 'totalTools',
    aliases: ['Tool 数量', '几个 Tool'],
    meaning: '本页列表条数；以页面上报为准',
  },
  {
    term: '~/.aiplat/tools',
    aliases: ['磁盘 Tool'],
    meaning: 'Tool 落盘目录',
  },
];

export function toolsGlossaryPromptText(maxLen = 1200): string {
  const parts: string[] = [];
  for (const e of TOOLS_GLOSSARY) {
    parts.push(`${e.term}=${e.meaning}`);
    for (const a of e.aliases || []) parts.push(`${a}=${e.meaning}`);
  }
  const text = parts.join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

export function toolsConsultantPageData(input: {
  totalTools: number;
  statusCount: Record<string, number>;
}): Record<string, unknown> {
  return {
    screen: '应用库 Tool：原子副作用出口，不是 Skill/Agent 页',
    what: '创建/编辑/执行/审核 Tool；签名与审批分线',
    can: '本机试跑、改源码描述、AI 审核',
    not: '审核通过≠资产审批上架；勿把 prompt Skill 说成已真上传',
    totalTools: input.totalTools,
    statusCount: input.statusCount,
    guideGlossary: toolsGlossaryPromptText(1200),
  };
}
