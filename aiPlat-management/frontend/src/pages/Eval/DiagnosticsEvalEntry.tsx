/**
 * E6 soft redirect: /diagnostics/eval → /eval?tab=agents
 * Escape hatch: ?legacy=1 keeps the old dashboard.
 */
import { Navigate, useSearchParams } from 'react-router-dom';
import DiagnosticsEvalDashboard from '../Diagnostics/EvalDashboard';

const DiagnosticsEvalEntry: React.FC = () => {
  const [params] = useSearchParams();
  if (params.get('legacy') === '1') {
    return <DiagnosticsEvalDashboard />;
  }
  return <Navigate to="/eval?tab=agents" replace />;
};

export default DiagnosticsEvalEntry;
