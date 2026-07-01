import React, { useState, useEffect } from 'react';

const TrainingMonitor: React.FC = () => {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const res = await fetch('/api/core/workbench/training/status');
      const d = await res.json();
      setStatus(d);
    } catch {}
    setLoading(false);
  };

  if (loading) return <div style={{ padding: 24, color: '#94a3b8' }}>加载中...</div>;

  const sftThreshold = status?.threshold || 100;
  const sftMinQuality = status?.quality_threshold || 0.8;
  const sftEnabled = status?.enabled ?? true;
  const qualityCount = status?.quality_count || 0;
  const approvedTotal = status?.approved_total || 0;
  const datasetCount = status?.dataset_count || 0;
  const latestModel = status?.latest_model || '';
  const readyToTrigger = status?.ready_to_trigger || false;

  const pct = sftThreshold > 0 ? Math.min(100, Math.round((qualityCount / sftThreshold) * 100)) : 0;

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2 style={{ fontSize: 20, margin: '0 0 4px', color: '#f1f5f9' }}>SFT/RL 训练监控</h2>
      <div style={{ fontSize: 13, color: '#64748b', marginBottom: 20 }}>
        自动微调管线状态
      </div>

      {/* Status cards */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
        {[
          { label: '启用状态', value: sftEnabled ? '运行中' : '已暂停', color: sftEnabled ? '#22c55e' : '#ef4444' },
          { label: '总审批数', value: `${approvedTotal} 条`, color: '#a855f7' },
          { label: '触发阈值', value: `${sftThreshold} 条`, color: '#3b82f6' },
          { label: '最低质量', value: `≥ ${sftMinQuality}`, color: '#f1f5f9' },
        ].map((c, i) => (
          <div key={i} style={{
            flex: 1, background: '#1e293b', borderRadius: 8, padding: 12,
            border: `1px solid ${c.color}20`,
          }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>{c.label}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: c.color, marginTop: 4 }}>
              {c.value}
            </div>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div style={{
        background: '#1e293b', borderRadius: 10, padding: 20, marginBottom: 20,
        border: '1px solid #334155',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 14, color: '#f1f5f9', fontWeight: 600 }}>高质量样本积累</span>
          <span style={{ fontSize: 13, color: '#94a3b8' }}>
            {qualityCount} / {sftThreshold} · {pct}%
          </span>
        </div>
        <div style={{ height: 10, background: '#0f172a', borderRadius: 5, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${pct}%`,
            background: pct >= 80 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#3b82f6',
            borderRadius: 5, transition: 'width 0.5s',
          }} />
        </div>
        <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
          {readyToTrigger
            ? '已达到触发阈值，等待 EvolutionEngine 夜间触发训练'
            : `距自动触发还需 ${sftThreshold - qualityCount} 条高质量样本`
          }
        </div>
      </div>

      {/* Pipeline info */}
      <div style={{
        background: '#1e293b', borderRadius: 10, padding: 20, marginBottom: 20,
        border: '1px solid #334155',
      }}>
        <h3 style={{ fontSize: 15, margin: '0 0 16px', color: '#f1f5f9' }}>训练管线流程</h3>
        <div style={{ display: 'flex', gap: 0, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
          {[
            { label: '用户反馈', desc: 'ImplicitFeedback' },
            { label: 'AutoLearner', desc: '审批 ≥ 0.8' },
            { label: 'TrajectoryScorer', desc: '可模仿性过滤' },
            { label: 'ShareGPT', desc: '数据集生成' },
            { label: '分层分割', desc: '15% 验证集' },
            { label: 'LoRA 训练', desc: '自动提交 Job' },
            { label: 'SFT→RL 桥接', desc: 'latest.json 信号' },
          ].map((step, i) => (
            <React.Fragment key={i}>
              <div style={{
                background: '#0f172a', borderRadius: 6, padding: '8px 12px',
                textAlign: 'center', minWidth: 90,
                border: '1px solid #334155',
              }}>
                <div style={{ color: '#3b82f6', fontWeight: 600, fontSize: 12 }}>{step.label}</div>
                <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>{step.desc}</div>
              </div>
              {i < 6 && <span style={{ color: '#334155', margin: '0 2px', fontSize: 16 }}>→</span>}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Latest model */}
      <div style={{
        background: '#1e293b', borderRadius: 10, padding: 20,
        border: '1px solid #334155',
      }}>
        <h3 style={{ fontSize: 15, margin: '0 0 8px', color: '#f1f5f9' }}>最新 SFT 模型</h3>
        <div style={{ fontSize: 13, color: '#94a3b8' }}>
          模型文件目录: ~/.aiplat/training/
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12 }}>
          <div style={{ flex: 1, background: '#0f172a', borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>训练数据集</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#f1f5f9', marginTop: 2 }}>{datasetCount} 个</div>
          </div>
          <div style={{ flex: 1, background: '#0f172a', borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>最新模型</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#f1f5f9', marginTop: 2 }}>
              {latestModel || '—'}
            </div>
          </div>
          <div style={{ flex: 1, background: '#0f172a', borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 11, color: '#64748b' }}>RL 状态</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: latestModel ? '#22c55e' : '#94a3b8', marginTop: 2 }}>
              {latestModel ? 'SFT 模型就绪' : '待 SFT 完成'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TrainingMonitor;
