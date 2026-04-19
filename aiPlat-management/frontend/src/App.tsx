import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { Loader2 } from 'lucide-react';
import AppLayout from './components/layout/AppLayout';
import './index.css';
import './styles/tokens.css';

const Loading = () => (
  <div className="flex items-center justify-center min-h-screen bg-dark-bg">
    <Loader2 className="w-8 h-8 text-primary animate-spin" />
  </div>
);

const withSuspense = (Component: React.LazyExoticComponent<React.FC>) => (
  <Suspense fallback={<Loading />}>
    <Component />
  </Suspense>
);

const Overview = lazy(() => import('./pages/Overview/Overview'));
const Alerts = lazy(() => import('./pages/Alerts/Alerts'));
const InfraNodes = lazy(() => import('./pages/Infra/Nodes/Nodes'));
const InfraModels = lazy(() => import('./pages/Infra/Models/Models'));
const InfraServices = lazy(() => import('./pages/Infra/Services/Services'));
const InfraScheduler = lazy(() => import('./pages/Infra/Scheduler/Scheduler'));
const InfraStorage = lazy(() => import('./pages/Infra/Storage/Storage'));
const InfraNetwork = lazy(() => import('./pages/Infra/Network/Network'));
const InfraMonitoring = lazy(() => import('./pages/Infra/Monitoring/Monitoring'));
const CoreAgents = lazy(() => import('./pages/Core/Agents/Agents'));
const CoreSkills = lazy(() => import('./pages/Core/Skills/Skills'));
const CoreTools = lazy(() => import('./pages/Core/Tools/Tools'));
const CoreMCP = lazy(() => import('./pages/Core/MCP/MCP'));
const CoreMemory = lazy(() => import('./pages/Core/Memory/Memory'));
const CoreJobs = lazy(() => import('./pages/Core/Jobs/Jobs'));
const CoreSkillPacks = lazy(() => import('./pages/Core/SkillPacks'));
const WorkspaceAgents = lazy(() => import('./pages/Workspace/Agents/Agents'));
const WorkspaceSkills = lazy(() => import('./pages/Workspace/Skills/Skills'));
const WorkspaceMCP = lazy(() => import('./pages/Workspace/MCP/MCP'));
const CoreLearningArtifacts = lazy(() => import('./pages/Core/Learning/Artifacts'));
const CoreLearningArtifactDetail = lazy(() => import('./pages/Core/Learning/Artifacts/ArtifactDetail'));
const CoreApprovals = lazy(() => import('./pages/Core/Learning/Approvals'));
const CoreReleases = lazy(() => import('./pages/Core/Learning/Releases'));
const PlatformGateway = lazy(() => import('./pages/Platform/Gateway/Gateway'));
const PlatformAuth = lazy(() => import('./pages/Platform/Auth/Auth'));
const PlatformTenant = lazy(() => import('./pages/Platform/Tenant/Tenant'));
const AppChannels = lazy(() => import('./pages/App/Channels/Channels'));
const AppSessions = lazy(() => import('./pages/App/Sessions/Sessions'));
const DiagnosticsHome = lazy(() => import('./pages/Diagnostics/Diagnostics'));
const DiagnosticsTraces = lazy(() => import('./pages/Diagnostics/Traces/Traces'));
const DiagnosticsTraceDetail = lazy(() => import('./pages/Diagnostics/Traces/TraceDetail'));
const DiagnosticsGraphs = lazy(() => import('./pages/Diagnostics/Graphs/Graphs'));
const DiagnosticsGraphRunDetail = lazy(() => import('./pages/Diagnostics/Graphs/GraphRunDetail'));
const DiagnosticsLinks = lazy(() => import('./pages/Diagnostics/Links/Links'));
const DiagnosticsRuns = lazy(() => import('./pages/Diagnostics/Runs/Runs'));
const DiagnosticsAudit = lazy(() => import('./pages/Diagnostics/Audit/Audit'));
const DiagnosticsPolicies = lazy(() => import('./pages/Diagnostics/Policies/Policies'));
const DiagnosticsSyscalls = lazy(() => import('./pages/Diagnostics/Syscalls'));
const DiagnosticsSmoke = lazy(() => import('./pages/Diagnostics/Smoke/Smoke'));
const Onboarding = lazy(() => import('./pages/Onboarding/Onboarding'));

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: withSuspense(Overview) },
      { path: 'overview', element: withSuspense(Overview) },
      { path: 'alerts', element: withSuspense(Alerts) },
      { path: 'onboarding', element: withSuspense(Onboarding) },
      { path: 'infra/nodes', element: withSuspense(InfraNodes) },
      { path: 'infra/models', element: withSuspense(InfraModels) },
      { path: 'infra/services', element: withSuspense(InfraServices) },
      { path: 'infra/scheduler', element: withSuspense(InfraScheduler) },
      { path: 'infra/storage', element: withSuspense(InfraStorage) },
      { path: 'infra/network', element: withSuspense(InfraNetwork) },
      { path: 'infra/monitoring', element: withSuspense(InfraMonitoring) },
      { path: 'core/agents', element: withSuspense(CoreAgents) },
      { path: 'core/skills', element: withSuspense(CoreSkills) },
      { path: 'core/tools', element: withSuspense(CoreTools) },
      { path: 'core/mcp', element: withSuspense(CoreMCP) },
      { path: 'core/memory', element: withSuspense(CoreMemory) },
      { path: 'core/skill-packs', element: withSuspense(CoreSkillPacks) },
      { path: 'core/jobs', element: withSuspense(CoreJobs) },
      { path: 'workspace/agents', element: withSuspense(WorkspaceAgents) },
      { path: 'workspace/skills', element: withSuspense(WorkspaceSkills) },
      { path: 'workspace/mcp', element: withSuspense(WorkspaceMCP) },
      { path: 'core/learning/artifacts', element: withSuspense(CoreLearningArtifacts) },
      { path: 'core/learning/artifacts/:artifactId', element: withSuspense(CoreLearningArtifactDetail) },
      { path: 'core/learning/releases', element: withSuspense(CoreReleases) },
      { path: 'core/approvals', element: withSuspense(CoreApprovals) },
      { path: 'platform/gateway', element: withSuspense(PlatformGateway) },
      { path: 'platform/auth', element: withSuspense(PlatformAuth) },
      { path: 'platform/tenant', element: withSuspense(PlatformTenant) },
      { path: 'app/channels', element: withSuspense(AppChannels) },
      { path: 'app/sessions', element: withSuspense(AppSessions) },
      { path: 'diagnostics', element: withSuspense(DiagnosticsHome) },
      { path: 'diagnostics/traces', element: withSuspense(DiagnosticsTraces) },
      { path: 'diagnostics/traces/:traceId', element: withSuspense(DiagnosticsTraceDetail) },
      { path: 'diagnostics/graphs', element: withSuspense(DiagnosticsGraphs) },
      { path: 'diagnostics/graphs/:runId', element: withSuspense(DiagnosticsGraphRunDetail) },
      { path: 'diagnostics/links', element: withSuspense(DiagnosticsLinks) },
      { path: 'diagnostics/runs', element: withSuspense(DiagnosticsRuns) },
      { path: 'diagnostics/audit', element: withSuspense(DiagnosticsAudit) },
      { path: 'diagnostics/policies', element: withSuspense(DiagnosticsPolicies) },
      { path: 'diagnostics/syscalls', element: withSuspense(DiagnosticsSyscalls) },
      { path: 'diagnostics/smoke', element: withSuspense(DiagnosticsSmoke) },
    ],
  },
]);

const App: React.FC = () => {
  return <RouterProvider router={router} future={{ v7_startTransition: true }} />;
};

export default App;
