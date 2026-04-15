import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface StatisticProps {
  title: string;
  value: number | string;
  suffix?: string;
  prefix?: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  valueStyle?: React.CSSProperties;
  className?: string;
}

export const Statistic: React.FC<StatisticProps> = ({
  title,
  value,
  suffix,
  prefix,
  trend,
  trendValue,
  valueStyle,
  className = '',
}) => {
  const getTrendIcon = () => {
    if (trend === 'up') return <TrendingUp className="w-4 h-4 text-success" />;
    if (trend === 'down') return <TrendingDown className="w-4 h-4 text-error" />;
    return null;
  };

  return (
    <div className={`p-4 ${className}`}>
      <div className="text-sm text-gray-400 mb-1">{title}</div>
      <div className="flex items-baseline gap-2">
        {prefix && <span className="text-gray-400">{prefix}</span>}
        <span className="text-2xl font-semibold text-gray-100" style={valueStyle}>
          {value}
        </span>
        {suffix && <span className="text-gray-400">{suffix}</span>}
      </div>
      {trend && trendValue && (
        <div className="flex items-center gap-1 mt-1">
          {getTrendIcon()}
          <span className={`text-xs ${trend === 'up' ? 'text-success' : trend === 'down' ? 'text-error' : 'text-gray-500'}`}>
            {trendValue}
          </span>
        </div>
      )}
    </div>
  );
};

export default Statistic;
