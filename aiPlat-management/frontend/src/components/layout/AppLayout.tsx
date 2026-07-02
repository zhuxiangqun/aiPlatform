import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';

// ── Role-based sidebar visibility ──────────────────────────────────────

const ROLE_MENUS: Record<string, string[]> = {
  admin:     ["infra", "core", "platform", "workspace", "app", "value", "user", "prompts"],
  developer: ["infra", "core", "workspace", "value", "user", "diagnostics"],
  business:  ["value", "user"],
  user:      ["user", "app"],
  approver:  ["user"],
};

function getRole(): string {
  return localStorage.getItem('aiplat_role') || 'developer';
}
function canSee(group: string): boolean {
  return (ROLE_MENUS[getRole()] || []).includes(group);
}
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, BarChart3, Bell, Bot, Box, Brain, ChevronDown, ChevronLeft,
  ChevronRight, Cpu, Database, FileText, Flag, FolderOpen, GitBranch, HardDrive, Key,
  LogOut, MessageSquare, Monitor, Network, Package, PenTool, Plug,
  Rocket, Server, Settings, Share2, Shield, ShoppingBag, Sliders, Sparkles, Target, User, Users, Wrench,
  type LucideIcon,
} from 'lucide-react';
import { NotificationBellButton, NotificationProvider, ToastProvider } from '../ui';

interface MenuItem {
  key: string;
  icon: LucideIcon;
  label: string;
}

interface MenuGroup {
  group: string;
  label: string;
  items: MenuItem[];
}

const menuItems: (MenuItem | { divider: boolean } | MenuGroup)[] = [
  { key: '/system-overview', icon: Activity, label: '系统概览' },
  { key: '/alerts', icon: Bell, label: '告警中心' },
  { key: '/releases', icon: Rocket, label: '版本管理' },
  { key: '/diagnostics', icon: Activity, label: '诊断中心' },
  { key: '/diagnostics/repairs', icon: Activity, label: '修复中心' },
  { key: '/diagnostics/eval', icon: BarChart3, label: 'Agent 评估' },
  { key: '/system-graph', icon: Activity, label: '系统图谱' },
  { key: '/onboarding', icon: Settings, label: '初始化向导' },
  { divider: true },
  { group: 'infra', label: '基础设施层', items: [
    { key: '/infra/nodes', icon: Server, label: '节点管理' },
    { key: '/infra/models', icon: Cpu, label: '模型管理' },
    { key: '/infra/finetune', icon: Wrench, label: '模型微调' },
    { key: '/infra/services', icon: Database, label: '服务管理' },
    { key: '/infra/scheduler', icon: HardDrive, label: '算力调度' },
    { key: '/infra/storage', icon: Database, label: '存储管理' },
    { key: '/infra/network', icon: Network, label: '网络管理' },
    { key: '/infra/monitoring', icon: Monitor, label: '监控告警' },
    { key: '/infra/llm-stats', icon: Monitor, label: 'LLM 路由监控' },
  ]},
  { divider: true },
  { group: 'core', label: '核心能力层', items: [
    { key: '/core/agents', icon: Bot, label: 'Agent管理' },
    { key: '/core/skills', icon: Sparkles, label: 'Skill管理' },
    { key: '/core/tools', icon: Wrench, label: 'Tool管理' },
    { key: '/core/mcp', icon: Plug, label: 'MCP管理' },
    { key: '/core/variables', icon: PenTool, label: '变量管理' },
    { key: '/core/credentials', icon: Key, label: '凭证管理' },
    { key: '/core/memory', icon: Brain, label: 'Memory管理' },
    { key: '/core/prompts', icon: FileText, label: '系统Prompt' },
    { key: '/core/agent-insight', icon: BarChart3, label: 'Agent能力' },
  ]},
  { divider: true },
  { group: 'prompts', label: '提示词工程', items: [
    { key: '/prompts/app', icon: FileText, label: '应用模板' },
  ]},
  { divider: true },
  { group: 'workspace', label: '应用能力层', items: [
    { key: '/workspace/agents', icon: Bot, label: 'Agent库' },
    { key: '/workspace/skills', icon: Sparkles, label: 'Skill库' },
    { key: '/workspace/tools', icon: Wrench, label: 'Tool库' },
    { key: '/core/workflows', icon: GitBranch, label: 'Workflow库' },
    { key: '/workspace/marketplace', icon: ShoppingBag, label: '商城' },
    { key: '/core/skill-packs', icon: Package, label: '包管理' },
    { key: '/workspace/mcp', icon: Plug, label: 'MCP库' },
    { key: '/workspace/teams', icon: Users, label: '团队组装' },
    { key: '/plugins', icon: Box, label: '插件管理' },
  ]},
  { divider: true },
  { group: 'platform', label: '平台服务层', items: [
    { key: '/platform/kb', icon: Database, label: '知识库管理' },
    { key: '/infra/ontology', icon: Share2, label: '本体管理' },
    { key: '/platform/gateway', icon: Network, label: 'API网关' },
    { key: '/platform/auth', icon: Shield, label: '认证鉴权' },
    { key: '/platform/tenant', icon: Users, label: '多租户' },
  ]},
  { divider: true },
  { group: 'app', label: '应用接入层', items: [
    { key: '/app/channels', icon: MessageSquare, label: '渠道管理' },
    { key: '/app/sessions', icon: MessageSquare, label: '会话管理' },
    { key: '/app/builder', icon: FolderOpen, label: '项目构建' },
    { key: '/app/diagrams', icon: PenTool, label: '图表工作室' },
    { key: '/app/apps', icon: Rocket, label: '已部署应用' },
  { key: '/studio', icon: Sparkles, label: 'App Studio' },
  ]},
  { divider: true },
  { group: 'value', label: '价值中心', items: [
    { key: '/value-center', icon: BarChart3, label: '价值看板' },
    { key: '/value-center/kpis', icon: Target, label: 'KPI管理' },
    { key: '/value-center/goals', icon: Flag, label: '目标追踪' },
    { key: '/value-center/roles', icon: Users, label: '角色管理' },
    { key: '/value-center/strategy', icon: Sliders, label: '策略控制' },
    { key: '/value-center/training', icon: GitBranch, label: '训练监控' },
  ]},
  { divider: true },
  { group: 'user', label: '终端使用', items: [
    { key: '/workbench', icon: Monitor, label: '工作台' },
  ]},
];

const userMenuItems: (MenuItem | { divider: boolean; key: string })[] = [
  { key: 'profile', icon: User, label: '个人中心' },
  { key: 'settings', icon: Settings, label: '系统设置' },
  { divider: true, key: 'divider1' },
];

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const isActive = (path: string) => location.pathname === path;

  return (
    <ToastProvider>
      <NotificationProvider>
        <div className="min-h-screen bg-dark-bg flex">
          {/* Sidebar */}
          <aside
            className={`
              fixed left-0 top-0 bottom-0 bg-dark-bg border-r border-dark-border z-40
              transition-all duration-200 ease-out overflow-hidden
              flex flex-col
              ${collapsed ? 'w-16' : 'w-60'}
            `}
          >
          {/* Logo */}
          <div className="h-[60px] flex items-center justify-center border-b border-dark-border px-4">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
              AI
            </div>
            {!collapsed && (
              <div>
                <span className="ml-3 font-semibold text-gray-200 tracking-tight">
                  AI Platform
                </span>
                <div className="ml-3 mt-1">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                    getRole() === 'admin' ? 'bg-red-900/50 text-red-400' :
                    getRole() === 'developer' ? 'bg-blue-900/50 text-blue-400' :
                    getRole() === 'business' ? 'bg-green-900/50 text-green-400' :
                    getRole() === 'approver' ? 'bg-purple-900/50 text-purple-400' :
                    'bg-gray-700 text-gray-400'
                  }`}>
                    {getRole() === 'admin' ? '管理员' :
                     getRole() === 'developer' ? '开发者' :
                     getRole() === 'business' ? '业务' :
                     getRole() === 'approver' ? '审批' : '用户'}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-2 px-2">
            {menuItems.map((item, index) => {
              if ('divider' in item) {
                return <div key={index} className="my-2 border-t border-gray-100" />;
              }

              if ('group' in item) {
                if (!canSee(item.group)) return null;
                return (
                  <div key={item.group} className="mb-2">
                    {!collapsed && (
                      <div className="px-3 py-2 text-xs font-medium text-gray-500 uppercase tracking-wide">
                        {item.label}
                      </div>
                    )}
                    {item.items.map((subItem) => {
                      const active = isActive(subItem.key);
                      return (
                        <button
                          key={subItem.key}
                          onClick={() => navigate(subItem.key)}
                          className={`
                            w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-0.5
                            text-sm font-medium transition-colors
                            ${active
                              ? 'bg-primary-light text-primary'
                              : 'text-gray-500 hover:bg-dark-hover hover:text-gray-200'
                            }
                          `}
                          title={collapsed ? subItem.label : undefined}
                        >
                          <subItem.icon className="w-[18px] h-[18px] flex-shrink-0" />
                          {!collapsed && <span>{subItem.label}</span>}
                        </button>
                      );
                    })}
                  </div>
                );
              }

              const active = isActive(item.key);
              return (
                <button
                  key={item.key}
                  onClick={() => navigate(item.key)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-0.5
                    text-sm font-medium transition-colors
                    ${active
                      ? 'bg-primary-light text-primary'
                      : 'text-gray-500 hover:bg-dark-hover hover:text-gray-200'
                    }
                  `}
                  title={collapsed ? item.label : undefined}
                >
                  <item.icon className="w-[18px] h-[18px] flex-shrink-0" />
                  {!collapsed && <span>{item.label}</span>}
                </button>
              );
            })}
          </nav>

          {/* Collapse Button */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="h-12 flex items-center justify-center border-t border-gray-100 text-gray-500 hover:text-gray-500 hover:bg-dark-hover transition-colors"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            {!collapsed && <span className="ml-2 text-sm">收起</span>}
          </button>
        </aside>

          {/* Main Content */}
          <main className={`flex-1 ${collapsed ? 'ml-16' : 'ml-60'} transition-all duration-200`}>
            {/* Header */}
            <header className="h-[60px] bg-dark-bg border-b border-dark-border px-6 flex items-center justify-end">
              <div className="flex items-center gap-4">
                {/* Notifications */}
                <NotificationBellButton />

              {/* User Menu */}
              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-dark-hover transition-colors"
                >
                  <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white text-sm font-medium">
                    A
                  </div>
                  <div className="text-left leading-tight">
                    <div className="text-sm font-medium text-gray-200">Admin</div>
                    <div className="text-xs text-gray-500">管理员</div>
                  </div>
                  <ChevronDown className="w-4 h-4 text-gray-500" />
                </button>

                {/* Dropdown */}
                <AnimatePresence>
                  {userMenuOpen && (
                    <>
                      <div
                        className="fixed inset-0 z-40"
                        onClick={() => setUserMenuOpen(false)}
                      />
                      <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.15 }}
                        className="absolute right-0 top-full mt-2 w-48 bg-dark-card rounded-xl shadow-lg border border-dark-border py-1 z-50"
                      >
                        {userMenuItems.map((item) => {
                          if ('divider' in item) {
                            return <div key={item.key} className="my-1 border-t border-gray-100" />;
                          }
                          return (
                            <button
                              key={item.key}
                              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-dark-hover"
                            >
                              <item.icon className="w-4 h-4" />
                              {item.label}
                            </button>
                          );
                        })}
                        <div className="my-1 border-t border-gray-100" />
                        <button
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-error hover:bg-error-light"
                        >
                          <LogOut className="w-4 h-4" />
                          退出登录
                        </button>
                      </motion.div>
                    </>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </header>

          {/* Page Content */}
          <div className="p-6 bg-dark-bg min-h-[calc(100vh-60px)]">
            <Outlet />
          </div>
          </main>
        </div>
      </NotificationProvider>
    </ToastProvider>
  );
};

export default AppLayout;
