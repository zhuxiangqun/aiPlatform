import React from 'react';

interface ProgressProps {
  value: number;
  max?: number;
  showLabel?: boolean;
  strokeColor?: string;
  trackColor?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const Progress: React.FC<ProgressProps> = ({
  value,
  max = 100,
  showLabel = false,
  strokeColor = '#3B82F6',
  trackColor = '#E5E7EB',
  size = 'md',
  className = '',
}) => {
  const percent = Math.min(100, Math.max(0, (value / max) * 100));

  const heightStyles = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  };

  return (
    <div className={`w-full ${className}`}>
      <div
        className={`w-full bg-gray-100 rounded-full overflow-hidden ${heightStyles[size]}`}
        style={{ backgroundColor: trackColor }}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${percent}%`, backgroundColor: strokeColor }}
        />
      </div>
      {showLabel && (
        <div className="mt-1 text-xs text-gray-500 text-right">
          {Math.round(percent)}%
        </div>
      )}
    </div>
  );
};

export default Progress;
