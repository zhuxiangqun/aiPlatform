import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { menuItems, type MenuEntry, type MenuItem, type MenuGroup } from '../../pageManifest';

// ── Flatten all menu items once (menuItems is static) — avoids O(n²) rebuild in isActive ──
const ALL_MENU_KEYS: string[] = (() => {
  const keys: string[] = [];
  for (const entry of menuItems) {
    if ('items' in entry && Array.isArray(entry.items)) {
      for (const item of entry.items) {
        if (item.key) keys.push(item.key);
      }
    } else if ('key' in entry && (entry as MenuItem).key) {
      keys.push((entry as MenuItem).key);
    }
  }
  return keys;
})();


// ── Role-based sidebar visibility ──────────────────────────────────────

const ROLE_MENUS: Record<string, string[]> = {
  admin:     ["dashboard","knowledge","build","diagnostics","platform","help"],
  developer: ["dashboard","knowledge","build","diagnostics","help"],
  operator:  ["dashboard","diagnostics","platform","help"],
  business:  ["dashboard","help"],
  user:      ["dashboard","help"],
  approver:  ["dashboard","diagnostics","help"],
  fde:       ["dashboard","knowledge","build","diagnostics","help"],
  viewer:    ["dashboard","help"],
};

function getRole(): string {
  return localStorage.getItem('aiplat_role') || 'developer';
}

// ── Two-level sidebar filtering ─────────────────────────────────────
// L1: Group-level (existing ROLE_MENUS)
// L2: Item-level (MenuItem.roles field)

function filterItemsByRole(items: MenuItem[], role: string): MenuItem[] {
  // Pass 1: filter non-subLabel items by roles
  const pass1 = items.filter(item => {
    if (item.subLabel) return true;   // keep subLabels for now
    if (item.roles) return item.roles.includes(role);
    return true;                       // no roles → inherit group visibility
  });

  // Pass 2: find empty subLabels (no visible children), mark for removal
  const emptySubLabels = new Set<string>();
  let currentSubLabel: string | null = null;
  let childCount = 0;

  for (const item of pass1) {
    if (item.subLabel) {
      if (currentSubLabel && childCount === 0) {
        emptySubLabels.add(currentSubLabel);
      }
      currentSubLabel = item.key;
      childCount = 0;
    } else {
      childCount++;
    }
  }
  // Check the last group
  if (currentSubLabel && childCount === 0) {
    emptySubLabels.add(currentSubLabel);
  }

  // Pass 3: remove empty subLabels
  return pass1.filter(item => !item.subLabel || !emptySubLabels.has(item.key));
}

// Advanced tools: admin/dev/fde get default expand; operator/approver get collapsed
function isAdvancedToolsLabel(subLabel: string): boolean {
  return subLabel.includes('高级工具');
}

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员', developer: '开发者', operator: '运维',
  business: '业务负责人', user: '终端用户', approver: '审批人', fde: 'FDE 工程师',
  viewer: '只读视图',
};
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, ChevronDown, ChevronLeft,
  ChevronRight, LogOut, Settings, User,
  type LucideIcon,
} from 'lucide-react';
import { NotificationBellButton, NotificationProvider, ToastProvider } from '../ui';
import FloatingDigitalHuman from '../digital-human/FloatingDigitalHuman';

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
  const [roleMenuOpen, setRoleMenuOpen] = useState(false);

  // URL-based auto-expand + role-based advanced tools default expand
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    const expanded = new Set<string>();
    const path = location.pathname + location.search;
    for (const group of menuItems) {
      if (!('group' in group)) continue;
      for (const item of group.items) {
        if (item.subLabel) continue;
        if (path.startsWith(item.key) || path === item.key) {
          expanded.add(group.group); break;
        }
        // Handle /platform/kb?tab=xxx pattern
        if (item.key.includes('?') && path.startsWith(item.key.split('?')[0])) {
          const tabA = new URLSearchParams(item.key.split('?')[1]).get('tab');
          const tabB = new URLSearchParams(location.search).get('tab');
          if (tabA && tabB && tabA === tabB) {
            expanded.add(group.group); break;
          }
        }
      }
    }
    // 🆕 Advanced tools: admin/dev/fde get diagnostics group expanded by default
    const role = getRole();
    if (['admin', 'developer', 'fde'].includes(role)) {
      expanded.add('diagnostics');
    }
    return expanded;
  });

  // Role-based default landing page redirect
  useEffect(() => {
    const role = getRole();
    const path = location.pathname;
    if (path === '/' || path === '') {
      if (role === 'fde') {
        navigate('/diagnostics/fde', { replace: true });
      } else if (role === 'approver') {
        navigate('/governance', { replace: true });
      }
    }
  }, []);

  const toggleGroup = (g: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(g)) next.delete(g); else next.add(g);
      return next;
    });
  };

   const isActive = (path: string) => {
     if (!path) return false;
     // Exact match
     if (location.pathname + location.search === path) return true;
     // Handle /platform/kb?tab=xxx matching
     if (path.includes('?tab=')) {
       const keyPath = path.split('?')[0];
       const keyTab = new URLSearchParams(path.split('?')[1]).get('tab');
       const curTab = new URLSearchParams(location.search).get('tab');
       if (location.pathname === keyPath && keyTab === curTab) return true;
     }
      // Prefix match: highlight parent. Skip if any item exactly matches current path.
      if (!path.includes('?') && location.pathname.startsWith(path + '/')) {
        const exactChild = ALL_MENU_KEYS.some(key =>
          key.startsWith(path + '/') && location.pathname === key
        );
        if (!exactChild) return true;
      }
      return false;
    };

  // ── Pre-compute filtered sidebar menu ───────────────────────
  const role = getRole();
  const visibleGroups = ROLE_MENUS[role] || [];
  // L1: Group-level filter — exclude groups not in ROLE_MENUS for current role
  const visibleMenu = menuItems.filter(entry => {
    if ('divider' in entry) return true;
    if ('group' in entry) return visibleGroups.includes(entry.group);
    return false;  // no top-level individual items in v2.1
  });

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
                    {ROLE_LABELS[getRole()] || '用户'}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-2 px-2">
            {visibleMenu.map((item, index) => {
              if ('divider' in item) {
                return <div key={index} className="my-2 border-t border-gray-100" />;
              }

              // item is a MenuGroup (L1 filtered by visibleMenu)
              const gname = item.group;
              const isExpanded = expandedGroups.has(gname);

              // L2: Item-level filter
              const role = getRole();
              const visibleItems = filterItemsByRole(item.items, role);

              // Check if any sub-item is active for group highlight
              const hasActiveChild = visibleItems.some(si =>
                !si.subLabel && isActive(si.key));
              return (
                <div key={item.group} className="mb-2">
                  {/* Group header — click to expand/collapse */}
                  <button
                    onClick={() => toggleGroup(gname)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg
                      text-xs font-medium uppercase tracking-wide transition-colors
                      ${hasActiveChild ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
                  >
                    <span className="truncate">{item.label}</span>
                    {!collapsed && (
                      <ChevronDown className={`w-3 h-3 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
                    )}
                  </button>
                  {/* Group items — shown when expanded */}
                  {isExpanded && !collapsed && visibleItems.map((subItem) => {
                    // Sub-label header (non-clickable)
                    if (subItem.subLabel) {
                      return (
                        <div key={subItem.subLabel}
                             className="px-3 pt-2 pb-1 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                          {subItem.subLabel}
                        </div>
                      );
                    }
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
                        title={subItem.label}
                      >
                        {subItem.icon && <subItem.icon className="w-[18px] h-[18px] flex-shrink-0" />}
                        <span className="truncate">{subItem.label}</span>
                      </button>
                    );
                  })}
                  {/* Collapsed mode: show only active child icon */}
                  {!isExpanded && collapsed && hasActiveChild && (
                    <div className="flex justify-center px-2">
                      {(() => {
                        const activeItem = visibleItems.find(si => !si.subLabel && isActive(si.key));
                        return activeItem?.icon
                          ? <activeItem.icon className="w-5 h-5 text-primary" />
                          : null;
                      })()}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>

          {/* Role Switcher */}
          <div className="border-t border-gray-100 px-3 py-2 relative">
            <button
              onClick={() => setRoleMenuOpen(!roleMenuOpen)}
              className="w-full flex items-center gap-2 text-xs text-gray-500 hover:text-gray-200 rounded px-2 py-1.5"
            >
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                getRole() === 'admin' ? 'bg-red-400' :
                getRole() === 'developer' ? 'bg-blue-400' :
                getRole() === 'business' ? 'bg-green-400' :
                getRole() === 'approver' ? 'bg-purple-400' : 'bg-gray-400'
              }`} />
              {!collapsed && <span>{ROLE_LABELS[getRole()] || getRole()}</span>}
              {!collapsed && <ChevronDown size={10} className="ml-auto" />}
            </button>
            {!collapsed && roleMenuOpen && (
              <div className="absolute bottom-full left-3 right-3 mb-1 bg-dark-bg border border-dark-border rounded-lg shadow-lg p-1 z-50">
                {Object.entries(ROLE_LABELS).map(([role, label]) => (
                  <button
                    key={role}
                    onClick={() => {
                      localStorage.setItem('aiplat_role', role);
                      window.location.reload();
                    }}
                    className={`w-full text-left px-3 py-1.5 text-xs rounded hover:bg-dark-hover ${
                      getRole() === role ? 'text-white font-semibold' : 'text-gray-500'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

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
        <FloatingDigitalHuman currentRoute={location.pathname} />
      </ToastProvider>
  );
};

export default AppLayout;
