/**
 * Workspace MCP glossary — Layer A for 小朱 (XIAOZHU.md §1.2–1.4).
 */
export type McpGlossEntry = { term: string; aliases?: string[]; meaning: string };

export const MCP_GLOSSARY: McpGlossEntry[] = [
  {
    term: '应用库 MCP',
    aliases: ['MCP 库', '/workspace/mcp'],
    meaning: '管理 MCP Server 接入（~/.aiplat/mcps）；外部工具服务，不是本地 Tool 文件',
  },
  {
    term: 'MCP Server',
    aliases: ['MCP 服务', 'server'],
    meaning: '一个 MCP 服务端实例；可启用/禁用、测工具、签名',
  },
  {
    term: 'transport',
    aliases: ['传输'],
    meaning: 'MCP 传输方式（如 stdio/http）；影响如何拉起与鉴权',
  },
  {
    term: '模板安装',
    aliases: ['HTTP API 桥接', 'Shell 命令执行', 'file_ops', 'db_query'],
    meaning: '用内置模板快速建 MCP；建完仍须配置与测试',
  },
  {
    term: '测试工具',
    aliases: ['测 MCP', 'Execute MCP'],
    meaning: '对本机某 MCP 工具试调用；不等于生产授权',
  },
  {
    term: '启用开关',
    aliases: ['setServerEnabled', 'enabled'],
    meaning: '是否对本机暴露该 MCP；关闭后 Agent 不应再调到',
  },
  {
    term: '资产审批',
    aliases: ['/approval?type=mcp'],
    meaning: 'MCP 上架/通过走审批时在此入口；本页测试≠审批通过',
  },
  {
    term: 'Tool',
    aliases: ['/workspace/tools'],
    meaning: '本地 Tool 定义页；与 MCP 并列的副作用出口',
  },
  {
    term: 'totalServers',
    aliases: ['MCP 数量', '几个 MCP'],
    meaning: '本页 Server 条数；以页面上报为准',
  },
  {
    term: '~/.aiplat/mcps',
    aliases: ['磁盘 MCP'],
    meaning: 'MCP 配置落盘目录',
  },
];

export function mcpGlossaryPromptText(maxLen = 1200): string {
  const parts: string[] = [];
  for (const e of MCP_GLOSSARY) {
    parts.push(`${e.term}=${e.meaning}`);
    for (const a of e.aliases || []) parts.push(`${a}=${e.meaning}`);
  }
  const text = parts.join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

export function mcpConsultantPageData(input: {
  totalServers: number;
  enabled: number;
}): Record<string, unknown> {
  return {
    screen: '应用库 MCP：外部工具服务接入，不是本地 Tool 页',
    what: '添加/启用 MCP、测工具、模板安装与签名',
    can: '本机测试 MCP 工具调用',
    not: '测试成功≠生产授权或资产已上架',
    totalServers: input.totalServers,
    enabled: input.enabled,
    guideGlossary: mcpGlossaryPromptText(1200),
  };
}
