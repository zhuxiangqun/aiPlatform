import React, { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  width?: number | string;
  footer?: React.ReactNode;
  className?: string;
}

/**
 * 右侧抽屉（Drawer）
 * - 用于 Notification Center 等需要侧边上下文的场景
 */
export const Drawer: React.FC<DrawerProps> = ({
  open,
  onClose,
  title,
  children,
  width = 420,
  footer,
  className = '',
}) => {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [open, onClose]);

  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  const widthStyle = typeof width === 'number' ? `${width}px` : width;

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[600]">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/50"
            onClick={onClose}
          />

          <motion.div
            initial={{ x: 24, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 24, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className={`
              absolute right-0 top-0 bottom-0
              bg-dark-card border-l border-dark-border shadow-xl
              flex flex-col
              ${className}
            `}
            style={{ width: widthStyle, maxWidth: '90vw' }}
          >
            <div className="h-[60px] px-5 border-b border-dark-border flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-100">{title}</div>
              <button
                onClick={onClose}
                className="p-1 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-dark-hover transition-colors"
                aria-label="关闭"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">{children}</div>

            {footer && (
              <div className="px-5 py-4 border-t border-dark-border flex justify-end gap-3">
                {footer}
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default Drawer;

