import React from 'react';
import { Inbox } from 'lucide-react';

interface EmptyProps {
  description?: string;
  icon?: React.ReactNode;
  className?: string;
}

export const Empty: React.FC<EmptyProps> = ({
  description = '暂无数据',
  icon,
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center py-12 ${className}`}>
      {icon || <Inbox className="w-12 h-12 text-gray-300 mb-3" />}
      <p className="text-sm text-gray-400">{description}</p>
    </div>
  );
};

export default Empty;
