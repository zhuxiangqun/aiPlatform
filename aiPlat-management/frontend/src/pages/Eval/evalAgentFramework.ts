/**
 * Product north-star: Agent eval as three layers — dimensions / methods / conclusions.
 * UI SSOT for「评什么」— coverage status ≠ proof of eval sufficiency.
 */

export type EvalDimCoverage = 'partial' | 'thin' | 'missing';

export type EvalAgentDimension = {
  id: string;
  title: string;
  asks: string;
  examples: string;
  /** What this product can show today (honest). Coverage ≠ sufficiency. */
  today: string;
  coverage: EvalDimCoverage;
};

/** Layer 1a: 8 core dimensions (discuss「评什么」— fairly complete checklist). */
export const EVAL_AGENT_DIMENSIONS: EvalAgentDimension[] = [
  {
    id: 'task_result',
    title: '1. 任务结果',
    asks: '是否完成用户目标；结果是否正确、完整、符合约束',
    examples: '成功率、正确率、完成度、必需步骤覆盖率',
    today: '可归因报告含 task_result；正式评测/历史分可看。≠ 业务金标准全覆盖',
    coverage: 'partial',
  },
  {
    id: 'grounding',
    title: '2. 事实与证据',
    asks: '事实是否准确；依据是否支持结论；是否编造',
    examples: '事实错误率、证据支持率、引用准确率、无依据断言率',
    today: 'grounding：builtin must_contain/expected_facts → fact_support_rate；UI 可看明细；≠ NLI/充分',
    coverage: 'partial',
  },
  {
    id: 'tools',
    title: '3. 工具与行动',
    asks: '是否选对工具/参数/顺序；失败与副作用是否处理好',
    examples: '工具选择准确率、调用成功率、参数错误率、误操作率',
    today:
      '有 tools_trajectory 报告 ≠ 已证明工具语义正确、轨迹高效、副作用门禁齐全',
    coverage: 'partial',
  },
  {
    id: 'trajectory',
    title: '4. 任务规划与轨迹',
    asks: '拆解、依赖、重规划是否合理；是否循环/无效调用',
    examples: '关键步骤覆盖率、无效调用率、重试、循环率、轨迹合规率',
    today: '并入 tools_trajectory；缺「试错成功 vs 规划成功」与长程恢复对比',
    coverage: 'partial',
  },
  {
    id: 'safety',
    title: '5. 安全与权限',
    asks: '权限、隐私、危险操作；拒绝/升级是否正确',
    examples: '越权率、泄露率、危险请求处理率、拒绝准确率',
    today:
      '安全 veto=发布硬门槛；拒绝校准另见 refusal_calibration（over/under_refusal）',
    coverage: 'partial',
  },
  {
    id: 'robustness',
    title: '6. 鲁棒性',
    asks: '含糊、缺失、冲突、对抗输入时是否仍稳健',
    examples: '扰动成功率、边界案例、注入抵抗、失败恢复',
    today:
      '可归因 robustness：识别 noise/missing_info/tool_failure 等扰动试卷 + 完成率/对抗分；≠ 红队充分',
    coverage: 'partial',
  },
  {
    id: 'interaction',
    title: '7. 交互质量',
    asks: '意图理解、表达清晰；不确定时是否恰当澄清',
    examples: '意图匹配、澄清适当率、可读性、用户修正率',
    today:
      '可归因 interaction：text_quality + missing_info/clarify 试卷完成率；≠ 人机体验充分',
    coverage: 'partial',
  },
  {
    id: 'efficiency',
    title: '8. 运行效率',
    asks: '时间、调用、资源是否可用；质量是否稳定',
    examples: '延迟 p50/p95、单任务成本、token、重复运行方差',
    today: '可归因报告含 cost 软警告；缺 pass@k 方差与成本归一化成功率',
    coverage: 'partial',
  },
];

/**
 * Layer 1b: specialty slices — needed for executable publish decisions,
 * not fully absorbed by the 8-dim checklist alone.
 */
export const EVAL_AGENT_SPECIALTY_SLICES: EvalAgentDimension[] = [
  {
    id: 'memory_horizon',
    title: 'S1. 记忆与多轮/长程',
    asks: '跨轮是否保持目标/约束/偏好；中断后能否恢复；状态是否污染',
    examples: '跨轮约束保持率、恢复成功率、状态污染率、长任务完成率',
    today: '可归因 memory_horizon：识别 session/multi 试卷或 turns；专用长程恢复用例仍缺',
    coverage: 'thin',
  },
  {
    id: 'set_reliability',
    title: 'S2. 评测集与判分可靠性',
    asks: '用例是否覆盖真实风险；难度是否有区分度；标签/Judge 是否可靠',
    examples: '风险覆盖、难度分层、标注一致 κ、Judge↔人工一致、同题方差',
    today: 'score_variance + judge_agreement（有 κ 则展示，否则 missing）；accuracy_claim=false',
    coverage: 'thin',
  },
  {
    id: 'failure_observability',
    title: 'S3. 失败恢复与可观测性',
    asks: '失败发生在哪一步；是否检测到错误；是否安全恢复；能否归因',
    examples: '失败步骤定位、检测率、安全恢复率、Trace 归因到模型/Prompt/工具/数据',
    today: 'failure_localization：approx_step + evidence/errors；完整 Trace 回放仍弱',
    coverage: 'partial',
  },
  {
    id: 'online_ux',
    title: 'S4. 线上效果与用户体验',
    asks: '离线基准能否代表真实流量；用户是否满意；受控实验是否改善',
    examples: '用户反馈、线上抽样评估、受控 A/B、回归告警',
    today: 'online_sample 摘要 + controlled_ab 切片（缺实验则 missing）；≠ 已做线上 A/B',
    coverage: 'thin',
  },
];

/** Layer 2: methods — each answers different questions. */
export const EVAL_AGENT_METHOD_NOTES = [
  '确定性规则 / 程序检查：格式、权限、schema、工具约束（可确定项）',
  '轨迹回放：步骤顺序、无效调用、循环、失败点定位',
  '人工金标 + 校准后的 LLM Judge：事实、完成度、语义质量（须报一致率）',
  '对抗 / 故障注入 / 红队：鲁棒与安全边界（按风险选用）',
  '同题多次运行：报分布/区间与方差，不单次平均定生死',
  '线上抽样与受控 A/B：离线分数不能单独代表真实流量',
] as const;

/**
 * Layer 3: conclusions for publish — what a decision-ready report must state.
 */
export const EVAL_AGENT_CONCLUSION_NOTES = [
  '覆盖范围：测了哪些维/切片、未测哪些（覆盖 ≠ 充分）',
  '样本量与置信度：n、难度分层、同题方差、Judge/人工一致证据',
  '失败证据：步骤定位、Trace 归因、可复现样例',
  '硬门槛：安全关键失败 → veto；其余看分数与趋势，不定生死单靠总分',
  '适用环境：本机/租户/模型版本；不得外推为未测环境已授权',
] as const;

/** @deprecated alias — prefer EVAL_AGENT_CONCLUSION_NOTES */
export const EVAL_AGENT_DELIVERABLES = EVAL_AGENT_CONCLUSION_NOTES;

export const EVAL_AGENT_META = {
  checklistOk:
    '讨论「评什么」：8 维清单较全面；另需记忆/长程、评测集可靠性、失败可观测、线上体验等专项切片。',
  schemeIncomplete:
    '声称「已能完整评测 Agent / 可发布」：须逐项验证用例、判分可靠性、长程覆盖与线上证据；本页「产品现状」只描述覆盖，不是充分性证明。',
} as const;

export function coverageLabel(c: EvalDimCoverage): string {
  if (c === 'partial') return '部分覆盖';
  if (c === 'thin') return '薄弱';
  return '未落地';
}
