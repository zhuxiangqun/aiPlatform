/**
 * Workspace Skills glossary for UI + 小朱 — Layer A (page knowledge) exemplar #3.
 *
 * See XIAOZHU.md §1.2–1.4. Short verifiable screen facts only (A).
 */

export type SkillsGlossDomain =
  | 'lifecycle'
  | 'actions'
  | 'roles'
  | 'categories'
  | 'gov'
  | 'ops';

export type SkillsGlossEntry = {
  term: string;
  aliases?: string[];
  meaning: string;
  domain: SkillsGlossDomain;
};

export const SKILLS_GLOSSARY: SkillsGlossEntry[] = [
  {
    term: '应用库 Skill',
    aliases: ['Skill 库', '/workspace/skills', '工作区 Skill'],
    meaning: '管理 ~/.aiplat/skills 里的可复用动作/SOP；可编辑删除；不是 Agent 角色页',
    domain: 'roles',
  },
  {
    term: 'Skill',
    aliases: ['技能', 'SKILL.md'],
    meaning: '可复用能力单元（prompt/handler）；Agent 绑定调用，本页维护 Skill 本体',
    domain: 'roles',
  },
  {
    term: 'Agent',
    aliases: ['智能体', '/workspace/agents'],
    meaning: '角色；在 Agent 页管理绑定。本页改 Skill 不会自动改 Agent 生命周期',
    domain: 'roles',
  },
  {
    term: 'Tool',
    aliases: ['工具', '/workspace/tools'],
    meaning: '原子副作用出口；Skill 可声明绑定 Tool，真副作用在 Tool/MCP，不在纯 prompt',
    domain: 'roles',
  },
  {
    term: 'execution_type',
    aliases: ['执行类型', 'handler', 'prompt'],
    meaning:
      'SKILL.md 声明：handler=须有 handler.py；prompt=纯 LLM；有 handler 却标 prompt 为误配风险',
    domain: 'roles',
  },
  {
    term: '资产审批',
    aliases: ['/approval?type=skill', 'Skill 审批'],
    meaning: '管理员通过/上架 Skill；本页待审核不能直接点通过',
    domain: 'roles',
  },

  {
    term: 'draft',
    aliases: ['草稿'],
    meaning: '草稿：可执行自测；尚未提交审批',
    domain: 'lifecycle',
  },
  {
    term: 'ready',
    aliases: ['待审核'],
    meaning: '已提交审批，等资产审批；本页不能点通过',
    domain: 'lifecycle',
  },
  {
    term: 'published',
    aliases: ['已发布'],
    meaning: '审批已通过；通常还需上架才 listed',
    domain: 'lifecycle',
  },
  {
    term: 'listed',
    aliases: ['已上架'],
    meaning: '已上架可供选用；生命周期对外可用态之一',
    domain: 'lifecycle',
  },
  {
    term: 'deprecated',
    aliases: ['已废弃', '弃用'],
    meaning: '已弃用；可恢复，硬删除在确认框',
    domain: 'lifecycle',
  },
  {
    term: '提交审批',
    aliases: ['draft → ready'],
    meaning: '行内更多：draft→ready，随后去资产审批',
    domain: 'lifecycle',
  },
  {
    term: '仅启用',
    aliases: ['enabled_only', '已启用'],
    meaning: '过滤约等于 published/listed 可用态；旧「启用」开关语义的列表过滤',
    domain: 'lifecycle',
  },

  {
    term: '创建',
    aliases: ['新建 Skill'],
    meaning: '表单新建 Skill 草稿',
    domain: 'actions',
  },
  {
    term: '对话创建',
    aliases: ['chat create skill'],
    meaning: '对话辅助生成 Skill 草稿，仍须保存与审批',
    domain: 'actions',
  },
  {
    term: '执行',
    aliases: ['Execute', '本机执行'],
    meaning: '对本机该 Skill 跑一次执行弹窗；不等于生产调度',
    domain: 'actions',
  },
  {
    term: '从模板安装',
    aliases: ['种子', 'seeds'],
    meaning: '从工作区种子安装 Skill，不是应用商店',
    domain: 'actions',
  },
  {
    term: '批量签名',
    aliases: ['签名'],
    meaning: '治理签名；与上架审核无关；未签名一般仍可本机执行',
    domain: 'actions',
  },
  {
    term: '导出插件',
    aliases: ['export plugin', '导出 zip'],
    meaning: '把 Skill 打成可导入的包 zip，不改变审批状态',
    domain: 'actions',
  },

  {
    term: '治理',
    aliases: ['GovDetailBadge', '签名/冒烟'],
    meaning: '列上治理徽标：签名/冒烟校验状态；与上架审核是两条线',
    domain: 'gov',
  },
  {
    term: '上架状态',
    aliases: ['StatusBadge', '生命周期列'],
    meaning: 'draft→ready→published→listed（及 deprecated）展示列',
    domain: 'gov',
  },
  {
    term: '来源',
    aliases: ['provenance', 'source'],
    meaning: 'Skill 从哪来（种子/导入/本地等），不是审批结论',
    domain: 'gov',
  },

  {
    term: 'general',
    aliases: ['通用'],
    meaning: 'Skill 分类筛选项：通用（非专用域）',
    domain: 'categories',
  },
  {
    term: 'execution',
    aliases: ['执行分类'],
    meaning: 'Skill 分类筛选项：执行向能力',
    domain: 'categories',
  },
  {
    term: 'retrieval',
    aliases: ['检索分类'],
    meaning: 'Skill 分类筛选项：检索向能力',
    domain: 'categories',
  },
  {
    term: 'analysis',
    aliases: ['分析'],
    meaning: 'Skill 分类筛选项：分析向能力',
    domain: 'categories',
  },
  {
    term: 'generation',
    aliases: ['生成'],
    meaning: 'Skill 分类筛选项：生成向能力',
    domain: 'categories',
  },
  {
    term: 'transformation',
    aliases: ['转换'],
    meaning: 'Skill 分类筛选项：转换向能力',
    domain: 'categories',
  },

  {
    term: 'totalSkills',
    aliases: ['Skill 数量', '几个 Skill'],
    meaning: '本页列表当前条数；以页面上报为准',
    domain: 'ops',
  },
  {
    term: '~/.aiplat/skills',
    aliases: ['AIPLAT_HOME/skills', '磁盘 Skill'],
    meaning: 'Skill 落盘目录；本页读写这里',
    domain: 'ops',
  },
  {
    term: 'Skill Pack 过滤',
    aliases: ['filterSkillIds'],
    meaning: '从 Skill Pack 跳转带来的 id 过滤；可清除，不等于审核队列',
    domain: 'ops',
  },
];

export function flattenSkillsGlossary(
  entries: SkillsGlossEntry[] = SKILLS_GLOSSARY,
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

export function skillsGlossaryPromptText(maxLen = 1400): string {
  const flat = flattenSkillsGlossary();
  const text = Object.entries(flat)
    .map(([k, v]) => `${k}=${v}`)
    .join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

export function skillsGlossaryDomainCounts(): Record<SkillsGlossDomain, number> {
  const counts = {} as Record<SkillsGlossDomain, number>;
  for (const e of SKILLS_GLOSSARY) {
    counts[e.domain] = (counts[e.domain] || 0) + 1;
  }
  return counts;
}

export function skillsConsultantPageData(input: {
  totalSkills: number;
  statusCount: Record<string, number>;
  ready: number;
  listed: number;
  deprecated: number;
}): Record<string, unknown> {
  return {
    screen: '应用库 Skill：可复用动作/SOP，不是 Agent 角色页',
    what: '编辑/执行 Skill；提交审批后去资产审批通过与上架',
    can: '本机创建草稿、执行自测、提交审批、签名与模板安装',
    not: '本页不能把待审核直接点成已发布；execution_type=handler 须有真实 handler',
    totalSkills: input.totalSkills,
    statusCount: input.statusCount,
    ready: input.ready,
    listed: input.listed,
    deprecated: input.deprecated,
    guideGlossary: skillsGlossaryPromptText(1400),
  };
}
