import React from 'react';
import { CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';

type AlertType = 'success' | 'error' | 'warning' | 'info';

interface AlertProps {
  type?: AlertType;
  title?: string;
  children: React.ReactNode;
  className?: string;
  closable?: boolean;
  onClose?: () => void;
}

const typeConfig: Record<AlertType, { bg: string; border: string; icon: React.ReactNode; iconColor: string }> = {
  success: {
    bg: 'bg-success-light',
    border: 'border-success/20',
    icon: <CheckCircle className="w-5 h-5 text-success" />,
    iconColor: 'text-success',
  },
  error: {
    bg: 'bg-error-light',
    border: 'border-error/20',
    icon: <AlertCircle className="w-5 h-5 text-error" />,
    iconColor: 'text-error',
  },
  warning: {
    bg: 'bg-warning-light',
    border: 'border-warning/20',
    icon: <AlertTriangle className="w-5 h-5 text-warning" />,
    iconColor: 'text-warning',
  },
  info: {
    bg: 'bg-primary-light',
    border: 'border-primary/20',
    icon: <Info className="w-5 h-5 text-primary" />,
    iconColor: 'text-primary',
  },
};

export const Alert: React.FC<AlertProps> = ({
  type = 'info',
  title,
  children,
  className = '',
  closable,
  onClose,
}) => {
  const config = typeConfig[type];

  return (
    <div
      className={`
        flex gap-3 p-4 rounded-lg border
        ${config.bg} ${config.border}
        ${className}
      `}
    >
      <div className={config.iconColor}>{config.icon}</div>
      <div className="flex-1">
        {title && <div className="font-medium text-gray-100">{title}</div>}
        <div className="text-sm text-gray-400">{children}</div>
      </div>
      {closable && onClose && (
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-300"
        >
          ×
        </button>
      )}
    </div>
  );
};

export default Alert;
