/**
 * Plain-language guides for Eval Center tabs (local-first; honesty intact).
 * Field/jargon dictionary SSOT: ./evalGlossary.ts (systematic inventory).
 */
import { evalGlossaryPromptText } from './evalGlossary';

export type EvalTabGuide = {
  title: string;
  /** Plain: what this tab is for */
  what: string;
  /** Optional: why the feature exists (product intent) */
  why?: string;
  /** What you can do here / which buttons */
  can: string;
  /** What NOT to claim from this tab */
  not: string;
};

export const EVAL_TAB_GUIDES: Record<string, EvalTabGuide> = {
  overview: {
    title: '总览',
    what: '先分清：评测 Agent / Skill / 生成应用＝成果物；验管道＝只测计分/排队通不通。',
    why: '混在一起会以为 Code-review/Session/Skill 管道在评产品；其实那些是自检。',
    can: '三张成果物卡片分别进 Agent / Skill / 生成应用；验管道做联调。',
    not: '管道 succeeded ≠ 产品已评准。',
  },
  sets: {
    title: '评测集',
    what: '维护评测题目/样本集合（Core EvalStore：新建 set、追加 task、导入黄金集）。',
    can: '创建 set、向选中 set 追加 task、导入 code-review-gold / Bootstrap E3。',
    not: '有评测集 ≠ 已经证明模型准；尚无画面改删已有条目。',
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
  'typed-plan': {
    title: '对象Plan',
    what:
      '通用对象 Plan 链：prompt/workflow/model/dataset/system 的 *-plan-exam，以及 L5 claims_gate 门槛核对。',
    why: 'Object Contract §0.8 Runner 与 §0.9 解禁门禁的操作面；与 Agent 冒烟 / 页面 Prompts 分列。',
    can:
      '选对象类型跑 dry/live Plan exam；填写范围字段核对 claims_gate（默认不解禁；可本机镜像或调 API）。',
    not:
      'Plan exam 绿 ≠ 准确率；fixture dry ≠ 真实宿主；勾选 explicit_authorize 也不自动改正式报告 claim。',
  },
  'case-packs': {
    title: 'Case Pack',
    what: '工作区 Case Pack 工厂：草稿扩题、人审、freeze、version++、coverage、变异/trace/holdout。',
    why: 'Plan v2 的题库载体；frozen 保可比，L3 generated/trace 保发现，均默认不可 claim。',
    can: 'draft→review→freeze；expand/bump；mutate/from-trace；holdout 标记；coverage 盘点。',
    not: 'freeze ≠ 准确率；generated/trace 不可 freeze 入 claim；claim_eligible 恒 false。',
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
    title: '评测 Agent',
    what:
      '评测对象＝命名工作区本机 Agent，或外部拉模式 HTTP 目标（对话文本）。框架三层：维度（8 维+专项切片）/ 方法 / 结论。',
    why: '成果物入口之一；讨论「评什么」8 维较全，可发布方案还需判分可靠性、长程与线上证据。',
    can:
      '本机：选用例集预检/正式评测/本地标准冒烟；冒烟矩阵 fail/warn→待处理清单点「去单卷看」；外部：登记目标→预检/live 拉；看可归因与本工作区历史（ext:{id}）。问错误原因时优先看本页 smokeIssue*，勿默认跳 /diagnostics/runs。',
    not:
      '外部拉工具序(IN_ORDER) ≠ 副作用充分；≠ 本机 ReAct；覆盖现状 ≠ 评测充分；工程分 ≠ 可发布；≠ 准确率认证；≠ Skill/生成应用；冒烟维度告警 ≠ 平台 runs 执行失败。',
  },
  skills: {
    title: '评测 Skill',
    what: '评测对象＝已登记的 Skill suite（platform skill_evals）。选 suite → 跑 → 看 run/results。',
    why: '与 Agent 同级的成果物入口；评触发/质量套件，不是 Docker fixture。',
    can: '刷新 suite 列表；跑 heuristic suite；查看 metrics 与 case 结果表。',
    not: '≠ 验管道「Skill 管道」fixture；无 suite 时需先 API upsert；成功 ≠ 准确率认证。',
  },
  apps: {
    title: '评测生成应用',
    what: '评测对象＝生成应用某次 Run（run_id）。走 runs_eval：最新评测 / 自动评测。',
    why: '与 Agent 同级的成果物入口；身份权威是 run_id，不是 Agent 榜。',
    can: '粘贴 run_id；可选 project_id；查看 latest 或触发 autoEvaluate。',
    not: '≠ Agent 工程分；≠ 管道自检；报告字段随 runs_eval 原生形状，非可归因 v0。',
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
    what:
      '先自检「打分尺子」好不好用：用黄金集里写死的「假装评审结果」去对「标准答案缺陷」，算出匹配率（P/R）。默认不调模型、不读你的仓库、也不跑评审 Agent。',
    why:
      '后面真要评代码评审时，也用同一套黄金集和匹配器。若装种子失败、匹配器坏了、报告写不出，live 分数就不可信。match-only 几秒、零 LLM，专门把这条计分管线验通（CI / 值班板也会点它）。',
    can:
      '「Run match-only」= 立刻本机对答案；「Enqueue job」= 丢到本机评测队列看 Job 通不通；「刷新报告」= 看已落盘条数。题在种子目录（workspace_seeds 或 ~/.aiplat/eval/tenants/eval-v1/code_review_gold），不是上面「评测集」Tab。',
    not:
      '匹配率高 ≠ 评审 Agent/模型测准了；也 ≠ 某个真实项目代码被审过。要测真评审，须给 case 配 target 再跑 live（不是本页默认）。',
  },
  session: {
    title: 'Session',
    what:
      '多轮对话「对账」冒烟：默认把预制的 prompt / expected / actual 丢进 session_eval runner，看每轮是否对上。不调真模型、不连真实用户会话。',
    why:
      '验证本机评测队列 + 多轮计分管线能跑通；Code-review 验的是评审尺子，这里验的是会话轮次对账。CI / 本地联调需要一条「对话类」Job 路径。',
    can:
      '本页只有 Enqueue（无 match-only）：点「Enqueue job」看 status=succeeded。默认载荷是 2 轮口算 fixture（1+1→2，再 +1→3）。',
    not:
      'succeeded ≠ 对话 Agent 测准了，也 ≠ 真实多轮业务场景已验证。accuracy_claim 仍为 false。',
  },
  arena: {
    title: 'Arena',
    what: '两个回答比长短的烟雾测试（length smoke），不是质量裁判。',
    why: '先确认 Arena runner / 盲评展示链路能 enqueue，再谈真质量对比。',
    can: 'Enqueue 看 job 是否成功；盲评结果只作证据展示。',
    not: '更长/胜出 ≠ 质量更好；不打开质量门禁。',
  },
  skill: {
    title: 'Skill 管道',
    what:
      '管道自检：技能/工具类 fixture 计分，用写死的 cases/results 对账，并探测 Docker 沙箱路径。',
    why:
      '先确认沙箱探针 + suite runner 通；真 Skill suite 请用成果物「评测 Skill」。',
    can:
      'Docker 可用时 Enqueue；看 job 成功与否。默认 mode=fixture，不会调用真实工具实现。',
    not:
      '≠ 成果物 Skill suite；不会真跑 live skill；成功 ≠ 工具能力已认证。',
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
    screen:
      '评测中心：成果物=Agent/Skill/生成应用；验管道(Code-review/Session/Skill管道)=自检非产品；非准确率',
    selectedTab: input.tabId,
    tabTitle: g?.title || input.tabId,
    what: g?.what || '',
    why: g?.why || '',
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
