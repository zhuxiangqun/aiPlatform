/**
 * Eval Center glossary for UI + 小朱 — Layer A (page knowledge) exemplar.
 *
 * See XIAOZHU.md §1.2–1.3: short verifiable screen facts live here (A);
 * platform how-to → CAPABILITIES / controlled Wiki (B); external trivia → LLM (C).
 *
 * ## How this dictionary is built (systematic, not ad-hoc)
 * 1. **Tabs** — every Eval Center tab id/label (see EVAL_TAB_GUIDES).
 * 2. **Visible fields** — `<dt>` / status keys shown on each panel
 *    (Overview, G2b, Preference, Scorecard, Evidence, Settings, Gates, Run…).
 * 3. **Honesty / plane banners** — accuracy_claim · κ · gate_claim · proxy/cohost.
 * 4. **Runners** — Session / Arena / Skill / P2 kinds the UI can enqueue.
 * 5. **Object contract maturity** — L1–L5 + A/B/C 指标口径（见 eval-object-contract-and-plan.md §0.5）。
 *
 * ## Maintenance rule
 * - Adding a user-visible Eval label or metric → add/update an entry **in the same change**.
 * - Prefer extending this file over patching answers in chat.
 * - Aliases (中文标签 / 英文 key) go on the same entry.
 * - Do not invent accuracy/production claims in `meaning`.
 * - Do not put long tutorials or design-vision here (those belong in B docs).
 * - Do not equate「Plan 能选中」with「已有可执行评测」or L5 校准.
 */

export type EvalGlossDomain =
  | 'honesty'
  | 'plane'
  | 'g2a'
  | 'g2b'
  | 'g2c'
  | 'preference'
  | 'scorecard'
  | 'evidence'
  | 'worksheets'
  | 'gates'
  | 'review'
  | 'runners'
  | 'reports'
  | 'sets'
  | 'tabs'
  | 'object_contract';

export type EvalGlossEntry = {
  /** Canonical term (prefer API/UI key when both exist). */
  term: string;
  /** Alternate spellings users may ask about. */
  aliases?: string[];
  /** Plain-language meaning (honesty intact). */
  meaning: string;
  domain: EvalGlossDomain;
  /** Tabs where this usually appears (empty = global / many). */
  surfaces?: string[];
};

/** Full inventory — extend here first; 小朱 reads the flattened form. */
export const EVAL_GLOSSARY: EvalGlossEntry[] = [
  // ── honesty (global banners) ─────────────────────────────────────
  {
    term: 'accuracy_claim',
    aliases: ['宣称准确率', 'accuracy'],
    meaning:
      '产品级准确率认证字段：方案A下永远false；跑通Job≠测准；不可与 scoped_accuracy_claim 混用',
    domain: 'honesty',
  },
  {
    term: 'scoped_accuracy_claim',
    aliases: ['G2b scoped claim', 'scoped准确率'],
    meaning:
      '仅G2b范围的准确率披露：owner attestation+aggregate --claim-ready后可为true；≠产品级accuracy_claim、≠安全/生产认证',
    domain: 'honesty',
    surfaces: ['g2b', 'scorecard'],
  },
  {
    term: 'claims_gate',
    aliases: ['L5门禁', 'claims-gate', 'eval.claims_gate.v1', '解禁'],
    meaning:
      'POST /evaluation/claims-gate：范围绑定+样本量+运行证据；输出eligible与claim；不静默抬升正式报告',
    domain: 'object_contract',
    surfaces: ['overview', 'agents'],
  },
  {
    term: 'kappa',
    aliases: ['κ', 'kappa_kind', 'inter_annotator_kappa', 'preference_κ'],
    meaning: '标注员之间是否一致（人与人）；不是模型准不准；单人复核时常为 null',
    domain: 'honesty',
    surfaces: ['overview', 'g2b', 'preference', 'settings'],
  },
  {
    term: 'gate_claim',
    aliases: ['门禁通过', 'local gate'],
    meaning: '本机工程门禁是否通过；不等于外部 / staging / 生产授权',
    domain: 'honesty',
    surfaces: ['gates', 'overview'],
  },
  {
    term: '诚实约束',
    aliases: ['honesty', '防误读'],
    meaning: '强制提示：分数/κ/门禁都是工程自检，不能当成准确率或对外发布证明',
    domain: 'honesty',
  },
  {
    term: 'process_split_authorized',
    aliases: ['process_split', '执行平面拆分授权'],
    meaning: '是否授权正式拆成独立生产执行平面；本机恒为 false',
    domain: 'honesty',
    surfaces: ['overview', 'scorecard', 'evidence'],
  },

  // ── execution plane ──────────────────────────────────────────────
  {
    term: 'upstream',
    aliases: ['上游', 'upstream mode'],
    meaning: '评测 Job 上游模式：proxy=已接到本机 :8010；cohost=未接通独立服务',
    domain: 'plane',
    surfaces: ['overview'],
  },
  {
    term: 'proxy',
    aliases: ['mode=proxy'],
    meaning: '本机 Job 平面已接通独立评测服务（:8010+worker），可 Enqueue',
    domain: 'plane',
  },
  {
    term: 'cohost',
    aliases: ['mode=cohost', '共宿'],
    meaning: '未接独立 eval 服务；Session/Arena/Skill 等 Job 不可用或需先起 proxy',
    domain: 'plane',
  },
  {
    term: '执行平面尚未迁移',
    aliases: ['B2', 'execution_not_migrated', '执行平面'],
    meaning:
      '产品上未签完正式拆分；本机能跑 Job 只代表本地联调，不是生产已迁移。≠ 某条 Job 的 runtime_tier=eval_worker；≠ Agent exam 已上 Worker',
    domain: 'plane',
  },
  {
    term: 'runtime_tier',
    aliases: ['运行时档位', '评测运行时', '实际执行面'],
    meaning:
      '单 job 实际执行面：fixture|pi|workspace_execute|core_skill_execute|eval_worker|external_pull；≠ target_runtime。多执行面用 runtime_parts[]，禁止异质压成单一值；见 runtime-tiers v1.4',
    domain: 'plane',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'target_runtime',
    aliases: ['目标交付形态'],
    meaning:
      '对象打算在哪交付/被评；可与本次 runtime_tier 不同（如 Pi 离线：tier=fixture · target=pi）',
    domain: 'plane',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'runtime_claim',
    aliases: ['runtime_claim_reason'],
    meaning:
      '本次结论是否可就实际 runtime_tier 范围作有限陈述；≠ accuracy/充分/发布认证；false 时必带 reason',
    domain: 'honesty',
    surfaces: ['agents'],
  },
  {
    term: 'workspace_execute',
    aliases: ['工作区 Execute'],
    meaning: 'Agent 正式 live 当前路径：run_workspace_agent + 真实 AgentInfo；≠ eval_worker',
    domain: 'plane',
    surfaces: ['agents'],
  },
  {
    term: 'core_skill_execute',
    aliases: ['Skill 执行档', 'skill_manager quality'],
    meaning:
      '实际经 Core skill_manager 调用被测 Skill（quality）；≠ fixture；≠ Agent workspace_execute',
    domain: 'plane',
    surfaces: ['overview'],
  },
  {
    term: 'external_pull',
    aliases: ['外部拉模式'],
    meaning: '外部 HTTP 拉对话评测档位；≠ 本机 Agent；≠ pi',
    domain: 'plane',
    surfaces: ['agents'],
  },
  {
    term: 'fixture',
    aliases: ['规则/dry-run 档', 'local_fixture', '预制用例', 'runtime_tier=fixture'],
    meaning:
      'runtime_tier=fixture：未加载/未调用被测对象（规则/dry-run/结构校验）或预制用例对账；target_runtime 仍可写目标形态；≠线上流量、≠准确率',
    domain: 'plane',
    surfaces: ['agents', 'overview', 'skill'],
  },
  {
    term: 'not_applicable',
    aliases: ['不适用', '契约不适用'],
    meaning:
      '对象契约/requires 不匹配；≠未测、≠失败；不得单独驱动综合不通过；维有 untested 时综合结论至多为有条件通过；见 formal_report v1.14（含claims_gate check-only）',
    domain: 'honesty',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'MatchReport',
    aliases: ['match_report', '适用性报告'],
    meaning:
      'eval.match_report.v1：入选/不适用原因；P2+ 冒烟按此筛题；正式报告 §2.1 强制披露',
    domain: 'honesty',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'Evaluation Plan',
    aliases: ['evaluation_plan', 'plan_id', '评测计划', 'compile-plan'],
    meaning:
      'eval.evaluation_plan.v1：契约→选题→runtime。Agent 冒烟：BUILTIN_EXAM_SUITE=题集模板，compile-plan=选题真相，失败阻断开跑。Plan 能选中≠题目已执行≠L5 校准',
    domain: 'honesty',
    surfaces: ['agents', 'overview'],
  },
  // ── object_contract maturity (SSOT: eval-object-contract §0.5) ──
  {
    term: '评测成熟度五级',
    aliases: ['L1-L5', '成熟度表', 'object maturity', '评测对象成熟度'],
    meaning:
      'Object Contract v1.0 锁定：L1入口→L2匹配→L3=版本化用例+oracle+可执行入口→L4=另有本次运行证据→L5=门槛满足后仅可作范围限定声明。禁止无入口称L3；未达L5不得作准确率声明',
    domain: 'object_contract',
    surfaces: ['agents', 'skills', 'apps', 'prompts', 'overview'],
  },
  {
    term: 'L1入口',
    aliases: ['成熟度L1', '有入口'],
    meaning: '有 Tab/API 入口即可；尚不能说「已评测」',
    domain: 'object_contract',
  },
  {
    term: 'L2计划匹配',
    aliases: ['成熟度L2', 'Plan能识别', '能编译匹配计划'],
    meaning: '能 compile-plan / MatchReport 入选或标 N/A；≠有可执行入口、≠有运行证据',
    domain: 'object_contract',
  },
  {
    term: 'L3题与判分',
    aliases: ['成熟度L3', '有实际题目与判分器', '可执行入口'],
    meaning:
      'AND：版本化用例 + 明确oracle/判分 + 可执行入口(Runner/API)。仅draft/JSON无入口→L2。≠自动等于与Agent同级产品',
    domain: 'object_contract',
  },
  {
    term: 'L4执行证据',
    aliases: ['成熟度L4', '有可复核的执行证据', '本次实际运行', '运行证据'],
    meaning:
      'L3之上另有本次运行可复核证据。运行证据/工程校准快照≠统计学校准；禁止称「已校准/准确率」',
    domain: 'object_contract',
  },
  {
    term: 'L5校准',
    aliases: ['成熟度L5', '充分性或准确性校准', '范围限定声明', '统计学校准'],
    meaning:
      '默认claim=false。须claims-gate门槛+explicit_authorize才可对限定对象版本×任务分布×运行条件×样本量声明；fixture/mixed/不完整覆盖不可解禁',
    domain: 'object_contract',
  },
  {
    term: '五态聚合',
    aliases: ['维度聚合', 'mergeMatrixStatuses', 'pass+untested', '适用态'],
    meaning:
      '适用态=pass/fail/untested/inconclusive，N/A非适用。有适用且全pass其余N/A→pass；无适用→N/A；零覆盖→untested；pass+untested→untested',
    domain: 'object_contract',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'runtime_parts',
    aliases: ['多执行面', '系统组合运行时', 'mixed runtime'],
    meaning:
      'system/多入口报告：各子任务自带 runtime_tier；异质时顶层不得压成单一实际档，可省略或标 mixed（非执行宿主）',
    domain: 'plane',
    surfaces: ['overview'],
  },
  {
    term: 'A维evaluates',
    aliases: ['evaluates', '用例包维度', 'A口径', '选题贡献维'],
    meaning:
      '用例/卷在 applicability 上声明的 evaluates[]：只说明「入选后贡献哪些维」；≠报告切片已出、≠本次已测',
    domain: 'object_contract',
    surfaces: ['agents', 'sets', 'overview'],
  },
  {
    term: 'B维报告切片',
    aliases: ['可归因切片', 'B口径', 'attributable slices'],
    meaning:
      'Agent 可归因报告工程信号（task_result/tools_trajectory/safety/…）；切片字段存在≠本 Plan 入选了对应卷、≠有足够证据',
    domain: 'object_contract',
    surfaces: ['agents', 'reports'],
  },
  {
    term: 'C维入口判分',
    aliases: ['C口径', '入口私有判分'],
    meaning:
      '各入口私有判分：Skill trigger TP/TN、Prompt expected_keys、Pi 结构断言等；≠统一平台维度表，不可与 A/B 合并宣称',
    domain: 'object_contract',
    surfaces: ['skills', 'prompts', 'apps'],
  },
  {
    term: 'object_type成熟度',
    aliases: [
      '评测对象成熟度表',
      'Agent成熟度',
      'Skill成熟度',
      'Prompt成熟度',
      'Workflow成熟度',
      'Model成熟度',
      'Dataset成熟度',
    ],
    meaning:
      '稳妥口径：Agent≈L4（未达L5）；Skill/API/生成应用有限定执行证据；Prompt/Workflow/Model/Dataset/System Plan链L3–L4；KB≠dataset。框架P0–P3≠对象同级完成；L5未宣称',
    domain: 'object_contract',
    surfaces: ['agents', 'skills', 'apps', 'prompts', 'knowledge', 'overview'],
  },
  {
    term: 'Prompt评测路径',
    aliases: ['prompt_eval', 'Prompts页', 'Prompt Plan', 'Prompt页面链', 'Prompt Plan链'],
    meaning:
      '分列：①页面链=L3–L4（DB用例+expected_keys+prompt_eval）；②Plan链=L3–L4（prompt/*+词面oracle+POST /evaluation/prompt-plan-exam）。禁止合并评级',
    domain: 'object_contract',
    surfaces: ['prompts'],
  },
  {
    term: '框架P0-P3接线',
    aliases: ['P0–P3已接线', 'Object Contract接线'],
    meaning:
      '仅指通用匹配、Plan编译、以及Agent/Skill/API/生成应用等部分执行适配已接线；≠Prompt/Workflow/Model/Dataset已有同等题库+Runner+证据。对象级以成熟度表逐项举证',
    domain: 'object_contract',
    surfaces: ['overview', 'agents'],
  },
  {
    term: '已登记匹配项',
    aliases: ['基础匹配项', 'applicability set', '三包已齐'],
    meaning:
      'applicability_draft 有 set 元数据=已登记匹配项（常含*/basic）；≠core/capability/special产品题包已齐，≠有可执行题卷与Runner。勿把「能匹配」写成「三包已齐」',
    domain: 'object_contract',
    surfaces: ['sets', 'overview'],
  },
  {
    term: 'Knowledge≠dataset',
    aliases: ['KB评测', 'kb_eval', '知识评测'],
    meaning:
      'Knowledge/KB 样本是检索/问答指标路径；≠通用 object_type=dataset 的 Plan 评测；盘点须分列',
    domain: 'object_contract',
    surfaces: ['knowledge'],
  },
  {
    term: 'eval_profile',
    aliases: ['eval_profile_source', '能力画像', 'derived_hints', 'profile_source'],
    meaning:
      '显式 eval_profile 优先。derived_hints=skills/tools 子串建议选题，须标来源/低置信；禁止仅凭派生悄悄排除用例或判 N/A；禁止按 agent_id 猜角色',
    domain: 'honesty',
    surfaces: ['agents'],
  },
  {
    term: 'pi',
    aliases: ['Pi 交付冒烟', 'runtime_tier=pi', 'target_runtime=pi', '厂外薄宿主'],
    meaning:
      'target_runtime=pi 表示目标交付；仅 live pi CLI 成功时 runtime_tier=pi·claim=true；offline/runs_eval→tier=fixture·claim=false',
    domain: 'plane',
    surfaces: ['overview'],
  },
  {
    term: 'skill_evals',
    aliases: ['Skill suite', '技能成果物评测'],
    meaning:
      'platform skill_evals：trigger→runtime_tier=fixture；quality→core_skill_execute（skill_manager 已调）；≠ Run 面板 skill_suite Job；≠ Agent exam',
    domain: 'plane',
    surfaces: ['overview'],
  },
  {
    term: 'Enqueue',
    aliases: ['Enqueue job', 'enqueue', '入队'],
    meaning: '把评测任务交给本机 worker 排队执行，并轮询 status',
    domain: 'plane',
    surfaces: ['session', 'arena', 'skill', 'research', 'knowledge', 'prompts', 'code-review'],
  },
  {
    term: 'tenant',
    aliases: ['tenant_id', 'eval-v1'],
    meaning: '评测租户隔离键；中心默认 eval-v1',
    domain: 'plane',
  },
  {
    term: 'sandbox',
    aliases: ['docker sandbox', '沙箱', 'AIPLAT_EVAL_SANDBOX_BACKEND'],
    meaning: '隔离执行后端；Skill 等需 docker；local_stub 不够跑 Skill',
    domain: 'plane',
    surfaces: ['skill'],
  },
  {
    term: 'docker',
    aliases: ['Docker', 'alpine:3.20'],
    meaning: '本机 Skill fixture 用的容器沙箱探针（network=none）；不真跑 live 工具',
    domain: 'plane',
    surfaces: ['skill'],
  },
  // ── tabs (Chinese labels users ask about) ────────────────────────
  {
    term: '总览',
    aliases: ['overview'],
    meaning: 'G2a 工程校准快照与快捷跳转；数字不是准确率',
    domain: 'tabs',
    surfaces: ['overview'],
  },
  {
    term: '复核',
    aliases: ['review'],
    meaning: '人工标定/裁决标签（G2a）；单人复核无 κ，不是准确率判定',
    domain: 'review',
    surfaces: ['review'],
  },

  // ── G2a overview / review ────────────────────────────────────────
  {
    term: 'G2a',
    aliases: ['工程校准'],
    meaning: '工程校准阶段：本地黄金集、人工复核与就绪快照；不是准确率认证',
    domain: 'g2a',
    surfaces: ['overview', 'review'],
  },
  {
    term: 'v0_locked',
    aliases: ['黄金集锁定', '黄金集锁定 v0', 'lock-v0'],
    meaning: '本地黄金集是否已锁定；工程锁，不是准确率，也不是外部 gate',
    domain: 'g2a',
    surfaces: ['overview', 'review', 'settings'],
  },
  {
    term: 'g2a_ready',
    aliases: ['校准就绪'],
    meaning: 'G2a 工程校准是否达到本地就绪条件',
    domain: 'g2a',
    surfaces: ['overview'],
  },
  {
    term: 'tasks',
    aliases: ['任务数', 'task_count', 'pack tasks'],
    meaning: '校准/题包任务数量（题目或用例条数）',
    domain: 'g2a',
    surfaces: ['overview', 'g2b'],
  },
  {
    term: 'adjudicated',
    aliases: ['已裁决', 'labels_adjudicated'],
    meaning: '已人工裁决条数（常显示为 已裁决/锁定目标）',
    domain: 'g2a',
    surfaces: ['overview', 'review'],
  },
  {
    term: 'pending',
    aliases: ['待复核', 'labels_pending', 'pending_dual_human'],
    meaning: '仍待人工处理的条数（复核或双人标注）',
    domain: 'g2a',
    surfaces: ['overview', 'review', 'g2b', 'preference'],
  },
  {
    term: 'sets / gates',
    aliases: ['评测集 / 门禁条数', 'setsGates'],
    meaning: '本地 store 中评测集条数 / 门禁记录条数',
    domain: 'g2a',
    surfaces: ['overview'],
  },
  {
    term: 'adjudicate',
    aliases: ['裁决', '复核裁决'],
    meaning: '人工确认/改写标签；属于标定，不是准确率判定',
    domain: 'review',
    surfaces: ['review'],
  },
  {
    term: 'preannotate',
    aliases: ['预标注'],
    meaning: '辅助预填标签，仍需人确认；不自动变成 accuracy',
    domain: 'review',
    surfaces: ['review'],
  },

  // ── sets / gates / reports ───────────────────────────────────────
  {
    term: '评测集',
    aliases: ['set', 'set_id', 'eval set'],
    meaning: '评测题目/样本集合；画面可新建 set/追加 task/导入黄金集；有集合 ≠ 模型已测准',
    domain: 'sets',
    surfaces: ['sets'],
  },
  {
    term: '门禁',
    aliases: ['gates', 'gate', 'gate_id', 'gate-e5', 'gate-g2a', 'calibrate-e4'],
    meaning: '本机工程「过不过」记录与动作；通过 ≠ 外部授权',
    domain: 'gates',
    surfaces: ['gates'],
  },
  {
    term: '对象Plan',
    aliases: ['typed-plan', 'typed plan exam', 'plan-exam', '对象 Plan'],
    meaning:
      '高级Tab：prompt/workflow/model/dataset/system Plan exam + claims_gate核对；≠页面Prompts；默认不解禁',
    domain: 'object_contract',
    surfaces: ['typed-plan'],
  },
  {
    term: '报告',
    aliases: ['reports', 'report_id', 'compare'],
    meaning: '已落库评测报告；同 composite_version 才宜对比；分数默认非 accuracy',
    domain: 'reports',
    surfaces: ['reports'],
  },
  {
    term: 'composite_version',
    aliases: ['composite', '评分合成版本'],
    meaning: '综合分版本号；跨版本分数不可直接比较',
    domain: 'reports',
    surfaces: ['reports'],
  },

  // ── G2b ──────────────────────────────────────────────────────────
  {
    term: 'G2b',
    aliases: ['dual-human', '双人盲标', 'closeout'],
    meaning: '双人盲标一致性收口；看人与人是否一致（κ），不是模型准确率',
    domain: 'g2b',
    surfaces: ['g2b'],
  },
  {
    term: 'pack_ready',
    aliases: ['题包就绪'],
    meaning: '发卷/题包材料是否就绪',
    domain: 'g2b',
    surfaces: ['g2b', 'preference'],
  },
  {
    term: 'closeout_n',
    aliases: ['n=100', 'scoped n'],
    meaning: '双人收口样本量（如 scoped n=100）；样本量齐 ≠ accuracy',
    domain: 'g2b',
    surfaces: ['g2b', 'scorecard'],
  },
  {
    term: 'dual_human_complete',
    aliases: ['双人完成'],
    meaning: '双人标注是否完成；完成只说明流程收口，不是准确率',
    domain: 'g2b',
    surfaces: ['g2b', 'preference'],
  },
  {
    term: 'pass_rate',
    aliases: ['G2b pass_rate'],
    meaning: '收口包通过率等工程汇总；不等于 accuracy_claim',
    domain: 'g2b',
    surfaces: ['g2b', 'scorecard'],
  },
  {
    term: 'runbook',
    aliases: ['操作手册路径'],
    meaning: '相关运维/收口文档路径提示，供人工对照',
    domain: 'g2b',
    surfaces: ['g2b', 'scorecard', 'evidence'],
  },

  // ── Preference ───────────────────────────────────────────────────
  {
    term: 'Preference',
    aliases: ['偏好', 'pairs'],
    meaning: '偏好对（A/B 哪边更好）汇总；偏好胜出 ≠ 准确率，也不替代 G2b',
    domain: 'preference',
    surfaces: ['preference'],
  },
  {
    term: 'pairs_n',
    aliases: ['偏好对数'],
    meaning: '偏好对（A/B）的数量，不是准确率样本数',
    domain: 'preference',
    surfaces: ['preference'],
  },
  {
    term: 'agreement',
    aliases: ['一致率'],
    meaning: '偏好标注一致程度；仍是人人一致性类指标，不是 accuracy',
    domain: 'preference',
    surfaces: ['preference'],
  },
  {
    term: 'fixture_solo',
    aliases: ['单人 fixture'],
    meaning: '单人/fixture 偏好路径；不能当成双人 κ',
    domain: 'preference',
    surfaces: ['preference'],
  },
  {
    term: 'labeled A / B',
    aliases: ['pending A / B'],
    meaning: '两侧标注员已标/待标数量',
    domain: 'preference',
    surfaces: ['preference'],
  },

  // ── Scorecard / Evidence / Worksheets ────────────────────────────
  {
    term: 'Scorecard',
    aliases: ['打分卡', 'attestation', 'axis', 'eligible', 'gaps'],
    meaning: '能力成熟度/证据是否齐的打分卡；高分或 eligible ≠ 准确率',
    domain: 'scorecard',
    surfaces: ['scorecard'],
  },
  {
    term: 'dual_human_attestation',
    aliases: ['双人签认'],
    meaning: '双人证据/签认状态；签认齐 ≠ accuracy_claim',
    domain: 'scorecard',
    surfaces: ['scorecard', 'evidence'],
  },
  {
    term: 'Evidence',
    aliases: ['证据', 'evidence audit', 'tracked hashes'],
    meaning: '证据树/清单是否齐全；齐全 ≠ 准确率',
    domain: 'evidence',
    surfaces: ['evidence'],
  },
  {
    term: 'feature5_audit_ready',
    aliases: ['feat5', 'required_for_feature_5_ok'],
    meaning: '功能维度 5 相关审计是否就绪；就绪 ≠ accuracy_claim',
    domain: 'evidence',
    surfaces: ['evidence'],
  },
  {
    term: 'attestation_ok',
    aliases: ['签认通过'],
    meaning: '签认检查是否通过（工程证据），不是准确率',
    domain: 'evidence',
    surfaces: ['evidence'],
  },
  {
    term: 'Worksheets',
    aliases: ['工作表', 'worksheet', '发卷'],
    meaning: '给人填的发卷/工作表；空白包本身不算 κ，也不算准确率',
    domain: 'worksheets',
    surfaces: ['worksheets'],
  },

  // ── G2c settings ─────────────────────────────────────────────────
  {
    term: 'G2c',
    aliases: ['设置', '自洽', 'g2c_ready'],
    meaning: '本地评测设置/自洽与复测；改设置不会把 accuracy_claim 变成 true',
    domain: 'g2c',
    surfaces: ['settings'],
  },
  {
    term: 'paired',
    aliases: ['配对状态'],
    meaning: 'G2c 自洽配对相关状态字段',
    domain: 'g2c',
    surfaces: ['settings'],
  },
  {
    term: 'retest_count',
    aliases: ['retest queue', '复测队列'],
    meaning: '复测队列条数/状态；复测仍是工程自检',
    domain: 'g2c',
    surfaces: ['settings'],
  },

  // ── runners ──────────────────────────────────────────────────────
  {
    term: 'Session',
    aliases: ['session_eval', '多轮对话'],
    meaning:
      '多轮对账冒烟：Enqueue 用预制 prompt/expected/actual（默认 2 轮口算）跑 session_eval；无真模型。succeeded≠对话 Agent 测准',
    domain: 'runners',
    surfaces: ['session'],
  },
  {
    term: 'Arena',
    aliases: ['arena', 'length_smoke', '长度烟雾', 'length_heuristic'],
    meaning: '双回答对比；默认比长短的烟雾测试，不是质量裁判，不打开质量门禁',
    domain: 'runners',
    surfaces: ['arena'],
  },
  {
    term: 'Skill',
    aliases: ['skill_suite', 'Skill 管道', '技能 fixture'],
    meaning:
      '技能 fixture + Docker 沙箱探针；Enqueue 默认 mode=fixture 不对真工具。成功≠工具能力认证；无 Docker 可能失败',
    domain: 'runners',
    surfaces: ['skill'],
  },
  {
    term: 'P2 Research',
    aliases: ['context_mgmt', 'memory_persist', 'self_learn', 'P2'],
    meaning: '上下文/记忆/自学习三项工程自检门；通过 ≠ 生产写回或自学习已授权',
    domain: 'runners',
    surfaces: ['research'],
  },
  {
    term: 'Code-review',
    aliases: ['code_review_gold', 'code_review', 'Run match-only'],
    meaning:
      '自检打分尺子：默认 match-only 用写死的假装评审结果对标准缺陷算 P/R（无 LLM、不跑评审 Agent、不读仓库）。为的是先保证计分管线可靠；≠测准模型/真项目。题在种子目录，≠评测集 Tab',
    domain: 'runners',
    surfaces: ['code-review'],
  },
  {
    term: 'Knowledge',
    aliases: ['kb_rag', '知识库评测'],
    meaning: '知识库检索类评测；样本空会失败；结果仍非 accuracy',
    domain: 'runners',
    surfaces: ['knowledge'],
  },
  {
    term: 'Prompts',
    aliases: ['prompt_eval'],
    meaning: 'Prompt 模板版本对比；A 高于 B ≠ 业务已验证准确',
    domain: 'runners',
    surfaces: ['prompts'],
  },
  {
    term: '评测 Agent',
    aliases: [
      '考 Agent',
      '历史分',
      'Agents',
      'agent suites',
      '历史分 / 脚手架',
      '从零开考',
      '正式评测',
      '8维',
      '完整评测',
    ],
    meaning:
      '成果物入口之一：命名工作区本机 Agent；框架=维度(8维+专项)/方法/结论；正式评测落工程分+可归因；覆盖≠充分；≠ Skill/生成应用/管道',
    domain: 'runners',
    surfaces: ['agents'],
  },
  {
    term: '外部拉模式',
    aliases: [
      '外部目标',
      'http_chat_pull',
      'ext:target',
      'external exam',
      '对话 HTTP 评测',
    ],
    meaning:
      'aiPlat 按试卷 POST 外部对话 HTTP；评 output_text，可选 IN_ORDER 工具序(v1 tool_calls)；结果 ext:{target_id}；≠ 副作用充分/准确率；accuracy_claim=false',
    domain: 'runners',
    surfaces: ['agents'],
  },
  {
    term: '评测框架三层',
    aliases: ['维度方法结论', '8维框架', '专项切片'],
    meaning:
      'Agent 报告叙事层：维/方法/结论。≠ Object Contract 的 A/B/C 口径；≠评测成熟度 L1–L5。覆盖描述≠充分性证明',
    domain: 'runners',
    surfaces: ['agents'],
  },
  {
    term: '评测 Skill',
    aliases: ['skills tab', 'skill_evals', 'Skill suite 成果物'],
    meaning:
      '成果物入口：已登记 Skill suite → platform skill_evals run/results；≠ 验管道「Skill 管道」fixture',
    domain: 'runners',
    surfaces: ['skills'],
  },
  {
    term: '评测生成应用',
    aliases: ['apps tab', 'runs_eval', '生成应用 Run'],
    meaning:
      '成果物入口：run_id → runs_eval latest/autoEvaluate；身份权威为 run_id；≠ Agent 历史分',
    domain: 'runners',
    surfaces: ['apps'],
  },
  {
    term: '生成评估代码',
    aliases: ['generate_agent_eval', '生成评估脚手架'],
    meaning:
      '对选中 agent_id 调用 POST /core/entropy/eval/generate：写 AGENT.md scoring_dimensions + ~/.aiplat/eval/{id}/eval_metric.py+eval_runner.py；已齐全则跳过。≠ Skill-eval suite / upsert_skill_eval_suite / 跑 Job',
    domain: 'runners',
    surfaces: ['agents'],
  },
  {
    term: '强制重生成',
    aliases: ['force regenerate', 'force=true'],
    meaning:
      '同上 generate_agent_eval(force=true)：覆盖已有维度与评估脚手架文件；仍不是 run_skill_eval_suite，也不等于模型准确率评测',
    domain: 'runners',
    surfaces: ['agents'],
  },
  {
    term: 'job status',
    aliases: ['queued', 'succeeded', 'failed', 'cancelled', 'status'],
    meaning: 'Job 队列状态：排队/成功/失败/取消；成功仍受诚实约束',
    domain: 'runners',
  },
  {
    term: 'quality_gate_eligible',
    aliases: ['质量门禁'],
    meaning: '是否允许当作质量门；Arena 默认 false',
    domain: 'runners',
    surfaces: ['arena'],
  },
  {
    term: 'tools_executed',
    aliases: ['live tools'],
    meaning: '是否真执行了工具；Skill fixture 路径应为 false',
    domain: 'runners',
    surfaces: ['skill'],
  },
];

/** Flatten canonical + aliases → meaning (for PageDataBridge / tests). */
export function flattenEvalGlossary(
  entries: EvalGlossEntry[] = EVAL_GLOSSARY,
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

/** Prompt pack for 小朱 (bounded). */
export function evalGlossaryPromptText(maxLen = 1600): string {
  const flat = flattenEvalGlossary();
  const text = Object.entries(flat)
    .map(([k, v]) => `${k}=${v}`)
    .join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

/** Domain coverage helper (tests / docs). */
export function evalGlossaryDomainCounts(): Record<EvalGlossDomain, number> {
  const counts = {} as Record<EvalGlossDomain, number>;
  for (const e of EVAL_GLOSSARY) {
    counts[e.domain] = (counts[e.domain] || 0) + 1;
  }
  return counts;
}
