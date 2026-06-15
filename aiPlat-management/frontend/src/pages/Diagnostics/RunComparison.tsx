import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowLeftRight, Play, Search } from 'lucide-react';
import { ExecutionViewer } from '../../components/ExecutionViewer';
import { Card, CardContent, Button, Input, toast } from '../../components/ui';

const RunComparison: React.FC = () => {
  const [runIdA, setRunIdA] = useState('');
  const [runIdB, setRunIdB] = useState('');
  const [comparing, setComparing] = useState(false);

  const startCompare = useCallback(() => {
    const a = runIdA.trim();
    const b = runIdB.trim();
    if (!a || !b) {
      toast.error('请输入两个 Run ID');
      return;
    }
    if (a === b) {
      toast.error('两个 Run ID 不能相同');
      return;
    }
    setComparing(true);
  }, [runIdA, runIdB]);

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400, color: '#e5e7eb' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <ArrowLeftRight size={22} color="#8b5cf6" />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Run 对比</h1>
      </div>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      <Card className="border-dark-border bg-dark-card" {...({ style: { marginBottom: 20 } } as any)}>
        <CardContent>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>Run ID A</div>
              <Input
                placeholder="输入 Run ID..."
                value={runIdA}
                onChange={e => setRunIdA(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', color: '#8b5cf6', fontSize: 18, paddingTop: 16 }}>
              <ArrowLeftRight size={20} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>Run ID B</div>
              <Input
                placeholder="输入 Run ID..."
                value={runIdB}
                onChange={e => setRunIdB(e.target.value)}
              />
            </div>
            <div style={{ paddingTop: 16 }}>
              <Button variant="primary" onClick={startCompare} icon={<Play size={14} />}>
                对比
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {comparing && (
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
        }}>
          <div>
            <ExecutionViewer
              title={`Run A: ${runIdA.slice(0, 12)}...`}
              replayRunId={runIdA}
              height={550}
            />
          </div>
          <div>
            <ExecutionViewer
              title={`Run B: ${runIdB.slice(0, 12)}...`}
              replayRunId={runIdB}
              height={550}
            />
          </div>
        </div>
      )}
      {!comparing && (
        <div style={{
          textAlign: 'center', padding: 60, color: '#6b7280',
          border: '1px dashed #374151', borderRadius: 12, background: '#1f2937',
        }}>
          <Search size={32} style={{ marginBottom: 12, opacity: 0.3 }} />
          <div style={{ fontSize: 14 }}>输入两个 Run ID 并点击"对比"开始</div>
        </div>
      )}
    </div>
  );
};

export default RunComparison;
