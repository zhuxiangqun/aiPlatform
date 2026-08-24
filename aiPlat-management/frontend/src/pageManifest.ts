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
}

// ─── Sidebar menu structure v2.1 — task-flow driven ─────────────────


export const menuItems: MenuEntry[] = [
  // ════════════════════════════════════════════════════════════════
  // 仪表盘
  // ════════════════════════════════════════════════════════════════
  { group: 'dashboard', label: '📊 仪表盘', items: [
    { key: '/system-overview', icon: Activity, label: '系统概览' },
    { key: '/alerts', icon: Bell, label: '告警中心' },
    { key: '/system-graph', icon: Share2, label: '系统图谱' },
    { key: '/governance', icon: Shield, label: '治理仪表盘' },
    { key: '/value-center', icon: BarChart3, label: '价值看板' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 知识工厂
  // ════════════════════════════════════════════════════════════════
  { group: 'knowledge', label: '🧠 知识工厂', items: [
    { key: '_sub_kb_factory', subLabel: '🏭 知识生产' },
    { key: '/knowledge-factory', icon: Brain, label: '知识工厂' },
    { key: '_sub_kb_source', subLabel: '📥 数据源' },
    { key: '/platform/kb/vault', icon: FileText, label: 'Vault 文档库' },
    { key: '_sub_kb_ontology', subLabel: '🧬 本体模型' },
    { key: '/ontology-editor', icon: PenTool, label: '本体编辑器' },
    { key: '/infra/ontology', icon: Box, label: '域本体管理' },
    { key: '_sub_kb_library', subLabel: '📚 知识库' },
    { key: '/platform/kb', icon: Database, label: '向量知识库' },
    { key: '/platform/kb/wiki', icon: BookOpen, label: 'LLM Wiki' },
    { key: '_sub_kb_quality', subLabel: '✅ 质量验证' },
    { key: '/platform/kb/eval', icon: Search, label: '检索评估' },
    { key: '/diagnostics/rag-quality', icon: Database, label: 'RAG 质量' },
    { key: '/platform/kb/health', icon: TrendingUp, label: '质量反馈' },
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
    { key: '/diagnostics/eval', icon: BarChart3, label: 'Agent 评估' },
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
    { key: '/core/workflows', icon: GitBranch, label: 'Workflow' },
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
