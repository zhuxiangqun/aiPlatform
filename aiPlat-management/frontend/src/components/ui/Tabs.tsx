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
  const [activeTab, setActiveTab] = useState(defaultActiveKey || tabs[0]?.key);

  const handleTabClick = (key: string) => {
    setActiveTab(key);
    onChange?.(key);
  };

  return (
    <div className={className}>
      <div className="flex border-b border-gray-200">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleTabClick(tab.key)}
            className={`
              relative px-4 py-2.5 text-sm font-medium transition-colors
              ${activeTab === tab.key
                ? 'text-primary'
                : 'text-gray-500 hover:text-gray-700'
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
      <div className="mt-4">
        {tabs.find((tab) => tab.key === activeTab)?.children}
      </div>
    </div>
  );
};

export default Tabs;
