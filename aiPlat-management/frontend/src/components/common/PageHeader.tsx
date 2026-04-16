import { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';

import { Button, Switch } from '../ui';

interface PageHeaderProps {
  title: string;
  description?: string;
  extra?: ReactNode;
  actions?: ReactNode;
  autoRefresh?: boolean;
  onRefresh?: () => void;
  loading?: boolean;
}

/**
 * 页面通用 Header（统一 UI Kit 口径）
 */
const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  extra,
  actions,
  autoRefresh,
  onRefresh,
  loading,
}) => {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="m-0 text-2xl font-semibold text-gray-200 tracking-tight leading-tight">
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-sm text-gray-500 leading-relaxed">
            {description}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        {autoRefresh !== undefined && onRefresh && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">自动刷新</span>
            <Switch checked={autoRefresh} onChange={() => {}} size="sm" />
          </div>
        )}

        {onRefresh && (
          <Button
            variant="secondary"
            onClick={onRefresh}
            loading={loading}
            icon={<RotateCcw size={14} />}
          >
            刷新
          </Button>
        )}

        {extra}
        {actions}
      </div>
    </div>
  );
};

export default PageHeader;
