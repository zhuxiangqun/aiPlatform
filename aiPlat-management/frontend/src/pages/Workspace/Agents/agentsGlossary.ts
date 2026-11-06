/**
 * Workspace Agents glossary for UI + 小朱 — Layer A (page knowledge) exemplar #2.
 *
 * See XIAOZHU.md §1.2–1.4: short verifiable screen facts live here (A);
 * platform how-to → CAPABILITIES / controlled Wiki (B); external trivia → LLM (C).
 *
 * ## How this dictionary is built
 * 1. Lifecycle statuses shown in filters / table (draft→listed).
 * 2. Header actions (创建、审批、签名、测试…).
 * 3. Role boundaries (Agent vs Skill / 工厂 / 资产审批).
 *
 * ## Maintenance
 * - New visible Agent-page label → same PR update here.
 * - Do not put long tutorials or design-vision here (B docs).
 */

export type AgentsGlossDomain =
  | 'lifecycle'
  | 'actions'
  | 'roles'
  | 'types'
  | 'ops';

export type AgentsGlossEntry = {
  term: string;
  aliases?: string[];
  meaning: string;
  domain: AgentsGlossDomain;
};

/** Full inventory — extend here first; 小朱 reads the flattened form. */
export const AGENTS_GLOSSARY: AgentsGlossEntry[] = [
  // ── screen ───────────────────────────────────────────────────────
  {
    term: '应用库 Agent',
    aliases: ['Agent 管理', '/workspace/agents', '工作区 Agent'],
    meaning:
      '管理 ~/.aiplat/agents 里的平台内角色；可编辑/删除/本机执行；不是整条应用工厂流水线',
    domain: 'roles',
  },
  {
    term: 'Agent',
    aliases: ['智能体', '角色'],
    meaning: '可绑多个 Skill 的角色；本页管注册与生命周期，不代替 Skill/Tool 本体编辑',
    domain: 'roles',
  },
  {
    term: 'Skill',
    aliases: ['技能'],
    meaning: '可复用动作/SOP；在 Skill 库维护，Agent 只引用绑定，不在本页写 Skill 正文',
    domain: 'roles',
  },
  {
    term: '应用工厂',
    aliases: ['工厂', '/app/factory'],
    meaning: '交付应用产品的入口；与本页「建平台内角色」不同，勿把工厂流水线说成本页功能',
    domain: 'roles',
  },
  {
    term: '资产审批',
    aliases: ['/approval', '审批中心'],
    meaning: '管理员通过/上架 Agent 的地方；本页「待审核」不能在此页点通过',
    domain: 'roles',
  },

  // ── lifecycle ────────────────────────────────────────────────────
  {
    term: 'draft',
    aliases: ['草稿'],
    meaning: '草稿：可本机对话/执行自测；尚未进入待审核',
    domain: 'lifecycle',
  },
  {
    term: 'ready',
    aliases: ['待审核'],
    meaning: '已提交审批、等待资产审批通过；本页不能直接点通过',
    domain: 'lifecycle',
  },
  {
    term: 'published',
    aliases: ['已发布'],
    meaning: '审批已通过；通常还需「上架」才会 listed',
    domain: 'lifecycle',
  },
  {
    term: 'listed',
    aliases: ['已上架'],
    meaning: '已上架可供选用；生命周期末态之一（另有 deprecated）',
    domain: 'lifecycle',
  },
  {
    term: 'deprecated',
    aliases: ['已废弃'],
    meaning: '已废弃，不应再当新工作首选',
    domain: 'lifecycle',
  },
  {
    term: '提交审批',
    aliases: ['draft → ready'],
    meaning: '行内更多菜单：把 draft 变为 ready（待审核），随后去资产审批',
    domain: 'lifecycle',
  },

  // ── header actions ───────────────────────────────────────────────
  {
    term: '创建',
    aliases: ['手动创建'],
    meaning: '打开表单新建 Agent 草稿',
    domain: 'actions',
  },
  {
    term: '对话创建',
    aliases: ['chat create'],
    meaning: '用对话辅助生成 Agent 草稿，仍须人工保存与后续审批',
    domain: 'actions',
  },
  {
    term: '从模板安装',
    aliases: ['种子', 'seeds', '模板'],
    meaning: '从工作区种子模板安装 Agent，不是远端应用商店',
    domain: 'actions',
  },
  {
    term: '清理重复',
    aliases: ['dedupe', '合并重复'],
    meaning: '合并同名且技能/工具相同的重复 Agent 记录',
    domain: 'actions',
  },
  {
    term: '批量签名',
    aliases: ['签名'],
    meaning: '治理签名线；与「审批通过」不同；本地执行一般不强制签名',
    domain: 'actions',
  },
  {
    term: '测试全部',
    aliases: ['测全部', 'test all'],
    meaning: '对本页列表做一轮本地连通/执行冒烟，不等于生产验收',
    domain: 'actions',
  },
  {
    term: 'Smart Agent Router',
    aliases: ['自动匹配 Agent', '路由输入框'],
    meaning: '按自然语言需求匹配已有 Agent；匹配失败不表示要新建工厂项目',
    domain: 'actions',
  },

  // ── types / ops ──────────────────────────────────────────────────
  {
    term: 'conversational',
    aliases: ['对话型'],
    meaning: 'agent_type：偏对话咨询（如小朱 platform_consultant）',
    domain: 'types',
  },
  {
    term: 'plan',
    aliases: ['规划型'],
    meaning: 'agent_type：偏规划拆解',
    domain: 'types',
  },
  {
    term: 'tool',
    aliases: ['工具型'],
    meaning: 'agent_type：偏工具调用',
    domain: 'types',
  },
  {
    term: 'rag',
    aliases: ['检索型'],
    meaning: 'agent_type：偏检索增强；顾问小朱默认关 semantic_injection，勿与本类型混谈',
    domain: 'types',
  },
  {
    term: 'totalAgents',
    aliases: ['Agent 数量', '几个 Agent'],
    meaning: '本页列表当前条数（来自磁盘扫描上报）；以页面数字为准，勿用 Wiki 猜测',
    domain: 'ops',
  },
  {
    term: '~/.aiplat/agents',
    aliases: ['AIPLAT_HOME/agents', '磁盘 Agent'],
    meaning: 'Agent 文件落盘目录；本页读写的是这里，不是仓库里的临时草稿 alone',
    domain: 'ops',
  },
];

export function flattenAgentsGlossary(
  entries: AgentsGlossEntry[] = AGENTS_GLOSSARY,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const e of entries) {
    out[e.term] = e.meaning;
    for (const a of e.aliases || []) {
      if (a && !(a in out)) out[a] = e.meaning;
    }
  }
  return out;
}

export function agentsGlossaryPromptText(maxLen = 1400): string {
  const flat = flattenAgentsGlossary();
  const text = Object.entries(flat)
    .map(([k, v]) => `${k}=${v}`)
    .join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

export function agentsGlossaryDomainCounts(): Record<AgentsGlossDomain, number> {
  const counts = {} as Record<AgentsGlossDomain, number>;
  for (const e of AGENTS_GLOSSARY) {
    counts[e.domain] = (counts[e.domain] || 0) + 1;
  }
  return counts;
}

/** Compact payload helper for PageDataBridge. */
export function agentsConsultantPageData(input: {
  totalAgents: number;
  statusCount: Record<string, number>;
  running: number;
  ready: number;
  error: number;
}): Record<string, unknown> {
  return {
    screen: '应用库 Agent：平台内角色注册与生命周期，不是应用工厂',
    what: '查看/创建/测试 Agent；提交审批后去资产审批通过与上架',
    can: '本机编辑草稿、对话/执行自测、提交审批、跳转资产审批',
    not: '本页不能把待审核直接点成已发布；不是工厂交付流水线',
    totalAgents: input.totalAgents,
    statusCount: input.statusCount,
    running: input.running,
    ready: input.ready,
    error: input.error,
    guideGlossary: agentsGlossaryPromptText(1400),
  };
}
