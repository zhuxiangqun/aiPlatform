import React from 'react';

interface Column<T> {
  key: string;
  title: string;
  dataIndex?: string;
  render?: (value: any, record: T, index: number) => React.ReactNode;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: keyof T | ((record: T) => string);
  loading?: boolean;
  emptyText?: string;
  onRow?: (record: T) => { onClick?: () => void; className?: string };
  expandedRowKeys?: string[];
  expandedRowRender?: (record: T, index: number) => React.ReactNode;
  className?: string;
}

function getNestedValue<T>(obj: T, path: string[]): unknown {
  let current: unknown = obj;
  for (const key of path) {
    if (current && typeof current === 'object' && key in current) {
      current = (current as Record<string, unknown>)[key];
    } else {
      return undefined;
    }
  }
  return current;
}

export function Table<T>({
  columns,
  data,
  rowKey,
  loading,
  emptyText = '暂无数据',
  onRow,
  expandedRowKeys,
  expandedRowRender,
  className = '',
}: TableProps<T>) {
  const getRowKey = (record: T, index: number): string => {
    if (typeof rowKey === 'function') {
      return rowKey(record);
    }
    const value = record[rowKey];
    return String(value ?? index);
  };

  const renderCell = (column: Column<T>, record: T, index: number) => {
    if (column.render) {
      const value = column.dataIndex
        ? getNestedValue(record, Array.isArray(column.dataIndex) ? column.dataIndex : [column.dataIndex as string])
        : undefined;
      return column.render(value, record, index);
    }
    if (column.dataIndex) {
      const value = getNestedValue(record, Array.isArray(column.dataIndex) ? column.dataIndex : [column.dataIndex as string]);
      return String(value ?? '-');
    }
    return '-';
  };

  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full">
        <thead>
          <tr className="bg-dark-bg border-b border-dark-border">
            {columns.map((column) => (
              <th
                key={column.key}
                className={`
                  px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide
                  ${column.align === 'center' ? 'text-center' : column.align === 'right' ? 'text-right' : 'text-left'}
                `}
                style={{ width: column.width }}
              >
                {column.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-12 text-center">
                <div className="flex justify-center">
                  <svg className="animate-spin h-6 w-6 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                </div>
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-12 text-center text-gray-400">
                {emptyText}
              </td>
            </tr>
          ) : (
            data.map((record, index) => {
              const rowProps = onRow?.(record);
              const k = getRowKey(record, index);
              const expanded = !!(expandedRowKeys && expandedRowKeys.includes(k) && expandedRowRender);
              return (
                <React.Fragment key={k}>
                  <tr
                    className={`
                      border-b border-dark-border
                      hover:bg-dark-hover transition-colors
                      ${rowProps?.className || ''}
                    `}
                    onClick={rowProps?.onClick}
                    style={{ cursor: rowProps?.onClick ? 'pointer' : 'default' }}
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={`
                          px-4 py-3 text-sm text-gray-200
                          ${column.align === 'center' ? 'text-center' : column.align === 'right' ? 'text-right' : 'text-left'}
                        `}
                      >
                        {renderCell(column, record, index)}
                      </td>
                    ))}
                  </tr>
                  {expanded && (
                    <tr className="border-b border-dark-border bg-dark-bg">
                      <td colSpan={columns.length} className="px-4 py-3">
                        {expandedRowRender ? expandedRowRender(record, index) : null}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export default Table;
