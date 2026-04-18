import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Bell, Check, Trash2 } from 'lucide-react';

import { Drawer } from './Drawer';
import { Button } from './Button';

export type NotificationVariant = 'info' | 'success' | 'warning' | 'error';

export interface NotificationItem {
  id: string;
  variant: NotificationVariant;
  title: string;
  description?: string;
  createdAt: number;
  read: boolean;
  link?: string; // 可选：点击跳转（路由）
}

export interface NotificationAPI {
  notify: (n: Omit<NotificationItem, 'id' | 'createdAt' | 'read'> & { id?: string; createdAt?: number; read?: boolean }) => string;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clear: () => void;
  open: () => void;
  close: () => void;
  isOpen: boolean;
  unreadCount: number;
  items: NotificationItem[];
}

const NotificationContext = createContext<NotificationAPI | null>(null);

let _notifyApi: Pick<NotificationAPI, 'notify' | 'open'> | null = null;

/** 允许在任何地方调用 notify.xxx()（不依赖 hooks） */
export const notify = {
  info: (title: string, description?: string, link?: string) => _notifyApi?.notify({ variant: 'info', title, description, link }),
  success: (title: string, description?: string, link?: string) => _notifyApi?.notify({ variant: 'success', title, description, link }),
  warning: (title: string, description?: string, link?: string) => _notifyApi?.notify({ variant: 'warning', title, description, link }),
  error: (title: string, description?: string, link?: string) => _notifyApi?.notify({ variant: 'error', title, description, link }),
  open: () => _notifyApi?.open(),
};

const badgeClassFor = (variant: NotificationVariant) => {
  switch (variant) {
    case 'success':
      return 'bg-success-light text-green-300';
    case 'warning':
      return 'bg-warning-light text-amber-300';
    case 'error':
      return 'bg-error-light text-red-300';
    case 'info':
    default:
      return 'bg-primary-light text-blue-300';
  }
};

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);

  const unreadCount = useMemo(() => items.filter((i) => !i.read).length, [items]);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  const markRead = useCallback((id: string) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, read: true } : i)));
  }, []);

  const markAllRead = useCallback(() => {
    setItems((prev) => prev.map((i) => ({ ...i, read: true })));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const doNotify = useCallback(
    (n: Omit<NotificationItem, 'id' | 'createdAt' | 'read'> & { id?: string; createdAt?: number; read?: boolean }) => {
      const id = n.id || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const createdAt = n.createdAt ?? Date.now();
      const item: NotificationItem = {
        id,
        variant: n.variant,
        title: n.title,
        description: n.description,
        createdAt,
        read: n.read ?? false,
        link: n.link,
      };
      setItems((prev) => [item, ...prev].slice(0, 200));
      return id;
    },
    []
  );

  const api = useMemo<NotificationAPI>(
    () => ({
      notify: doNotify,
      markRead,
      markAllRead,
      clear,
      open,
      close,
      isOpen,
      unreadCount,
      items,
    }),
    [doNotify, markRead, markAllRead, clear, open, close, isOpen, unreadCount, items]
  );

  useEffect(() => {
    _notifyApi = { notify: doNotify, open };
    return () => {
      _notifyApi = null;
    };
  }, [doNotify, open]);

  return (
    <NotificationContext.Provider value={api}>
      {children}
      <Drawer
        open={isOpen}
        onClose={close}
        title="通知中心"
        footer={
          <>
            <Button variant="secondary" onClick={markAllRead} icon={<Check size={16} />}>
              全部已读
            </Button>
            <Button variant="danger" onClick={clear} icon={<Trash2 size={16} />}>
              清空
            </Button>
          </>
        }
      >
        {items.length === 0 ? (
          <div className="text-sm text-gray-500">暂无通知</div>
        ) : (
          <div className="space-y-2">
            {items.map((n) => (
              <div
                key={n.id}
                className={`
                  p-3 rounded-xl border border-dark-border
                  ${n.read ? 'bg-dark-bg' : 'bg-dark-hover'}
                `}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${badgeClassFor(n.variant)}`}>
                        {n.variant}
                      </span>
                      <div className="text-sm font-medium text-gray-100 truncate">{n.title}</div>
                    </div>
                    {n.description && <div className="text-xs text-gray-500 mt-1 break-words">{n.description}</div>}
                    <div className="text-[11px] text-gray-500 mt-1">
                      {new Date(n.createdAt).toLocaleString('zh-CN')}
                    </div>
                    {n.link && (
                      <div className="mt-2">
                        <button
                          type="button"
                          className="text-xs text-primary hover:text-primary-hover"
                          onClick={() => {
                            const link = n.link;
                            if (!link) return;
                            markRead(n.id);
                            close();
                            // Open in a new tab by default to avoid disrupting current workflow.
                            const url = link.startsWith('http')
                              ? link
                              : `${window.location.origin}${link.startsWith('/') ? link : `/${link}`}`;
                            window.open(url, '_blank', 'noopener,noreferrer');
                          }}
                        >
                          打开详情
                        </button>
                      </div>
                    )}
                  </div>
                  {!n.read && (
                    <button
                      className="p-1 rounded-lg text-gray-500 hover:bg-dark-bg hover:text-gray-200 transition-colors"
                      onClick={() => markRead(n.id)}
                      aria-label="标记已读"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Drawer>
    </NotificationContext.Provider>
  );
};

export const useNotifications = (): NotificationAPI => {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    return {
      notify: () => '',
      markRead: () => {},
      markAllRead: () => {},
      clear: () => {},
      open: () => {},
      close: () => {},
      isOpen: false,
      unreadCount: 0,
      items: [],
    };
  }
  return ctx;
};

/** 顶部铃铛按钮（可选组件） */
export const NotificationBellButton: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { open, unreadCount } = useNotifications();
  return (
    <button
      onClick={open}
      className={`relative p-2 rounded-lg text-gray-500 hover:text-gray-500 hover:bg-dark-hover transition-colors ${className}`}
      aria-label="通知中心"
    >
      <Bell className="w-[18px] h-[18px]" />
      {unreadCount > 0 && (
        <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-error text-white text-[11px] flex items-center justify-center">
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  );
};
