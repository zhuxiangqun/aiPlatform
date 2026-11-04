/**
 * Compat redirect: /diagnostics/eval → /eval?tab=agents
 * Forwards ?agent=…; escape hatch ?legacy=1 keeps the old dashboard.
 */
import { Navigate, useSearchParams } from 'react-router-dom';
import DiagnosticsEvalDashboard from '../Diagnostics/EvalDashboard';

const DiagnosticsEvalEntry: React.FC = () => {
  const [params] = useSearchParams();
  if (params.get('legacy') === '1') {
    return <DiagnosticsEvalDashboard />;
  }
  const next = new URLSearchParams();
  next.set('tab', 'agents');
  const agent = (params.get('agent') || '').trim();
  if (agent) next.set('agent', agent);
  return <Navigate to={`/eval?${next.toString()}`} replace />;
};

export default DiagnosticsEvalEntry;
