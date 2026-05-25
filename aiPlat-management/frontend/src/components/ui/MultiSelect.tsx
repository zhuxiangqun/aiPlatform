import React, { useMemo, useState } from 'react';

interface MultiSelectProps {
  label: string;
  options: Array<{ value: string; label: string }>;
  selected: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  hint?: string;
}

export const MultiSelect: React.FC<MultiSelectProps> = ({
  label, options, selected, onChange, placeholder, hint,
}) => {
  const [search, setSearch] = useState('');

  const selectedSet = new Set(selected);

  const toggle = (value: string) => {
    if (selectedSet.has(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.toLowerCase();
    return options.filter((o) =>
      o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
    );
  }, [options, search]);

  const unselected = filtered.filter((o) => !selectedSet.has(o.value));

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-gray-300">{label}</span>
        {selected.length > 0 && <span className="text-[10px] text-gray-500">{selected.length} 项</span>}
      </div>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {options
            .filter((o) => selectedSet.has(o.value))
            .map((o) => (
              <button
                key={o.value}
                onClick={() => toggle(o.value)}
                title="点击移除"
                className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-xs font-medium bg-primary/15 text-primary border border-primary/25 hover:bg-primary/25 transition-colors"
              >
                {o.label}
                <span className="text-[10px] opacity-60 ml-0.5">×</span>
              </button>
            ))}
        </div>
      )}

      {options.length > 8 && (
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={placeholder || '搜索...'}
          className="w-full h-7 px-2 mb-1.5 text-xs bg-dark-card border border-dark-border rounded focus:border-primary/50 focus:outline-none text-gray-200 placeholder-gray-600"
        />
      )}

      <div className="flex flex-wrap gap-1 max-h-40 overflow-auto p-1 rounded-lg border border-dark-border bg-dark-card/50">
        {unselected.length > 0 ? (
          unselected.map((o) => (
            <button
              key={o.value}
              onClick={() => toggle(o.value)}
              title="点击添加"
              className="inline-flex items-center px-2 py-0.5 rounded text-xs text-gray-400 bg-dark-bg border border-dark-border hover:text-gray-200 hover:border-gray-600 transition-colors"
            >
              + {o.label}
            </button>
          ))
        ) : (
          <span className="text-xs text-gray-600 p-1">
            {search ? '无匹配结果' : '全部已选'}
          </span>
        )}
      </div>

      {hint && <div className="text-[10px] text-gray-600 mt-1">{hint}</div>}
    </div>
  );
};
