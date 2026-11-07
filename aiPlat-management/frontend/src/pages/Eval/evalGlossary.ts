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
 *
 * ## Maintenance rule
 * - Adding a user-visible Eval label or metric → add/update an entry **in the same change**.
 * - Prefer extending this file over patching answers in chat.
 * - Aliases (中文标签 / 英文 key) go on the same entry.
 * - Do not invent accuracy/production claims in `meaning`.
 * - Do not put long tutorials or design-vision here (those belong in B docs).
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
  | 'tabs';

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
    meaning: '是否宣称「模型准确率」；评测中心本地必须为 false，跑通 Job 也不等于测准',
    domain: 'honesty',
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
      '本次实际执行面（归档主键）：fixture|pi|workspace_execute|core_skill_execute|eval_worker|external_pull；≠ target_runtime；见 eval-exam-runtime-tiers.md v1.3',
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
    aliases: ['规则/dry-run 档'],
    meaning:
      '实际未加载、未调用被测对象（规则/dry-run/结构校验）；target_runtime 仍可写目标形态',
    domain: 'plane',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'not_applicable',
    aliases: ['不适用', '契约不适用'],
    meaning:
      '对象契约/requires 不匹配；≠未测、≠失败；不得单独驱动综合不通过；见 formal_report v1.12',
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
    aliases: ['evaluation_plan', 'plan_id', '评测计划'],
    meaning:
      'eval.evaluation_plan.v1：契约→选题→runtime；冒烟 UI 以 Plan 为选题真相（模板=内置卷）；正式报告披露 plan_id 与三包覆盖；≠充分/准确认证',
    domain: 'honesty',
    surfaces: ['agents', 'overview'],
  },
  {
    term: 'eval_profile',
    aliases: ['eval_profile_source', '能力画像', 'derived_hints'],
    meaning:
      'Agent 评测契约：显式 config.eval_profile 优先；否则 skills/tools 子串 derived_hints；禁止按 agent_id 猜角色',
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
  {
    term: 'fixture',
    aliases: ['local_fixture', '预制用例'],
    meaning: '预制用例对账，验证链路/门禁；不是真实线上流量，也不等于准确率',
    domain: 'plane',
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
      '第1层评测维度(8维+记忆长程/评测集可靠性/失败可观测/线上体验)；第2层方法；第3层结论(覆盖范围/置信度/失败证据/veto/适用环境)。产品现状=覆盖描述≠充分性证明',
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
