import React, { useState } from 'react';

interface Tab {
  key: string;
  label: string;
  children: React.ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultActiveKey?: string;
  onChange?: (key: string) => void;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  defaultActiveKey,
  onChange,
  className = '',
}) => {
  const list = Array.isArray(tabs) ? tabs : [];
  const [activeTab, setActiveTab] = useState(defaultActiveKey || list[0]?.key);

  const handleTabClick = (key: string) => {
    setActiveTab(key);
    onChange?.(key);
  };

  return (
    <div className={className}>
      <div className="flex gap-1 border-b border-dark-border overflow-x-auto">
        {list.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => handleTabClick(tab.key)}
            className={`
              relative px-3 py-2 text-sm font-medium transition-colors whitespace-nowrap
              ${activeTab === tab.key
                ? 'text-primary'
                : 'text-gray-500 hover:text-gray-300'
              }
            `}
          >
            {tab.label}
            {activeTab === tab.key && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        ))}
      </div>
      <div className="mt-3">
        {list.find((tab) => tab.key === activeTab)?.children}
      </div>
    </div>
  );
};

export default Tabs;
