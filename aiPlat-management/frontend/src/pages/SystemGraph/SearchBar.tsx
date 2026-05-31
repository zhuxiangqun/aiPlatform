import React, { useState, useMemo } from 'react';
import { Search } from 'lucide-react';

interface Props {
  query: string;
  onQueryChange: (q: string) => void;
  graphData: any;
  onNodeSelect: (id: string) => void;
  tab: 'code' | 'capability' | 'wiki' | 'architecture';
}

const SearchBar: React.FC<Props> = ({ query, onQueryChange, graphData, onNodeSelect }) => {
  const [focused, setFocused] = useState(false);

  const results = useMemo(() => {
    if (!query || query.length < 2 || !graphData?.nodes) return [];
    const q = query.toLowerCase();
    return graphData.nodes
      .filter((n: any) =>
        n.name?.toLowerCase().includes(q) ||
        n.fullName?.toLowerCase().includes(q)
      )
      .slice(0, 10);
  }, [query, graphData]);

  return (
    <div className="relative">
      <div className={`flex items-center gap-1 px-2 py-1 rounded border transition-colors ${
        focused ? 'border-primary/50 bg-dark-bg' : 'border-dark-border bg-dark-bg/50'
      }`}>
        <Search className="w-3 h-3 text-gray-500" />
        <input
          type="text"
          value={query}
          onChange={e => onQueryChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 200)}
          placeholder="搜索节点..."
          className="bg-transparent text-xs text-gray-200 outline-none w-32 placeholder-gray-600"
        />
        {query && (
          <button onClick={() => onQueryChange('')} className="text-gray-500 text-[10px]">×</button>
        )}
      </div>
      {focused && results.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-72 max-h-48 overflow-y-auto bg-dark-card border border-dark-border rounded-lg shadow-lg z-20">
          {results.map((n: any) => (
            <button
              key={n.id}
              onClick={() => { onNodeSelect(n.id); onQueryChange(''); }}
              className="w-full text-left px-2 py-1.5 text-xs text-gray-300 hover:bg-dark-hover flex items-center gap-2"
            >
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: n.itemStyle?.color || '#6b7280' }} />
              <span className="truncate">{n.name}</span>
              <span className="text-[10px] text-gray-600 ml-auto">{n.category}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchBar;
