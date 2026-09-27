import React, { useEffect, useMemo, useRef, useState } from 'react';

interface MultiSelectProps {
  label: string;
  options: Array<{ value: string; label: string }>;
  selected: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  hint?: string;
  /** Max unselected rows shown in the picker list (default 12). */
  listLimit?: number;
}

export const MultiSelect: React.FC<MultiSelectProps> = ({
  label,
  options = [],
  selected = [],
  onChange,
  placeholder,
  hint,
  listLimit = 12,
}) => {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const opts = Array.isArray(options) ? options : [];
  const sel = Array.isArray(selected) ? selected : [];

  const selectedSet = useMemo(() => new Set(sel), [sel]);
  const optionMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of opts) m.set(o.value, o.label);
    return m;
  }, [opts]);

  const selectedItems = useMemo(
    () =>
      sel.map((value) => ({
        value,
        label: optionMap.get(value) || `${value}（未在列表中找到）`,
      })),
    [sel, optionMap],
  );

  const toggle = (value: string) => {
    if (selectedSet.has(value)) {
      onChange(sel.filter((v) => v !== value));
    } else {
      onChange([...sel, value]);
    }
  };

  const filteredUnselected = useMemo(() => {
    const q = search.trim().toLowerCase();
    return opts
      .filter((o) => !selectedSet.has(o.value))
      .filter(
        (o) =>
          !q ||
          o.label.toLowerCase().includes(q) ||
          o.value.toLowerCase().includes(q),
      );
  }, [opts, selectedSet, search]);

  const visible = filteredUnselected.slice(0, listLimit);
  const hiddenCount = Math.max(0, filteredUnselected.length - visible.length);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-gray-300">{label}</span>
        <span className="text-[10px] text-gray-500">
          已选 {sel.length}
          {opts.length ? ` · 可选 ${opts.length}` : ''}
        </span>
      </div>

      {selectedItems.length > 0 ? (
        <div className="flex flex-wrap gap-1 mb-2 max-h-24 overflow-y-auto">
          {selectedItems.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => toggle(o.value)}
              title="点击移除"
              className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-xs font-medium bg-primary/15 text-primary border border-primary/25 hover:bg-primary/25 transition-colors"
            >
              <span className="truncate max-w-[220px]">{o.label}</span>
              <span className="text-[10px] opacity-60 ml-0.5">×</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="text-xs text-gray-600 mb-2">尚未选择</div>
      )}

      <div className="relative">
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder || `搜索并添加…（共 ${opts.length} 项）`}
          className="w-full h-8 px-2.5 text-xs bg-dark-card border border-dark-border rounded-lg focus:border-primary/50 focus:outline-none text-gray-200 placeholder-gray-600"
        />
        {open && (
          <div className="absolute z-30 left-0 right-0 mt-1 rounded-lg border border-dark-border bg-dark-card shadow-xl max-h-56 overflow-y-auto">
            {visible.length > 0 ? (
              <>
                {visible.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => {
                      toggle(o.value);
                      setSearch('');
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover hover:text-gray-100 border-b border-dark-border/40 last:border-0"
                    title={o.value}
                  >
                    <span className="text-primary/80 mr-1">+</span>
                    {o.label}
                  </button>
                ))}
                {hiddenCount > 0 && (
                  <div className="px-3 py-1.5 text-[10px] text-gray-500">
                    还有 {hiddenCount} 项，继续输入关键词筛选
                  </div>
                )}
              </>
            ) : (
              <div className="px-3 py-2 text-xs text-gray-500">
                {search.trim() ? '无匹配结果' : '全部已选或无可选项'}
              </div>
            )}
          </div>
        )}
      </div>

      {hint && <div className="text-[10px] text-gray-600 mt-1">{hint}</div>}
    </div>
  );
};
