/**
 * Compat redirect only: /diagnostics/eval → /eval?tab=agents
 * Forwards ?agent=… . No standalone legacy page — Agents UI lives in EvalCenter.
 */
import { Navigate, useSearchParams } from 'react-router-dom';

const DiagnosticsEvalEntry: React.FC = () => {
  const [params] = useSearchParams();
  const next = new URLSearchParams();
  next.set('tab', 'agents');
  const agent = (params.get('agent') || '').trim();
  if (agent) next.set('agent', agent);
  return <Navigate to={`/eval?${next.toString()}`} replace />;
};

export default DiagnosticsEvalEntry;
