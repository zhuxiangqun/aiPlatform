/**
 * Layer A 加深路由名单（与 XIAOZHU.md §1.4 对齐）。
 * CI：consultantLayerACoverage.test.ts 断言每条路由在源码中有 reportPageData(route)。
 *
 * 分级：
 * - deep：必须 reportPageData + guideGlossary（科目密集 / 易假阴性）
 * - purpose_only：仅 PAGE_PURPOSE（全菜单已有门禁）；禁止顾问宣称「功能不存在」类绝对句时应依赖未上报说明
 */
export type LayerADeepRoute = {
  route: string;
  /** 人类可读；写入文档 */
  label: string;
  /** 期望出现 reportPageData 的文件 glob 提示（测试只校验字符串存在） */
  hint?: string;
};

/** §1.4 加深覆盖 — 新增高频页必须同步本表 + XIAOZHU.md */
export const LAYER_A_DEEP_ROUTES: LayerADeepRoute[] = [
  { route: '/eval', label: '评测中心' },
  { route: '/workspace/agents', label: 'Agent' },
  { route: '/workspace/skills', label: 'Skill' },
  { route: '/workspace/tools', label: 'Tool' },
  { route: '/workspace/mcp', label: 'MCP' },
  { route: '/app/factory', label: '应用工厂' },
  { route: '/infra/models', label: '模型管理' },
  { route: '/governance', label: '治理仪表盘' },
  { route: '/alerts', label: '告警中心' },
  { route: '/diagnostics', label: '诊断概览' },
  { route: '/diagnostics/fde', label: 'FDE 工作台', hint: 'fdeGlossary + 新建客户' },
  { route: '/diagnostics/runs', label: '运行记录' },
  { route: '/diagnostics/observability', label: '可观测性' },
  { route: '/diagnostics/production-depth', label: '生产深度' },
  { route: '/diagnostics/evolution-status', label: '自进化状态', hint: 'EvolutionStatus.tsx' },
  { route: '/ontology-editor', label: '本体编辑器（可重定向到 knowledge/business?tab=editor）' },
  { route: '/approval', label: '资产审批' },
  { route: '/app/sessions', label: '会话管理' },
  // 存量回填：易与 FDE/租户混淆的高频页
  { route: '/knowledge/business', label: '业务说明书', hint: 'BusinessOntologyShell' },
  { route: '/knowledge/library', label: '知识库', hint: 'KnowledgeLibraryShell' },
  { route: '/org/pilot', label: '组织试点', hint: 'OrgPilotPage；≠ FDE 客户 Profile' },
];

export const LAYER_A_DEEP_ROUTE_PATHS: string[] = LAYER_A_DEEP_ROUTES.map((r) => r.route);
