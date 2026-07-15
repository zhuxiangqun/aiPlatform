import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader } from '../../components/ui';
import { FileText, CheckCircle, XCircle, Archive } from 'lucide-react';

interface HistoryItem {
  id: string;
  name: string;
  type: string;
  status: string;
  description: string;
}

const typeLabels: Record<string, string> = { agent: 'Agent', skill: 'Skill' };
const statusLabels: Record<string, string> = { published: '已发布', listed: '已上架', deprecated: '已废弃' };
const statusIcons: Record<string, React.ReactNode> = {
  published: <CheckCircle className="w-3 h-3 text-green-400" />,
  listed: <CheckCircle className="w-3 h-3 text-blue-400" />,
  deprecated: <Archive className="w-3 h-3 text-gray-400" />,
};

const ApprovalHistory: React.FC = () => {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/approval/history?limit=50')
      .then(r => r.json())
      .then(d => setItems(d.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4 p-4">
      <h1 className="text-lg font-semibold text-gray-100">审批记录</h1>
      {loading ? (
        <div className="text-gray-500 text-sm">加载中…</div>
      ) : items.length === 0 ? (
        <div className="text-gray-500 text-sm">暂无审批记录</div>
      ) : (
        <Card>
          <CardHeader>
            <span className="text-sm font-medium">最近 {items.length} 条记录</span>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {items.map((item, i) => (
                <div key={i} className="flex items-center justify-between py-2 px-2 bg-gray-800/50 rounded text-xs">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-gray-500 w-10">{typeLabels[item.type] || item.type}</span>
                    <span className="text-gray-300 truncate">{item.name}</span>
                    <span className="text-gray-600 truncate hidden sm:inline">{item.description}</span>
                  </div>
                  <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                    {statusIcons[item.status]}
                    <span className={`${
                      item.status === 'published' ? 'text-green-400' :
                      item.status === 'listed' ? 'text-blue-400' : 'text-gray-500'
                    }`}>
                      {statusLabels[item.status] || item.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ApprovalHistory;
