import { useState, useEffect, useCallback } from 'react';

export function useProjectId() {
  const [projectId, setProjectId] = useState<string>(() => localStorage.getItem('diag_project_id') || '');

  useEffect(() => {
    if (projectId) localStorage.setItem('diag_project_id', projectId);
    else localStorage.removeItem('diag_project_id');
  }, [projectId]);

  const reset = useCallback(() => setProjectId(''), []);

  return { projectId, setProjectId, reset };
}
