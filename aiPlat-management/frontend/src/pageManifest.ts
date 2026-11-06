import {
  Activity, AlertTriangle, BarChart3, Bell, BookOpen, Bot, Box, Brain,
  Code, Cpu, Database, FileText, Flame, FolderGit, FolderOpen,
  GitBranch, HardDrive, History, Key, Layers, LayoutDashboard, Link,
  ListOrdered, MessageSquare, Monitor, Network, Package, Palette,
  PenTool, Play, Plug, Rocket, Search, Server, Settings, Share2,
  Shield, ShoppingBag, Sparkles, Terminal, TrendingUp, Users, Wrench,
  type LucideIcon,
} from 'lucide-react';

// ─── Shared types ────────────────────────────────────────────────────

export interface MenuItem {
  key: string;
  icon?: LucideIcon;
  label: string;
  subLabel?: string;
  roles?: string[];  // 显式可见角色，缺省时继承 group 级权限
}

export interface MenuGroup {
  group: string;
  label: string;
  items: MenuItem[];
}

export type MenuEntry = MenuItem | { divider: boolean } | MenuGroup;

export interface PageMeta {
  label: string;
  group: string;
  groupLabel: string;
  /** One-line purpose for 小朱 consultant context. */
  purpose?: string;
}

// ─── Sidebar menu structure v2.1 — task-flow driven ─────────────────


export const menuItems: MenuEntry[] = [
  // ════════════════════════════════════════════════════════════════
  // 仪表盘
  // ════════════════════════════════════════════════════════════════
  { group: 'dashboard', label: '📊 仪表盘', items: [
    { key: '/system-overview', icon: Activity, label: '系统概览' },
    { key: '/org/pilot', icon: Users, label: '组织试点', roles: ['admin', 'developer', 'operator', 'business', 'fde', 'approver'] },
    { key: '/alerts', icon: Bell, label: '告警中心' },
    { key: '/system-graph', icon: Share2, label: '系统图谱' },
    { key: '/governance', icon: Shield, label: '治理仪表盘' },
    { key: '/value-center', icon: BarChart3, label: '价值看板' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 知识（双轨：业务本体 | 知识库）
  // ════════════════════════════════════════════════════════════════
  { group: 'knowledge', label: '🧠 知识', items: [
    { key: '/knowledge/business', icon: Box, label: '业务说明书' },
    { key: '/knowledge/library', icon: Database, label: '知识库' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 评测（与「知识 / AI 应用工厂」平级；统一入口 /eval；旧 diagnostics/eval 已硬切）
  // ════════════════════════════════════════════════════════════════
  { group: 'eval', label: '📈 评测', items: [
    { key: '/eval', icon: BarChart3, label: '评测中心' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // AI 应用工厂（精简到项目生命周期 + 工作区能力）
  // ════════════════════════════════════════════════════════════════
  { group: 'build', label: '🤖 AI 应用工厂', items: [
    // ── 应用生命周期 ──
    { key: '_sub_lifecycle', subLabel: '📦 应用生命周期' },
    { key: '/app/factory', icon: FolderOpen, label: '应用工厂' },
    { key: '/app/apps', icon: Rocket, label: '已部署应用' },
    { key: '/diagnostics/fde', icon: Wrench, label: 'FDE 工作台' },
    // ── 工作区能力 ──
    { key: '_sub_workspace_ctrl', subLabel: '🧩 工作区能力' },
    { key: '/workspace/agents', icon: Bot, label: 'Agent' },
    { key: '/workspace/skills', icon: Sparkles, label: 'Skill' },
    { key: '/workspace/tools', icon: Wrench, label: 'Tool' },
    { key: '/workspace/mcp', icon: Plug, label: 'MCP' },
    { key: '/core/workflows', icon: GitBranch, label: 'Workflow' },
    { key: '/workspace/teams', icon: Users, label: 'Teams' },
    { key: '/workspace/marketplace', icon: ShoppingBag, label: '能力市场' },
    // ── 配置 ──
    { key: '_sub_runtime', subLabel: '⚙️ 配置' },
    { key: '/core/prompts', icon: FileText, label: '提示词配置' },
    { key: '/core/variables', icon: PenTool, label: '变量管理' },
    { key: '/core/credentials', icon: Key, label: '凭证管理' },
    // ── 开发辅助 ──
    { key: '_sub_devtools', subLabel: '🛠️ 开发辅助' },
    { key: '/diagnostics/code-intel', icon: Code, label: '代码智能', roles: ['admin','developer','fde'] },
    { key: '/diagnostics/browser-test', icon: Monitor, label: '浏览器测试', roles: ['admin','developer','fde'] },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 诊断与治理（仅 per-project）
  // ════════════════════════════════════════════════════════════════
  { group: 'diagnostics', label: '🩺 诊断与治理', items: [
    // ── 概览与监控 ──
    { key: '_sub_overview', subLabel: '概览与监控' },
    { key: '/diagnostics', icon: Activity, label: '诊断概览' },
    { key: '/diagnostics/control-profile', icon: Cpu, label: '控制画像' },
    { key: '/diagnostics/observability', icon: Monitor, label: '可观测性' },
    { key: '/diagnostics/production-depth', icon: Shield, label: '生产深度', roles: ['admin','developer','operator'] },
    // ── 排查与追踪 ──
    { key: '_sub_troubleshoot', subLabel: '排查与追踪' },
    { key: '/diagnostics/traces', icon: Network, label: '链路追踪' },
    { key: '/diagnostics/runs', icon: FileText, label: '运行记录' },
    { key: '/diagnostics/run-comparison', icon: BarChart3, label: '运行对比' },
    { key: '/diagnostics/llm-review', icon: Search, label: 'LLM 审查' },
    // ── 项目维护 ──
    { key: '_sub_maintain', subLabel: '项目维护' },
    { key: '/diagnostics/repairs', icon: Wrench, label: '修复中心' },
    { key: '/diagnostics/business-value', icon: TrendingUp, label: '业务价值' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 平台设置
  // ════════════════════════════════════════════════════════════════
  { group: 'platform', label: '⚙️ 平台设置', items: [
    // ── 监控与运维 ──
    { key: '_sub_ops', subLabel: '监控与运维' },
    { key: '/infra/monitoring', icon: Monitor, label: '监控面板', roles: ['admin','operator'] },
    { key: '/infra/llm-stats', icon: Share2, label: 'LLM 路由监控', roles: ['admin','operator'] },
    { key: '/diagnostics/routing-dashboard', icon: Share2, label: '路由仪表盘' },
    { key: '/diagnostics/routing-replay', icon: Play, label: '路由回放' },
    { key: '/diagnostics/policy-debug', icon: Search, label: '策略调试', roles: ['admin','developer'] },
    { key: '/diagnosis', icon: Search, label: '诊断产品' },
    { key: '/infra/nodes', icon: Server, label: '节点管理', roles: ['admin','operator'] },
    { key: '/infra/services', icon: Layers, label: '服务管理', roles: ['admin','operator'] },
    { key: '/infra/network', icon: Network, label: '网络管理', roles: ['admin','operator'] },
    { key: '/core/jobs', icon: ListOrdered, label: '任务管理', roles: ['admin','developer','operator'] },
    { key: '/infra/models', icon: Cpu, label: '模型管理' },
    { key: '/diagnostics/model-playground', icon: Cpu, label: '模型演练场', roles: ['admin','developer','fde'] },
    { key: '/diagnostics/model-audit', icon: Shield, label: '模型审计', roles: ['admin'] },
    { key: '/infra/finetune', icon: Wrench, label: '模型微调' },
    { key: '/infra/storage', icon: Database, label: '存储管理' },
    { key: '/infra/scheduler', icon: HardDrive, label: '算力调度' },
    // ── 能力配置 ──
    { key: '_sub_engine_cfg', subLabel: '🧬 能力配置' },
    { key: '/core/agents', icon: Bot, label: '引擎 Agent' },
    { key: '/core/skills', icon: Sparkles, label: '引擎 Skill' },
    { key: '/core/tools', icon: Wrench, label: '引擎 Tool' },
    { key: '/core/mcp', icon: Plug, label: '引擎 MCP' },
    // Workflow 属于应用编排（工作区能力），不是引擎内置原子能力 —— 不挂在此
    { key: '/core/memory', icon: Brain, label: 'Memory' },
    { key: '/core/checkpoints', icon: History, label: '文件 Checkpoint' },
    // ── 接入配置 ──
    { key: '_sub_config', subLabel: '接入配置' },
    { key: '/platform/gateway', icon: Network, label: 'API 网关' },
    { key: '/platform/auth', icon: Shield, label: '认证鉴权' },
    { key: '/platform/tenant', icon: Users, label: '多租户管理' },
    { key: '/app/channels', icon: MessageSquare, label: '渠道管理' },
    { key: '/app/sessions', icon: MessageSquare, label: '会话管理' },
    // ── 系统维护 ──
    { key: '_sub_sysops', subLabel: '系统维护' },
    { key: '/onboarding', icon: Settings, label: '初始化向导' },
    { key: '/pentest', icon: Shield, label: '渗透测试' },
    { key: '/releases', icon: Rocket, label: '版本管理' },
    { key: '/core/learning/releases', icon: Rocket, label: '发布管理' },
    { key: '/core/skills-rollouts', icon: Share2, label: '技能发布' },
    { key: '/core/skill-packs', icon: Package, label: '技能包' },
    { key: '/core/learning/artifacts', icon: BookOpen, label: '学习产出' },
    { key: '/governance/capabilities', icon: Cpu, label: '核心能力管理', roles: ['admin','developer'] },
    // ── 安全与合规 ──
    { key: '_sub_security', subLabel: '安全与合规' },
    { key: '/diagnostics/safety', icon: Shield, label: '安全监控' },
    { key: '/diagnostics/audit', icon: FileText, label: '审计日志' },
    { key: '/diagnostics/change-control', icon: Shield, label: '变更控制' },
    { key: '/diagnostics/capability-boundary', icon: AlertTriangle, label: '能力边界', roles: ['admin','developer','fde'] },
    { key: '/diagnostics/capability-policy', icon: Settings, label: '能力策略', roles: ['admin','developer','fde'] },
    { key: '/approval', icon: Package, label: '资产审批' },
    { key: '/approval/history', icon: FileText, label: '审批记录' },
    { key: '/core/approvals', icon: Shield, label: '运行时审批' },
    // ── 高级工具 (默认折叠) ──
    { key: '_sub_advanced', subLabel: '🔬 高级工具' },
    { key: '/diagnostics/syscalls', icon: Terminal, label: '系统调用' },
    { key: '/diagnostics/policies', icon: FileText, label: '策略管理' },
    { key: '/diagnostics/exec-backends', icon: Cpu, label: '执行后端', roles: ['admin','developer','operator'] },
    { key: '/diagnostics/context', icon: Layers, label: '上下文分析' },
    { key: '/diagnostics/links', icon: Link, label: '依赖关系' },
    { key: '/diagnostics/graphs', icon: Share2, label: '知识图谱' },
    { key: '/diagnostics/repo', icon: FolderGit, label: '仓库分析' },
    { key: '/diagnostics/smoke', icon: Flame, label: '冒烟测试', roles: ['admin','operator'] },
    { key: '/diagnostics/workflows', icon: GitBranch, label: '工作流诊断' },
    { key: '/diagnostics/ops', icon: Settings, label: '运维诊断' },
    { key: '/diagnostics/capability-graph', icon: Share2, label: '能力图谱' },
  ]},
  { group: 'help', label: '📖 帮助', items: [
    { key: '/docs', icon: BookOpen, label: '文档系统' },
  ]},
];

// ─── Page lookup ─────────────────────────────────────────────────────

const _pageCache = new Map<string, PageMeta>();

export function getPageInfo(path: string): PageMeta | null {
  const cached = _pageCache.get(path);
  if (cached) return cached;

  for (const entry of menuItems) {
    if (!('group' in entry)) continue;
    const group0 = entry as MenuGroup;
    for (const item of group0.items) {
      if (item.subLabel) continue; // skip section headers
      const itemKey = item.key.split('?')[0]; // strip query params
      if (path.startsWith(itemKey) || path === itemKey) {
        const meta: PageMeta = {
          label: item.label,
          group: group0.group,
          groupLabel: group0.label.replace(/^[^\s]+\s/, ''), // strip emoji prefix
          purpose: PAGE_PURPOSE[itemKey],
        };
        _pageCache.set(path, meta);
        return meta;
      }
    }
  }

  // Fallback: try parent paths (e.g. /diagnostics/fde/123 → /diagnostics/fde)
  const segments = path.split('/');
  while (segments.length > 1) {
    segments.pop();
    const parent = segments.join('/') || '/';
    const parentMeta = _pageCache.get(parent);
    if (parentMeta) {
      _pageCache.set(path, parentMeta);
      return parentMeta;
    }
    for (const entry of menuItems) {
      if (!('group' in entry)) continue;
      const group0 = entry as MenuGroup;
      for (const item of group0.items) {
        if (item.subLabel) continue;
        const itemKey = item.key.split('?')[0];
        if (parent.startsWith(itemKey) || parent === itemKey) {
          const meta: PageMeta = {
            label: item.label,
            group: group0.group,
            groupLabel: group0.label.replace(/^[^\s]+\s/, ''),
            purpose: PAGE_PURPOSE[itemKey],
          };
          _pageCache.set(path, meta);
          _pageCache.set(parent, meta);
          return meta;
        }
      }
    }
  }

  return null;
}

// ─── All pages flat list (for documentation/wiki generation) ─────────

export interface PageEntry {
  route: string;
  label: string;
  group: string;
  groupLabel: string;
}

export function getAllPages(): PageEntry[] {
  const pages: PageEntry[] = [];
  for (const entry of menuItems) {
    if (!('group' in entry)) continue;
    const group0 = entry as MenuGroup;
    const groupLabel = group0.label.replace(/^[^\s]+\s/, '');
    for (const item of group0.items) {
      if (item.subLabel) continue;
      pages.push({
        route: item.key.split('?')[0],
        label: item.label,
        group: group0.group,
        groupLabel,
      });
    }
  }
  return pages;
}

/** One-line screen purpose for digital-human brief (小朱). Keep values single-quoted in spirit for TS parser. */
export const PAGE_PURPOSE: Record<string, string> = {
  '/system-overview': '平台总览与健康入口',
  '/org/pilot': '组织试点：试点组织与落地进度',
  '/alerts': '告警中心：平台告警查看与处理',
  '/system-graph': '系统图谱：能力与依赖关系总览',
  '/governance': '治理仪表盘：策略、审批与合规概况',
  '/value-center': '价值看板：业务价值与收益度量',
  '/knowledge/business': '业务说明书：域本体与业务知识',
  '/knowledge/library': '知识库：Wiki/文档集合管理与检索',
  '/eval': '评测中心：本机校准与 Session/Arena/Skill 等 Job 联调；分数/κ/门禁≠准确率或对外发布',
  '/app/factory': '应用工厂：从需求到可部署应用的整条流水线',
  '/app/apps': '已部署应用列表与运行入口',
  '/diagnostics/fde': 'FDE 交付工作台：诊断、证据与签收',
  '/workspace/agents': '应用库 Agent：注册与执行平台内角色，不是整条工厂流水线',
  '/workspace/skills': 'Skill 库：可复用动作与 SOP',
  '/workspace/tools': 'Tool 库：原子操作与脚本',
  '/workspace/mcp': 'MCP 接入：外部工具服务',
  '/core/workflows': 'Workflow：多阶段编排定义与管理',
  '/workspace/teams': 'Teams：默认团队与阶段编排配置',
  '/workspace/marketplace': '能力市场：可安装能力浏览（非远端应用商店替代审批）',
  '/core/prompts': '提示词配置：模板与版本',
  '/core/variables': '变量管理：运行时/环境变量',
  '/core/credentials': '凭证管理：密钥与凭据（勿在对话中回显密文）',
  '/diagnostics/code-intel': '代码智能：仓库与符号分析',
  '/diagnostics/browser-test': '浏览器测试：UI 自动化冒烟',
  '/diagnostics': '诊断概览：健康检查与诊断入口',
  '/diagnostics/control-profile': '控制画像：ControlProfile 与工具白名单',
  '/diagnostics/observability': '可观测性：指标/日志/链路聚合',
  '/diagnostics/production-depth': '生产深度+架构健康（反思/Docker/事件/向量/契约 + Policy/旁路/plan_execute/Router/CRAG/Autonomous）',
  '/diagnostics/traces': '链路追踪：请求与执行轨迹',
  '/diagnostics/runs': '运行记录：Agent/Skill 运行历史与失败摘要',
  '/diagnostics/run-comparison': '运行对比：两次运行差异',
  '/diagnostics/llm-review': 'LLM 审查：模型输出审查记录',
  '/diagnostics/repairs': '修复中心：缺陷修复与跟踪',
  '/diagnostics/business-value': '业务价值：诊断侧价值度量',
  '/infra/monitoring': '监控面板：基础设施监控',
  '/infra/llm-stats': 'LLM 路由监控：调用与路由统计',
  '/diagnostics/routing-dashboard': '路由仪表盘：选模/路由决策可视化',
  '/diagnostics/routing-replay': '路由回放：历史路由决策回放',
  '/diagnostics/policy-debug': '策略调试：PolicyGate 调试',
  '/diagnosis': '诊断产品：独立诊断应用入口',
  '/infra/nodes': '节点管理：计算节点',
  '/infra/services': '服务管理：进程与服务状态',
  '/infra/network': '网络管理：端口与网络映射',
  '/core/jobs': '任务管理：后台任务与队列',
  '/infra/models': '模型目录与选模（purpose → unified_pipeline）',
  '/diagnostics/model-playground': '模型演练场：试调用与对比',
  '/diagnostics/model-audit': '模型审计：模型使用审计',
  '/infra/finetune': '模型微调：SFT/适配器训练入口',
  '/infra/storage': '存储管理：对象/本地存储',
  '/infra/scheduler': '算力调度：GPU/算力分配',
  '/core/agents': '引擎 Agent：core 引擎侧 Agent（非工作区应用库）',
  '/core/skills': '引擎 Skill：core 引擎侧 Skill（非工作区应用库）',
  '/core/tools': '引擎 Tool：core 引擎侧 Tool（非工作区应用库）',
  '/core/mcp': '引擎 MCP：core 引擎侧 MCP（非工作区应用库）',
  '/core/memory': 'Memory：记忆子系统查看',
  '/core/checkpoints': '文件 Checkpoint：工作区检查点',
  '/platform/gateway': 'API 网关：路由与限流入口',
  '/platform/auth': '认证鉴权：登录/MFA/令牌',
  '/platform/tenant': '多租户管理：租户与隔离',
  '/app/channels': '渠道管理：对外消息渠道',
  '/app/sessions': '会话管理：用户会话列表',
  '/onboarding': '初始化向导：平台首次配置',
  '/pentest': '渗透测试：安全测试工具箱',
  '/releases': '版本管理：发布版本',
  '/core/learning/releases': '发布管理：学习/发布流水',
  '/core/skills-rollouts': '技能发布：Skill 滚动发布',
  '/core/skill-packs': '技能包：Skill Pack 打包与分发',
  '/core/learning/artifacts': '学习产出：学习产物浏览',
  '/governance/capabilities': '核心能力管理：能力登记与边界',
  '/diagnostics/safety': '安全监控：安全事件与告警',
  '/diagnostics/audit': '审计日志：操作审计',
  '/diagnostics/change-control': '变更控制：变更单与门禁',
  '/diagnostics/capability-boundary': '能力边界：边界违规与守卫',
  '/diagnostics/capability-policy': '能力策略：能力启用策略',
  '/approval': '资产审批：Agent/Skill 等资产通过与上架',
  '/approval/history': '审批记录：历史审批单',
  '/core/approvals': '运行时审批：执行中 HITL 审批',
  '/diagnostics/syscalls': '系统调用：syscall 观测',
  '/diagnostics/policies': '策略管理：策略条目',
  '/diagnostics/exec-backends': '执行后端：执行后端配置',
  '/diagnostics/context': '上下文分析：注入层与预算',
  '/diagnostics/links': '依赖关系：模块依赖',
  '/diagnostics/graphs': '知识图谱：图谱浏览',
  '/diagnostics/repo': '仓库分析：代码仓分析',
  '/diagnostics/smoke': '冒烟测试：一键冒烟',
  '/diagnostics/workflows': '工作流诊断：编排诊断',
  '/diagnostics/ops': '运维诊断：运维检查',
  '/diagnostics/capability-graph': '能力图谱：能力关系图',
  '/docs': '文档系统：平台文档浏览',
  '/diagnostics/doctor': '一键诊断与运行时健康',
  '/ontology-editor': '本体编辑器：高级 YAML 域本体编辑（日常可走从文档生成）',
};
