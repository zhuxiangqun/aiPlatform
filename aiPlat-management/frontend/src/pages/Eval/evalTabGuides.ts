/**
 * Plain-language guides for Eval Center tabs (local-first; honesty intact).
 * Field/jargon dictionary SSOT: ./evalGlossary.ts (systematic inventory).
 */
import { evalGlossaryPromptText } from './evalGlossary';

export type EvalTabGuide = {
  title: string;
  /** One-line: what this tab is for */
  what: string;
  /** What you can do here */
  can: string;
  /** What NOT to claim from this tab */
  not: string;
};

export const EVAL_TAB_GUIDES: Record<string, EvalTabGuide> = {
  overview: {
    title: '总览',
    what: '看本机评测「校准」是否就绪：任务数、是否锁定、上游是代理还是共宿。',
    can: '快速跳到复核、门禁、跑 Session/Arena 等。',
    not: '这里的数字不是模型准确率，也不能当对外发布证明。',
  },
  sets: {
    title: '评测集',
    what: '管理评测用的题目/样本集合（本地 store）。',
    can: '查看、选用评测集做后续跑分与报告。',
    not: '有评测集 ≠ 已经证明模型准。',
  },
  review: {
    title: '复核',
    what: '人工标定/裁决题目标签（G2a 工程校准）。',
    can: '处理待复核项；必要时锁定 v0 黄金集。',
    not: '单人复核没有一致性 κ；lock-v0 只锁本地黄金集，不是准确率。',
  },
  gates: {
    title: '门禁',
    what: '本机「过不过」的工程门（gate_claim）。',
    can: '跑/查看本地门禁结果，用于开发自检。',
    not: '本机门禁通过 ≠ 外部/staging/生产已授权。',
  },
  reports: {
    title: '报告',
    what: '查看已落库的评测报告与趋势（只读为主）。',
    can: '对照同版本报告、查证据摘要。',
    not: '报告分数默认不能写成 accuracy；跨版本分数不可直接比。',
  },
  g2b: {
    title: 'G2b',
    what: '双人盲标一致性（κ）收口面板——看标注员是否彼此一致。',
    can: '查看 scoped n=100 的 κ/通过率等汇总。',
    not: 'κ 是「人与人是否一致」，不是「模型准不准」。',
  },
  preference: {
    title: 'Preference',
    what: '偏好对（A/B 哪边更好）的汇总，偏产品口味而非对错题。',
    can: '查看偏好对数量与报告事实。',
    not: '偏好胜出 ≠ 准确率，也不替代 G2b。',
  },
  scorecard: {
    title: 'Scorecard',
    what: '能力成熟度打分卡（功能覆盖/证据是否齐）。',
    can: '看各项工程能力是否达到本地门槛。',
    not: '高分不等于 accuracy；功能分 ≠ 模型准。',
  },
  evidence: {
    title: 'Evidence',
    what: '证据树/审计清单：材料齐不齐。',
    can: '核对缺什么证据、哪些条目已就位。',
    not: '证据齐全 ≠ 准确率宣称。',
  },
  worksheets: {
    title: 'Worksheets',
    what: '给人填的工作表/发卷预览（人工标注用）。',
    can: '生成或预览空白包、发卷说明。',
    not: '空白包本身不算 κ，也不算准确率。',
  },
  agents: {
    title: 'Agents',
    what: '评测相关 Agent 套件列表（只读 + 诊断视图）。',
    can: '查看套件；动态跑分请走下方 Session 等 Job 面板。',
    not: '列表存在 ≠ 执行平面已正式生产拆分。',
  },
  knowledge: {
    title: 'Knowledge',
    what: '知识库检索类评测（kb_rag）。',
    can: '在 Job 平面 enqueue；或跳转知识库管理页。',
    not: '样本库空会失败；结果仍非 accuracy。',
  },
  prompts: {
    title: 'Prompts',
    what: 'Prompt 模板版本对比评测。',
    can: '指定两版模板 enqueue；或打开模板管理。',
    not: 'A 版分数高于 B ≠ 业务已验证准确。',
  },
  'code-review': {
    title: 'Code-review',
    what: '代码评审黄金集（code_review_gold）工程跑分。',
    can: 'Enqueue 本地 gold 任务；值班板入口在 Governance。',
    not: '匹配率是工程指标，不是对外准确率认证。',
  },
  session: {
    title: 'Session',
    what: '多轮对话评测：看会话里每轮答对/答错（fixture）。',
    can: '点 Enqueue job，在本机 worker 上跑通并看状态。',
    not: 'fixture 成功只证明链路通，不证明真实用户场景准确。',
  },
  arena: {
    title: 'Arena',
    what: '两个回答比长短的烟雾测试（length smoke），不是质量裁判。',
    can: 'Enqueue 看 job 是否成功；盲评结果只作证据展示。',
    not: '更长/胜出 ≠ 质量更好；不打开质量门禁。',
  },
  skill: {
    title: 'Skill',
    what: '技能/工具类评测的 fixture 计分；需 Docker 沙箱探针。',
    can: 'Docker 可用时 Enqueue；验证隔离路径 + 用例对账。',
    not: '不会真跑 live skill 工具；成功 ≠ 工具能力已认证。',
  },
  research: {
    title: 'P2 Research',
    what: '上下文 / 记忆持久化 / 自学习 三项工程 fixture 门。',
    can: '分别 Enqueue，确认本机门禁脚本对应路径可跑。',
    not: '不等于生产 Memory 写回或自学习已授权上线。',
  },
  settings: {
    title: '设置',
    what: 'G2c 等本地评测设置与自洽报告开关。',
    can: '查看/触发本地设置项（仍受诚实约束）。',
    not: '改设置不会把 accuracy_claim 变成 true。',
  },
};

/** Compact payload for 小朱 PageDataBridge (tab guide + systematic glossary). */
export function evalConsultantPageData(input: {
  tabId: string;
  upstreamMode?: string | null;
  accuracyClaim?: boolean;
  g2aReady?: boolean;
  v0Locked?: boolean;
  pending?: number | null;
  setsCount?: number;
  gatesCount?: number;
}): Record<string, unknown> {
  const g = EVAL_TAB_GUIDES[input.tabId];
  const catalog = Object.entries(EVAL_TAB_GUIDES)
    .map(([id, x]) => `${id}:${x.what}`)
    .join(' | ');
  return {
    screen: '评测中心：本机校准与 Job 联调，不是准确率/对外发布看板',
    selectedTab: input.tabId,
    tabTitle: g?.title || input.tabId,
    what: g?.what || '',
    can: g?.can || '',
    not: g?.not || '',
    honesty:
      'accuracy_claim 必须 false；κ≠准确率；gate_claim≠外部/staging授权；fixture成功≠真实准确',
    upstream: input.upstreamMode || 'unknown',
    accuracyClaim: String(Boolean(input.accuracyClaim)),
    g2aReady: String(Boolean(input.g2aReady)),
    v0Locked: String(Boolean(input.v0Locked)),
    pending: input.pending ?? '—',
    setsGates: `${input.setsCount ?? 0}/${input.gatesCount ?? 0}`,
    // Longer packs for cross-tab / field Q&A (pageDataToText allows guide*).
    guideCatalog: catalog.slice(0, 880),
    guideGlossary: evalGlossaryPromptText(1600),
  };
}
