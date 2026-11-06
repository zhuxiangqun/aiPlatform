/**
 * Compact Layer A glossary packs for 小朱 (pages that already reportPageData,
 * or high-consult routes). Keep meanings short; extend per-module files when dense.
 * See XIAOZHU.md §1.2–1.4.
 */

export type Gloss = { term: string; aliases?: string[]; meaning: string };

function pack(entries: Gloss[], maxLen = 1100): string {
  const parts: string[] = [];
  for (const e of entries) {
    parts.push(`${e.term}=${e.meaning}`);
    for (const a of e.aliases || []) parts.push(`${a}=${e.meaning}`);
  }
  const text = parts.join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

export const GOVERNANCE_GLOSSARY: Gloss[] = [
  { term: '治理仪表盘', aliases: ['/governance'], meaning: '策略/审批/合规健康总览；不是资产审批操作台本身' },
  { term: 'overall_health', aliases: ['整体健康'], meaning: '治理机制综合健康分或等级摘要' },
  { term: 'pending_approvals', aliases: ['待审批'], meaning: '等待处理的审批单数量；去 /approval 处理资产类' },
  { term: 'denied_calls', aliases: ['拒绝调用'], meaning: '今日被拒的受控调用次数（审计摘要）' },
  { term: 'mechanismsNeedingAttention', aliases: ['需关注机制'], meaning: '状态异常或需跟进的治理机制数' },
];

export const ALERTS_GLOSSARY: Gloss[] = [
  { term: '告警中心', aliases: ['/alerts'], meaning: '平台告警查看与分档；不代替修复中心' },
  { term: 'firingCritical', aliases: ['critical', '严重'], meaning: '正在触发的严重告警数' },
  { term: 'firingWarning', aliases: ['warning', '警告'], meaning: '正在触发的警告告警数' },
  { term: 'firingInfo', aliases: ['info'], meaning: '信息级告警数' },
  { term: 'activeTab', aliases: ['当前 Tab'], meaning: '告警中心当前查看的分栏' },
];

export const DIAGNOSTICS_GLOSSARY: Gloss[] = [
  { term: '诊断概览', aliases: ['/diagnostics'], meaning: '健康检查与诊断入口；点具体工具进子页' },
  { term: 'layerStatus', aliases: ['分层健康'], meaning: '各层健康状态摘要' },
  { term: 'unhealthyLayers', aliases: ['不健康层'], meaning: '当前不健康的分层名单' },
  { term: 'guardResult', aliases: ['架构守卫'], meaning: '架构守卫本轮 PASS/FAIL 摘要' },
  { term: 'diagRunId', aliases: ['诊断运行'], meaning: '统一诊断任务 run id（若有）' },
];

export const RUNS_GLOSSARY: Gloss[] = [
  { term: '运行记录', aliases: ['/diagnostics/runs'], meaning: 'Agent/Skill 运行历史与事件流；含失败摘要' },
  { term: 'runId', aliases: ['运行 ID'], meaning: '当前查看的运行标识' },
  { term: 'runStatus', aliases: ['运行状态'], meaning: '该次运行状态（成功/失败/进行中等）' },
  { term: 'eventCount', aliases: ['事件数'], meaning: '本运行事件条数' },
  { term: 'eventKinds', aliases: ['事件类型'], meaning: '事件 kind 汇总，不含完整 I/O' },
];

export const OBSERVABILITY_GLOSSARY: Gloss[] = [
  { term: '可观测性', aliases: ['/diagnostics/observability'], meaning: '指标/LLM/错误聚合看板' },
  { term: 'activeRuns', aliases: ['活跃运行'], meaning: '当前活跃运行数' },
  { term: 'llmCalls', aliases: ['LLM 调用'], meaning: 'LLM 调用计数摘要' },
  { term: 'llmErrorRate', aliases: ['LLM 错误率'], meaning: 'LLM 调用错误率；不是模型 accuracy' },
  { term: 'topErrors', aliases: ['高频错误'], meaning: 'Top 错误类型摘要' },
];

export const ONTOLOGY_GLOSSARY: Gloss[] = [
  { term: '本体编辑器', aliases: ['/ontology-editor', 'ontology'], meaning: '高级 YAML 域本体编辑；日常可走「从文档生成」' },
  { term: 'domainCount', aliases: ['域数量'], meaning: '已加载域个数' },
  { term: 'selectedDomain', aliases: ['当前域'], meaning: '编辑器当前选中的 domain_id' },
  { term: 'classCount', aliases: ['类数量'], meaning: '当前域类/实体类型数' },
  { term: 'hasSchema', aliases: ['有 schema'], meaning: '当前域是否已载入 schema' },
];

export const PRODUCTION_DEPTH_GLOSSARY: Gloss[] = [
  { term: '生产深度', aliases: ['/diagnostics/production-depth'], meaning: '生产深度+架构健康自检（反思/Docker/向量/契约等）' },
  { term: 'itemNames', aliases: ['检查项'], meaning: '各检查项 id:status 摘要' },
  { term: '刷新', aliases: ['重新检查'], meaning: '重新拉取生产深度检查结果' },
];

export const SESSIONS_GLOSSARY: Gloss[] = [
  { term: '会话管理', aliases: ['/app/sessions'], meaning: '跨渠道用户对话会话列表与结束；不是工作区 Agent 编辑页' },
  { term: 'active', aliases: ['活跃'], meaning: '会话仍在进行，可结束' },
  { term: 'ended', aliases: ['已结束'], meaning: '会话已正常结束' },
  { term: 'timeout', aliases: ['超时'], meaning: '会话因超时结束' },
  { term: 'channel_type', aliases: ['渠道'], meaning: '会话来源渠道（Telegram/Slack/WebChat/API/微信等）' },
  { term: 'message_count', aliases: ['消息数'], meaning: '该会话累计消息条数' },
  { term: '结束会话', aliases: ['end session'], meaning: '将活跃会话标记为结束；不删除历史' },
];

export const APPROVAL_GLOSSARY: Gloss[] = [
  { term: '资产审批', aliases: ['/approval'], meaning: 'Agent/Skill/Tool/MCP 等资产通过与上架；工作区「待审核」在此处理' },
  { term: '通过', aliases: ['approve', 'published'], meaning: '审批通过 → 通常变为已发布；上架另一步' },
  { term: '上架', aliases: ['list', 'listed'], meaning: '已发布后再上架 → listed，可供选用' },
  { term: '驳回', aliases: ['reject'], meaning: '驳回待审核资产，退回修改' },
  { term: 'ready', aliases: ['待审核队列'], meaning: '已提交、等待本页处理的资产' },
  { term: '运行时审批', aliases: ['/core/approvals', 'HITL'], meaning: '执行中人审，不是资产上架审批' },
];

export const governanceGlossaryText = () => pack(GOVERNANCE_GLOSSARY);
export const alertsGlossaryText = () => pack(ALERTS_GLOSSARY);
export const diagnosticsGlossaryText = () => pack(DIAGNOSTICS_GLOSSARY);
export const runsGlossaryText = () => pack(RUNS_GLOSSARY);
export const observabilityGlossaryText = () => pack(OBSERVABILITY_GLOSSARY);
export const ontologyGlossaryText = () => pack(ONTOLOGY_GLOSSARY);
export const productionDepthGlossaryText = () => pack(PRODUCTION_DEPTH_GLOSSARY);
export const approvalGlossaryText = () => pack(APPROVAL_GLOSSARY);
export const sessionsGlossaryText = () => pack(SESSIONS_GLOSSARY);
