import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, Info, TriangleAlert, X, XCircle } from 'lucide-react';

export type ToastVariant = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
  createdAt: number;
  durationMs: number;
}

export interface ToastAPI {
  push: (t: Omit<ToastItem, 'id' | 'createdAt'> & { id?: string }) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const ToastContext = createContext<ToastAPI | null>(null);

let _toastApi: ToastAPI | null = null;

/** 允许在任何地方（非 React hook）调用 toast.xxx() */
export const toast = {
  success: (title: string, description?: string) => _toastApi?.push({ variant: 'success', title, description, durationMs: 3000 }),
  error: (title: string, description?: string) => _toastApi?.push({ variant: 'error', title, description, durationMs: 5000 }),
  warning: (title: string, description?: string) => _toastApi?.push({ variant: 'warning', title, description, durationMs: 4000 }),
  info: (title: string, description?: string) => _toastApi?.push({ variant: 'info', title, description, durationMs: 3000 }),
};

const iconFor = (variant: ToastVariant) => {
  switch (variant) {
    case 'success':
      return <CheckCircle2 className="w-4 h-4 text-success" />;
    case 'error':
      return <XCircle className="w-4 h-4 text-error" />;
    case 'warning':
      return <TriangleAlert className="w-4 h-4 text-warning" />;
    case 'info':
    default:
      return <Info className="w-4 h-4 text-primary" />;
  }
};

const containerClassFor = (variant: ToastVariant) => {
  switch (variant) {
    case 'success':
      return 'border-success-border';
    case 'error':
      return 'border-error-border';
    case 'warning':
      return 'border-warning-border';
    case 'info':
    default:
      return 'border-primary-border';
  }
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timersRef = useRef<Record<string, number>>({});

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const handle = timersRef.current[id];
    if (handle) {
      window.clearTimeout(handle);
      delete timersRef.current[id];
    }
  }, []);

  const clear = useCallback(() => {
    setItems([]);
    Object.values(timersRef.current).forEach((h) => window.clearTimeout(h));
    timersRef.current = {};
  }, []);

  const push = useCallback(
    (t: Omit<ToastItem, 'id' | 'createdAt'> & { id?: string }) => {
      const id = t.id || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const next: ToastItem = {
        id,
        variant: t.variant,
        title: t.title,
        description: t.description,
        durationMs: t.durationMs ?? 3000,
        createdAt: Date.now(),
      };
      setItems((prev) => [next, ...prev].slice(0, 5));
      const handle = window.setTimeout(() => dismiss(id), next.durationMs);
      timersRef.current[id] = handle;
      return id;
    },
    [dismiss]
  );

  const api = useMemo<ToastAPI>(() => ({ push, dismiss, clear }), [push, dismiss, clear]);

  useEffect(() => {
    _toastApi = api;
    return () => {
      if (_toastApi === api) _toastApi = null;
    };
  }, [api]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="fixed top-4 right-4 z-[800] w-[360px] max-w-[calc(100vw-2rem)] space-y-2">
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.15 }}
              className={`
                bg-dark-card border rounded-xl shadow-lg
                ${containerClassFor(t.variant)}
              `}
            >
              <div className="p-3 flex items-start gap-3">
                <div className="mt-0.5">{iconFor(t.variant)}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-100">{t.title}</div>
                  {t.description && <div className="text-xs text-gray-500 mt-0.5 break-words">{t.description}</div>}
                </div>
                <button
                  onClick={() => dismiss(t.id)}
                  className="p-1 rounded-lg text-gray-500 hover:bg-dark-hover hover:text-gray-200 transition-colors"
                  aria-label="关闭"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastAPI => {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // 兜底：避免在 Provider 外调用导致崩溃
    return {
      push: () => '',
      dismiss: () => {},
      clear: () => {},
    };
  }
  return ctx;
};

export default ToastProvider;

