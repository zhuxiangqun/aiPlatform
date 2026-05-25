import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, Input, toast } from '../../components/ui';

interface Release {
  version: string;
  date: string;
  commit: string;
  message: string;
}

const ReleasesPage: React.FC = () => {
  const [version, setVersion] = useState('');
  const [message, setMessage] = useState('');
  const [releases, setReleases] = useState<Release[]>([]);

  const fetchReleases = useCallback(async () => {
    try {
      const res = await fetch('/api/releases');
      const data = await res.json();
      setReleases(data.releases || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchReleases(); }, [fetchReleases]);

  const handleRelease = async () => {
    if (!version) { toast.error('请输入版本号'); return; }
    try {
      const params = new URLSearchParams({ version });
      if (message) params.set('message', message);
      const res = await fetch('/api/releases?' + params.toString(), { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        toast.success('版本 ' + version + ' 发布成功');
        setVersion(''); setMessage('');
        fetchReleases();
      } else {
        toast.error(data.detail || '发布失败');
      }
    } catch { toast.error('发布失败'); }
  };

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <h2 style={{ margin: 0 }}>版本管理</h2>
      <p style={{ color: '#888', margin: '4px 0 20px' }}>版本标记与管理</p>

      <Card>
        <CardHeader title="📦 标记版本" />
        <CardContent>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Input value={version} onChange={e => setVersion(e.target.value)}
              placeholder="版本号 (如 v1.3.0)" />
            <Input value={message} onChange={e => setMessage(e.target.value)}
              placeholder="发布说明 (可选)" />
            <Button variant="primary" onClick={handleRelease}>发布</Button>
          </div>
        </CardContent>
      </Card>

      <div style={{ marginTop: 16 }}>
        <Card>
          <CardHeader title="📋 版本列表" />
          <CardContent>
            {releases.length === 0 ? (
              <div style={{ color: '#666', padding: 20, textAlign: 'center' }}>暂无版本</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #333', color: '#888', fontSize: 13, textAlign: 'left' }}>
                    <th style={{ padding: '8px 12px' }}>#</th>
                    <th style={{ padding: '8px 12px' }}>版本</th>
                    <th style={{ padding: '8px 12px' }}>日期</th>
                    <th style={{ padding: '8px 12px' }}>Commit</th>
                    <th style={{ padding: '8px 12px' }}>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {releases.map((r, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #1a1a2e', color: '#ccc', fontSize: 13 }}>
                      <td style={{ padding: '8px 12px' }}>{i + 1}</td>
                      <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#4fc3f7' }}>{r.version}</td>
                      <td style={{ padding: '8px 12px' }}>{r.date}</td>
                      <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 11 }}>{r.commit}</td>
                      <td style={{ padding: '8px 12px' }}>{r.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default ReleasesPage;
