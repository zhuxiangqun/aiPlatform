import { ReactNode } from 'react';
import { Button, Space, Switch } from 'antd';
import { RotateCcw } from 'lucide-react';
import { theme } from '../../styles/theme';

interface PageHeaderProps {
  title: string;
  description?: string;
  extra?: ReactNode;
  actions?: ReactNode;
  autoRefresh?: boolean;
  onRefresh?: () => void;
  loading?: boolean;
}

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
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: theme.spacing[6],
        padding: theme.spacing[0],
      }}
    >
      <div>
        <h1
          style={{
            margin: 0,
            fontSize: theme.font.size['2xl'],
            fontWeight: theme.font.weight.semibold,
            color: theme.colors.text.primary,
            letterSpacing: theme.font.tracking.tight,
            lineHeight: 1.3,
          }}
        >
          {title}
        </h1>
        {description && (
          <p
            style={{
              margin: `${theme.spacing[2]}px 0 0`,
              fontSize: theme.font.size.base,
              color: theme.colors.text.secondary,
              lineHeight: 1.5,
            }}
          >
            {description}
          </p>
        )}
      </div>
      <Space size={12} align="center">
        {autoRefresh !== undefined && onRefresh && (
          <>
            <span style={{ fontSize: theme.font.size.sm, color: theme.colors.text.tertiary }}>
              自动刷新
            </span>
            <Switch
              checked={autoRefresh}
              onChange={() => {}}
              size="small"
            />
          </>
        )}
        {onRefresh && (
          <Button
            onClick={onRefresh}
            loading={loading}
            icon={<RotateCcw size={14} />}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            刷新
          </Button>
        )}
        {extra}
        {actions}
      </Space>
    </div>
  );
};

export default PageHeader;
