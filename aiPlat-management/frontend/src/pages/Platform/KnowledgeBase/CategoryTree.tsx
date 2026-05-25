import React from 'react';
import type { KBCategory } from '../../../services';

interface Props {
  contentCategories: KBCategory[];
  activeCategory: string;
  onSelect: (key: string) => void;
}

export const CategoryTree: React.FC<Props> = ({ contentCategories, activeCategory, onSelect }) => {
  return (
    <div className="flex gap-1.5 flex-wrap">
      <button onClick={() => onSelect('all')}
        className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
          activeCategory === 'all' ? 'bg-primary/20 text-primary font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-dark-hover'
        }`}>
        全部文档
      </button>
      {contentCategories.map((cat) => (
        <button key={cat.key} onClick={() => onSelect(cat.key)}
          className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
            activeCategory === cat.key ? 'bg-primary/20 text-primary font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-dark-hover'
          }`}>
          {cat.label} {cat.count > 0 && <span className="text-[10px] opacity-50">{cat.count}</span>}
        </button>
      ))}
    </div>
  );
};
