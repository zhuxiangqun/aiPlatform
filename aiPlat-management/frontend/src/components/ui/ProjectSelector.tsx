import React, { useEffect, useState } from 'react';

interface Project {
  project_id: string;
  name: string;
}

interface Props {
  value: string;
  onChange: (projectId: string) => void;
}

const ProjectSelector: React.FC<Props> = ({ value, onChange }) => {
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    fetch('/api/platform/builder/projects')
      .then(r => r.json())
      .then(d => setProjects(d.projects || []))
      .catch(() => {});
  }, []);

  if (projects.length === 0) return null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
      <span style={{ fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>📂 项目</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          flex: 1, maxWidth: 280,
          background: '#1e293b', border: '1px solid #374151', borderRadius: 6,
          padding: '6px 10px', color: '#e2e8f0', fontSize: 13, outline: 'none',
        }}
      >
        <option value="">-- 全部项目 --</option>
        {projects.map(p => (
          <option key={p.project_id} value={p.project_id}>{p.name}</option>
        ))}
      </select>
      {!value && (
        <span style={{ fontSize: 11, color: '#64748b' }}>选择项目以筛选数据</span>
      )}
    </div>
  );
};

export default ProjectSelector;
