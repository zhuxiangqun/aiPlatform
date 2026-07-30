import {
  Activity, AlertTriangle, BarChart3, Bell, BookOpen, Bot, Box, Brain,
  Cpu, Database, FileText, FolderOpen, GitBranch, HardDrive, Key,
  MessageSquare, Monitor, Network, Package, PenTool, Plug,
  Rocket, Search, Settings, Share2, Shield, ShoppingBag, Sparkles,
  TrendingUp, Users, Wrench,
  type LucideIcon,
} from 'lucide-react';

// ─── Shared types ────────────────────────────────────────────────────

export interface MenuItem {
  key: string;
  icon?: LucideIcon;
  label: string;
  subLabel?: string;
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

// ─── Sidebar menu structure (single source of truth) ─────────────────

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
    { key: '/platform/kb/health', icon: TrendingUp, label: '质量反馈' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // AI 应用工厂
  // ════════════════════════════════════════════════════════════════
  { group: 'build', label: '🤖 AI 应用工厂', items: [
    { key: '_sub_lifecycle', subLabel: '📦 应用生命周期' },
    { key: '/studio', icon: Sparkles, label: '新建应用' },
    { key: '/diagnostics/fde', icon: Wrench, label: 'FDE 工作台' },
    { key: '/app/builder', icon: FolderOpen, label: '我的项目' },
    { key: '/app/apps', icon: Rocket, label: '已部署应用' },
    { key: '_sub_assembly', subLabel: '🧩 能力组装' },
    { key: '/core/agents', icon: Bot, label: 'Agent 管理' },
    { key: '/core/skills', icon: Sparkles, label: 'Skill 管理' },
    { key: '/core/workflows', icon: GitBranch, label: 'Workflow 管理' },
    { key: '/core/tools', icon: Wrench, label: 'Tool 管理' },
    { key: '/core/mcp', icon: Plug, label: 'MCP 连接' },
    { key: '/core/memory', icon: Brain, label: 'Memory 管理' },
    { key: '/workspace/marketplace', icon: ShoppingBag, label: '能力市场' },
    { key: '_sub_runtime', subLabel: '⚙️ 运行时配置' },
    { key: '/core/prompts', icon: FileText, label: '提示词配置' },
    { key: '/core/variables', icon: PenTool, label: '变量管理' },
    { key: '/core/credentials', icon: Key, label: '凭证管理' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 诊断与治理
  // ════════════════════════════════════════════════════════════════
  { group: 'diagnostics', label: '🩺 诊断与治理', items: [
    { key: '_sub_platform', subLabel: '📊 平台健康' },
    { key: '/diagnostics', icon: Activity, label: '诊断概览' },
    { key: '/diagnostics/control-profile', icon: Cpu, label: '控制画像' },
    { key: '/diagnostics/observability', icon: Monitor, label: '可观测性' },
    { key: '_sub_knowledge', subLabel: '🧠 知识健康' },
    { key: '/diagnostics/knowledge-health', icon: Database, label: '本体审计' },
    { key: '/diagnostics/drift-status', icon: AlertTriangle, label: '知识漂移' },
    { key: '/diagnostics/llm-review', icon: Search, label: 'LLM 审查' },
    { key: '_sub_project', subLabel: '📈 项目健康' },
    { key: '/diagnostics/business-value', icon: TrendingUp, label: '业务价值' },
    { key: '/diagnostics/eval', icon: BarChart3, label: 'Agent 评估' },
    { key: '/diagnostics/repairs', icon: Wrench, label: '修复中心' },
    { key: '_sub_runtime', subLabel: '🔍 安全与合规' },
    { key: '/diagnostics/safety', icon: Shield, label: '安全监控' },
    { key: '/diagnostics/audit', icon: FileText, label: '审计日志' },
    { key: '/diagnostics/change-control', icon: Shield, label: '变更控制' },
    { key: '_sub_approval', subLabel: '📋 审批管理' },
    { key: '/approval', icon: Package, label: '资产审批' },
    { key: '/core/approvals', icon: Shield, label: '运行时审批' },
    { key: '/approval/history', icon: FileText, label: '审批记录' },
  ]},
  { divider: true },
  // ════════════════════════════════════════════════════════════════
  // 平台设置
  // ════════════════════════════════════════════════════════════════
  { group: 'platform', label: '⚙️ 平台设置', items: [
    { key: '_sub_ops', subLabel: '🔧 日常运维' },
    { key: '/infra/models', icon: Cpu, label: '模型管理' },
    { key: '/infra/finetune', icon: Wrench, label: '模型微调' },
    { key: '/infra/storage', icon: Database, label: '存储管理' },
    { key: '/infra/scheduler', icon: HardDrive, label: '算力调度' },
    { key: '_sub_config', subLabel: '🔐 平台配置' },
    { key: '/platform/gateway', icon: Network, label: 'API 网关' },
    { key: '/platform/auth', icon: Shield, label: '认证鉴权' },
    { key: '/platform/tenant', icon: Users, label: '多租户管理' },
    { key: '/app/channels', icon: MessageSquare, label: '渠道管理' },
    { key: '/app/sessions', icon: MessageSquare, label: '会话管理' },
    { key: '_sub_sysops', subLabel: '🛡️ 系统运维' },
    { key: '/onboarding', icon: Settings, label: '初始化向导' },
    { key: '/pentest', icon: Shield, label: '渗透测试' },
    { key: '/releases', icon: Rocket, label: '版本管理' },
    { key: '/infra/llm-stats', icon: Monitor, label: 'LLM 路由监控' },
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
