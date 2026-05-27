import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { RefreshCw, Activity } from 'lucide-react';

interface HealthCardProps {
  title: string;
  score: number;
  details: { label: string; value: string | number }[];
  loading?: boolean;
  onRefresh?: () => void;
}

const HealthCard: React.FC<HealthCardProps> = ({ title, score, details, loading, onRefresh }) => {
  const color = score >= 85 ? 'text-green-400' : score >= 70 ? 'text-yellow-400' : 'text-red-400';
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">{title}</span>
          {onRefresh && <Button variant="ghost" size="sm" onClick={onRefresh} loading={loading}><RefreshCw className="w-3 h-3" /></Button>}
        </div>
      </CardHeader>
      <CardContent>
        <div className={`text-3xl font-bold ${color} mb-3`}>{score}</div>
        <div className="space-y-1">
          {details.map((d, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-gray-500">{d.label}</span>
              <span className="text-gray-300">{d.value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

const WikiHealthDashboard: React.FC = () => {
  const [lint, setLint] = useState<any>(null);
  const [lintLoading, setLintLoading] = useState(false);

  const fetchLint = async () => {
    setLintLoading(true);
    try { const r = await fetch('/api/core/wiki/lint'); setLint(await r.json()); } catch {}
    finally { setLintLoading(false); }
  };

  useEffect(() => { fetchLint(); }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Activity className="w-4 h-4 text-primary" />
        <h1 className="text-lg font-semibold text-gray-100">Wiki 知识库健康</h1>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <HealthCard
          title="Wiki 知识库"
          score={lint?.health_score ?? '—'}
          details={[
            { label: '页面数', value: lint?.total_pages ?? '—' },
            { label: '死链', value: lint?.stats?.dead_links ?? '—' },
            { label: '孤立页面', value: lint?.stats?.orphan_pages ?? '—' },
            { label: '矛盾', value: lint?.stats?.contradictions ?? '—' },
          ]}
          loading={lintLoading}
          onRefresh={fetchLint}
        />
      </div>

      {/* Wiki Checks Detail */}
      {lint?.checks && lint.checks.length > 0 && (
        <Card>
          <CardHeader><div className="text-sm font-medium text-gray-200">检查明细</div></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
              {lint.checks.map((chk: any, idx: number) => (
                <div key={idx} className={`p-2 rounded border text-xs ${chk.pass ? 'border-green-900/40 bg-green-900/10' : 'border-yellow-900/40 bg-yellow-900/10'}`}>
                  <div className="flex items-center gap-1.5">
                    <span className={chk.pass ? 'text-green-400' : 'text-yellow-400'}>{chk.pass ? '✓' : '!'}</span>
                    <span className="text-gray-300">{chk.name}</span>
                  </div>
                  <div className={`ml-4 text-[10px] ${chk.pass ? 'text-green-500' : 'text-yellow-500'}`}>
                    {chk.pass ? '通过' : `${chk.count} 个问题`}
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

export default WikiHealthDashboard;
