/**
 * App Factory glossary — Layer A for 小朱 (XIAOZHU.md §1.2–1.4).
 */
export type FactoryGlossEntry = { term: string; aliases?: string[]; meaning: string };

export const FACTORY_GLOSSARY: FactoryGlossEntry[] = [
  {
    term: '应用工厂',
    aliases: ['/app/factory', '工厂'],
    meaning: '从需求到可部署应用的交付流水线；不是工作区里再建一个 Agent',
  },
  {
    term: '项目',
    aliases: ['project', 'projectCount'],
    meaning: '工厂内的一个交付项目；有阶段/状态/可能卡在人审',
  },
  {
    term: '已部署应用',
    aliases: ['deployedAppCount', '/app/apps'],
    meaning: '工厂产出已部署实例数；与工作区 Agent 数量无关',
  },
  {
    term: 'HITL',
    aliases: ['awaitingApproval', '人审', '等待审批'],
    meaning: '流水线停在等人审批/确认；需在工厂或审批入口处理，小朱不代批',
  },
  {
    term: '卡住提示',
    aliases: ['stuckHints', 'stuckHintCount'],
    meaning: '项目可能阻塞的简短提示；以页面上报为准',
  },
  {
    term: '通过率',
    aliases: ['avgPassRate', 'passRate'],
    meaning: '项目侧质量/门禁通过率摘要；不是模型 accuracy_claim',
  },
  {
    term: '阶段',
    aliases: ['stageCount', 'phase', 'selectedProjectPhase'],
    meaning: '流水线当前阶段名；阶段名来自配置，勿硬套业务口头禅',
  },
  {
    term: 'Agent',
    aliases: ['/workspace/agents'],
    meaning: '平台内角色；做助手去 Agent 页，做产品交付留在工厂',
  },
  {
    term: 'FDE 工作台',
    aliases: ['/diagnostics/fde'],
    meaning: '现场诊断与交付签收；与工厂流水线相关但入口不同',
  },
];

export function factoryGlossaryPromptText(maxLen = 1200): string {
  const parts: string[] = [];
  for (const e of FACTORY_GLOSSARY) {
    parts.push(`${e.term}=${e.meaning}`);
    for (const a of e.aliases || []) parts.push(`${a}=${e.meaning}`);
  }
  const text = parts.join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}
