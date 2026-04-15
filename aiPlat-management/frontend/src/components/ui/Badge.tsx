import React from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-gray-100 text-gray-700',
  success: 'bg-success-light text-green-700',
  warning: 'bg-warning-light text-amber-700',
  error: 'bg-error-light text-red-700',
  info: 'bg-primary-light text-blue-700',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  children,
  className = '',
}) => {
  return (
    <span
      className={`
        inline-flex items-center px-2.5 py-0.5 rounded-full
        text-xs font-medium
        ${variantStyles[variant]}
        ${className}
      `}
    >
      {children}
    </span>
  );
};

interface TagProps {
  color?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  onClose?: () => void;
}

export const Tag: React.FC<TagProps> = ({
  color,
  icon,
  children,
  className = '',
  onClose,
}) => {
  return (
    <span
      className={`
        inline-flex items-center gap-1 px-2.5 py-1 rounded-md
        text-xs font-medium
        ${color ? '' : 'bg-gray-100 text-gray-700'}
        ${className}
      `}
      style={color ? { backgroundColor: `${color}15`, color } : undefined}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
      {onClose && (
        <button
          onClick={onClose}
          className="ml-1 hover:opacity-70"
        >
          ×
        </button>
      )}
    </span>
  );
};

export default Badge;
