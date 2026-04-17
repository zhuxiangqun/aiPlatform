import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Server,
  Cpu,
  Database,
  Network,
  Monitor,
  Bot,
  Sparkles,
  Brain,
  HardDrive,
  Shield,
  ShieldCheck,
  FileText,
  Layers,
  Users,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  Settings,
  LogOut,
  User,
  Bell,
  ChevronDown,
  Wrench,
  Activity,
  Plug,
  Package,
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
  { key: '/overview', icon: LayoutDashboard, label: '平台总览' },
  { key: '/alerts', icon: Bell, label: '告警中心' },
  { key: '/diagnostics', icon: Activity, label: '可观测性' },
  { divider: true },
  { group: 'infra', label: '基础设施层', items: [
    { key: '/infra/nodes', icon: Server, label: '节点管理' },
    { key: '/infra/models', icon: Cpu, label: '模型管理' },
    { key: '/infra/services', icon: Database, label: '服务管理' },
    { key: '/infra/scheduler', icon: HardDrive, label: '算力调度' },
    { key: '/infra/storage', icon: Database, label: '存储管理' },
    { key: '/infra/network', icon: Network, label: '网络管理' },
    { key: '/infra/monitoring', icon: Monitor, label: '监控告警' },
  ]},
  { divider: true },
  { group: 'core', label: '核心能力层', items: [
    { key: '/core/agents', icon: Bot, label: 'Agent管理' },
    { key: '/core/skills', icon: Sparkles, label: 'Skill管理' },
    { key: '/core/tools', icon: Wrench, label: 'Tool管理' },
    { key: '/core/mcp', icon: Plug, label: 'MCP管理' },
    { key: '/core/memory', icon: Brain, label: 'Memory管理' },
    { key: '/core/learning/artifacts', icon: FileText, label: 'Learning产物' },
    { key: '/core/learning/releases', icon: Layers, label: 'Release候选' },
    { key: '/core/approvals', icon: ShieldCheck, label: '审批中心' },
  ]},
  { divider: true },
  { group: 'workspace', label: '应用库', items: [
    { key: '/workspace/agents', icon: Package, label: 'Agent库' },
    { key: '/workspace/skills', icon: Package, label: 'Skill库' },
    { key: '/workspace/mcp', icon: Package, label: 'MCP库' },
  ]},
  { divider: true },
  { group: 'platform', label: '平台服务层', items: [
    { key: '/platform/gateway', icon: Network, label: 'API网关' },
    { key: '/platform/auth', icon: Shield, label: '认证鉴权' },
    { key: '/platform/tenant', icon: Users, label: '多租户' },
  ]},
  { divider: true },
  { group: 'app', label: '应用接入层', items: [
    { key: '/app/channels', icon: MessageSquare, label: '渠道管理' },
    { key: '/app/sessions', icon: MessageSquare, label: '会话管理' },
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
              <span className="ml-3 font-semibold text-gray-200 tracking-tight">
                AI Platform
              </span>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-2 px-2">
            {menuItems.map((item, index) => {
              if ('divider' in item) {
                return <div key={index} className="my-2 border-t border-gray-100" />;
              }

              if ('group' in item) {
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
