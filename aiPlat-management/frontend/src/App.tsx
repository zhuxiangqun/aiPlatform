import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
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

const SystemOverview = lazy(() => import('./pages/SystemOverview/SystemOverview'));
const Alerts = lazy(() => import('./pages/Alerts/Alerts'));
const InfraNodes = lazy(() => import('./pages/Infra/Nodes/Nodes'));
const InfraModels = lazy(() => import('./pages/Infra/Models/Models'));
const InfraFineTune = lazy(() => import('./pages/Infra/FineTune/FineTune'));
const InfraOntology = lazy(() => import('./pages/Infra/Ontology/OntologyManager'));
const InfraServices = lazy(() => import('./pages/Infra/Services/Services'));
const InfraScheduler = lazy(() => import('./pages/Infra/Scheduler/Scheduler'));
const InfraStorage = lazy(() => import('./pages/Infra/Storage/Storage'));
const InfraNetwork = lazy(() => import('./pages/Infra/Network/Network'));
const InfraMonitoring = lazy(() => import('./pages/Infra/Monitoring/Monitoring'));
const LlmRouteMonitor = lazy(() => import('./pages/Infra/LlmRouteMonitor'));
const CoreAgents = lazy(() => import('./pages/Core/Agents/Agents'));
const CoreSkills = lazy(() => import('./pages/Core/Skills/Skills'));
const CoreSkillsRollouts = lazy(() => import('./pages/Core/Skills/Rollouts'));
const CorePrompts = lazy(() => import('./pages/Core/Prompts'));
const PromptApp = lazy(() => import('./pages/Prompts/AppTemplates'));
const CoreTools = lazy(() => import('./pages/Core/Tools/Tools'));
const WorkspaceTeams = lazy(() => import('./pages/App/Builder/TeamAssemblyPage'));
const CorePlugins = lazy(() => import('./pages/Core/Plugins'));
const PackagePlugins = lazy(() => import('./pages/Plugins/Plugins'));
const CoreMCP = lazy(() => import('./pages/Core/MCP/MCP'));
const WorkflowsPage = lazy(() => import('./pages/Core/Workflows/WorkflowsPage'));
const WorkflowCanvas = lazy(() => import('./pages/Builder/WorkflowCanvas'));
const WorkflowRunPage = lazy(() => import('./pages/Core/Workflows/WorkflowRunPage'));
const CoreVariables = lazy(() => import('./pages/Core/Variables/Variables'));
const CoreCredentials = lazy(() => import('./pages/Core/Credentials/Credentials'));
const CoreMemory = lazy(() => import('./pages/Core/Memory/Memory'));
const FileCheckpoints = lazy(() => import('./pages/Core/Checkpoints/FileCheckpoints'));
const CoreJobs = lazy(() => import('./pages/Core/Jobs/Jobs'));
const CoreSkillPacks = lazy(() => import('./pages/Core/SkillPacks'));
const WorkspaceAgents = lazy(() => import('./pages/Workspace/Agents/Agents'));
const WorkspaceSkills = lazy(() => import('./pages/Workspace/Skills/Skills'));
const WorkspaceSkillLint = lazy(() => import('./pages/Workspace/Skills/LintDashboard'));
const WorkspaceMarketplace = lazy(() => import('./pages/Workspace/Marketplace'));
const WorkspaceMCP = lazy(() => import('./pages/Workspace/MCP/MCP'));
const WorkspaceTools = lazy(() => import('./pages/Workspace/Tools/Tools'));
const CoreLearningArtifacts = lazy(() => import('./pages/Core/Learning/Artifacts'));
const CoreLearningArtifactDetail = lazy(() => import('./pages/Core/Learning/Artifacts/ArtifactDetail'));
const CoreApprovals = lazy(() => import('./pages/Core/Learning/Approvals'));
const CoreReleases = lazy(() => import('./pages/Core/Learning/Releases'));
const CoreLearningRollouts = lazy(() => import('./pages/Core/Learning/Rollouts'));
const PlatformGateway = lazy(() => import('./pages/Platform/Gateway/Gateway'));
const PlatformAuth = lazy(() => import('./pages/Platform/Auth/Auth'));
const PlatformTenant = lazy(() => import('./pages/Platform/Tenant/Tenant'));
const AppChannels = lazy(() => import('./pages/App/Channels/Channels'));
const AppSessions = lazy(() => import('./pages/App/Sessions/Sessions'));
const AppKnowledgeBase = lazy(() => import('./pages/Platform/KnowledgeBase'));
const AppMaterialsChat = lazy(() => import('./pages/Platform/KnowledgeBase/MaterialsChat'));
const AppTeamAssembly = lazy(() => import('./pages/App/Builder/TeamAssemblyPage'));
const AgentInsightPage = lazy(() => import('./pages/App/Builder/AgentInsightPage'));
const AppsPage = lazy(() => import('./pages/App/Builder/AppsPage'));
const AppFactory = lazy(() => import("./pages/App/AIFactory"));
const AppPage = lazy(() => import("./pages/App/AppPage"));
const AppChatPage = lazy(() => import('./pages/App/Builder/AppChatPage'));
const AppProjects = lazy(() => import('./pages/App/Builder/ProjectsPage'));
const AppProjectDetail = lazy(() => import('./pages/App/Builder/ProjectDetailPage'));
const AppDiagrams = lazy(() => import('./pages/App/DiagramStudio'));
const DiagnosticsHome = lazy(() => import('./pages/Diagnostics/Diagnostics'));
const DiagnosticsDoctor = lazy(() => import('./pages/Diagnostics/Doctor'));
const DiagnosticsTraces = lazy(() => import('./pages/Diagnostics/Traces/Traces'));
const DiagnosticsTraceDetail = lazy(() => import('./pages/Diagnostics/Traces/TraceDetail'));
const DiagnosticsGraphs = lazy(() => import('./pages/Diagnostics/Graphs/Graphs'));
const DiagnosticsGraphRunDetail = lazy(() => import('./pages/Diagnostics/Graphs/GraphRunDetail'));
const DiagnosticsLinks = lazy(() => import('./pages/Diagnostics/Links/Links'));
const DiagnosticsRuns = lazy(() => import('./pages/Diagnostics/Runs/Runs'));
const DiagnosticsAudit = lazy(() => import('./pages/Diagnostics/Audit/Audit'));
const DiagnosticsPolicies = lazy(() => import('./pages/Diagnostics/Policies/Policies'));
const DiagnosticsLLMReview = lazy(() => import('./pages/Diagnostics/LLMReview'));
const DiagnosticsSyscalls = lazy(() => import('./pages/Diagnostics/Syscalls'));
const DiagnosticsSmoke = lazy(() => import('./pages/Diagnostics/Smoke/Smoke'));
const DiagnosticsBrowserTest = lazy(() => import('./pages/Diagnostics/BrowserTest/BrowserTestPanel'));
const DiagnosticsEvalDashboard = lazy(() => import('./pages/Diagnostics/EvalDashboard'));
const BusinessValueReport = lazy(() => import('./pages/Diagnostics/BusinessValueReport'));
const ReleasesPage = lazy(() => import('./pages/Releases/ReleasesPage'));
const ApprovalCenter = lazy(() => import('./pages/Management/ApprovalCenter'));
const ApprovalHistory = lazy(() => import('./pages/Management/ApprovalHistory'));
const DiagnosticsOps = lazy(() => import('./pages/Diagnostics/Ops'));
const DiagnosticsRepo = lazy(() => import('./pages/Diagnostics/Repo'));
const DiagnosticsChangeControl = lazy(() => import('./pages/Diagnostics/ChangeControl'));
const DiagnosticsRoutingReplayList = lazy(() => import('./pages/Diagnostics/RoutingReplay/RoutingReplayList'));
const DiagnosticsRoutingReplayDetail = lazy(() => import('./pages/Diagnostics/RoutingReplay/RoutingReplayDetail'));
const DiagnosticsRoutingDashboard = lazy(() => import('./pages/Diagnostics/RoutingReplay/RoutingDashboard'));
const DiagnosticsPolicyDebug = lazy(() => import('./pages/Diagnostics/PolicyDebug'));
const DiagnosticsContext = lazy(() => import('./pages/Diagnostics/Context'));
const DiagnosticsCapabilityPolicy = lazy(() => import('./pages/Diagnostics/CapabilityPolicy'));
const DiagnosticsCapabilityBoundary = lazy(() => import('./pages/Diagnostics/CapabilityBoundary'));
const DiagnosticsRAGQuality = lazy(() => import('./pages/Diagnostics/RAGQuality'));
const DiagnosticsExecBackends = lazy(() => import('./pages/Diagnostics/ExecBackends'));
const DiagnosticsWorkflows = lazy(() => import('./pages/Diagnostics/Workflows'));
const DiagnosticsCodeIntel = lazy(() => import('./pages/Diagnostics/CodeIntel/CodeIntel'));
const DiagnosticsCapabilityGraph = lazy(() => import('./pages/Diagnostics/CapabilityGraph/CapabilityGraph'));
const RepairCenter = lazy(() => import('./pages/Diagnostics/RepairCenter'));
const FdeDashboard = lazy(() => import('./pages/Diagnostics/FdeDashboard'));
const ObservabilityDashboard = lazy(() => import('./pages/Diagnostics/ObservabilityDashboard'));
const KnowledgeOverview = lazy(() => import('./pages/Knowledge/KnowledgeOverview'));
const KnowledgeFactoryPage = lazy(() => import('./pages/KnowledgeFactory/KnowledgeFactoryPage'));
const DocsViewer = lazy(() => import('./pages/Docs/DocsViewer'));
const OntologyEditor = lazy(() => import('./pages/OntologyEditor'));
const GovernanceDashboard = lazy(() => import('./pages/Governance'));
const CapabilitiesAdmin = lazy(() => import('./pages/Admin/Capabilities'));
const RunComparison = lazy(() => import('./pages/Diagnostics/RunComparison'));
const ModelPlayground = lazy(() => import('./pages/Diagnostics/ModelPlayground'));
const ModelAuditPanel = lazy(() => import('./pages/Diagnostics/ModelAuditPanel'));
const SafetyPanel = lazy(() => import('./pages/Diagnostics/SafetyPanel'));
const ControlProfilePanel = lazy(() => import('./components/model/ControlProfilePanel'));
const SystemGraph = lazy(() => import('./pages/SystemGraph'));
const Onboarding = lazy(() => import('./pages/Onboarding/Onboarding'));
const OnboardingWizard = lazy(() => import('./pages/Onboarding/OnboardingWizard'));
const ValueDashboard = lazy(() => import('./pages/ValueCenter/ValueDashboard'));
const EnterpriseKPIs = lazy(() => import('./pages/ValueCenter/EnterpriseKPIs'));
const BusinessGoals = lazy(() => import('./pages/ValueCenter/BusinessGoals'));
const RoleManager = lazy(() => import('./pages/ValueCenter/RoleManager'));
const StrategyControl = lazy(() => import('./pages/ValueCenter/StrategyControl'));
const UserWorkbench = lazy(() => import('./pages/ValueCenter/UserWorkbench'));
const TrainingMonitor = lazy(() => import('./pages/ValueCenter/TrainingMonitor'));
const SpecDetailPage = lazy(() => import('./pages/ValueCenter/SpecDetail'));
const StudioPage = lazy(() => import('./pages/Studio/StudioPage'));
const PentestPage = lazy(() => import('./pages/Pentest/Pentest'));

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: withSuspense(SystemOverview) },
      { path: 'overview', element: <Navigate to="/system-overview" replace /> },
      { path: 'system-overview', element: withSuspense(SystemOverview) },
      { path: 'system-graph', element: withSuspense(SystemGraph) },
      { path: 'alerts', element: withSuspense(Alerts) },
      { path: 'onboarding', element: withSuspense(Onboarding) },
      { path: 'onboarding/wizard', element: withSuspense(OnboardingWizard) },
      { path: 'value-center', element: withSuspense(ValueDashboard) },
      { path: 'value-center/kpis', element: withSuspense(EnterpriseKPIs) },
      { path: 'value-center/goals', element: withSuspense(BusinessGoals) },
      { path: 'value-center/roles', element: withSuspense(RoleManager) },
      { path: 'value-center/strategy', element: withSuspense(StrategyControl) },
      { path: 'value-center/training', element: withSuspense(TrainingMonitor) },
      { path: 'value-center/spec/:specId', element: withSuspense(SpecDetailPage) },
      { path: 'workbench', element: <Navigate to="/app/factory" replace /> },
      { path: 'knowledge/overview', element: withSuspense(KnowledgeOverview) },
      { path: 'knowledge-factory', element: withSuspense(KnowledgeFactoryPage) },
      { path: 'docs', element: withSuspense(DocsViewer) },
      { path: 'ontology-editor', element: withSuspense(OntologyEditor) },
      { path: 'governance', element: withSuspense(GovernanceDashboard) },
      { path: 'governance/capabilities', element: withSuspense(CapabilitiesAdmin) },
      { path: 'infra/nodes', element: withSuspense(InfraNodes) },
      { path: 'infra/models', element: withSuspense(InfraModels) },
      { path: 'infra/finetune', element: withSuspense(InfraFineTune) },
      { path: 'infra/ontology', element: withSuspense(InfraOntology) },
      { path: 'infra/services', element: withSuspense(InfraServices) },
      { path: 'infra/scheduler', element: withSuspense(InfraScheduler) },
      { path: 'infra/storage', element: withSuspense(InfraStorage) },
      { path: 'infra/network', element: withSuspense(InfraNetwork) },
      { path: 'infra/monitoring', element: withSuspense(InfraMonitoring) },
      { path: 'infra/llm-stats', element: withSuspense(LlmRouteMonitor) },
      { path: 'core/agents', element: withSuspense(CoreAgents) },
      { path: 'core/skills', element: withSuspense(CoreSkills) },
      { path: 'core/skills-rollouts', element: withSuspense(CoreSkillsRollouts) },
      { path: 'core/prompts', element: withSuspense(CorePrompts) },
      { path: 'core/tools', element: withSuspense(CoreTools) },
      { path: 'core/plugins', element: withSuspense(CorePlugins) },
      { path: 'core/mcp', element: withSuspense(CoreMCP) },
      { path: 'core/workflows', element: withSuspense(WorkflowsPage) },
      { path: 'core/workflows/new', element: withSuspense(WorkflowCanvas) },
      { path: 'core/workflows/:id/edit', element: withSuspense(WorkflowCanvas) },
      { path: 'core/workflows/:id/runs/:projectId', element: withSuspense(WorkflowRunPage) },
      { path: 'core/variables', element: withSuspense(CoreVariables) },
      { path: 'core/credentials', element: withSuspense(CoreCredentials) },
      { path: 'core/memory', element: withSuspense(CoreMemory) },
      { path: 'core/checkpoints', element: withSuspense(FileCheckpoints) },
      { path: 'core/skill-packs', element: withSuspense(CoreSkillPacks) },
      { path: 'core/jobs', element: withSuspense(CoreJobs) },
      { path: 'prompts/app', element: withSuspense(PromptApp) },
      { path: 'workspace/agents', element: withSuspense(WorkspaceAgents) },
      { path: 'workspace/skills', element: withSuspense(WorkspaceSkills) },
      { path: 'workspace/skills-lint', element: withSuspense(WorkspaceSkillLint) },
      { path: 'workspace/marketplace', element: withSuspense(WorkspaceMarketplace) },
      { path: 'workspace/mcp', element: withSuspense(WorkspaceMCP) },
      { path: 'workspace/tools', element: withSuspense(WorkspaceTools) },
      { path: 'workspace/teams', element: withSuspense(WorkspaceTeams) },
      { path: 'plugins', element: withSuspense(PackagePlugins) },
      { path: 'core/learning/artifacts', element: withSuspense(CoreLearningArtifacts) },
      { path: 'core/learning/artifacts/:artifactId', element: withSuspense(CoreLearningArtifactDetail) },
      { path: 'core/learning/releases', element: withSuspense(CoreReleases) },
      { path: 'core/learning/rollouts', element: withSuspense(CoreLearningRollouts) },
      { path: 'core/approvals', element: withSuspense(CoreApprovals) },
      { path: 'core/agent-insight', element: withSuspense(AgentInsightPage) },
      { path: 'core/agent-insight/:agentId', element: withSuspense(AgentInsightPage) },
      { path: 'platform/gateway', element: withSuspense(PlatformGateway) },
      { path: 'platform/auth', element: withSuspense(PlatformAuth) },
      { path: 'platform/tenant', element: withSuspense(PlatformTenant) },
      { path: 'app/channels', element: withSuspense(AppChannels) },
      { path: 'app/sessions', element: withSuspense(AppSessions) },
      { path: 'platform/kb', element: withSuspense(AppKnowledgeBase) },
      { path: 'platform/kb/wiki', element: withSuspense(AppKnowledgeBase) },
      { path: 'platform/kb/eval', element: withSuspense(AppKnowledgeBase) },
      { path: 'platform/kb/vault', element: withSuspense(AppKnowledgeBase) },
      { path: 'platform/kb/health', element: withSuspense(AppKnowledgeBase) },
      { path: 'platform/kb/chat/:sessionId', element: withSuspense(AppMaterialsChat) },
      { path: 'app/builder/team', element: withSuspense(AppTeamAssembly) },
      { path: "app/factory", element: withSuspense(AppFactory) },
      { path: "app/apps/:projectId", element: withSuspense(AppPage) },
      { path: 'app/builder/projects', element: withSuspense(AppProjects) },
      { path: 'app/builder/projects/:id', element: withSuspense(AppProjectDetail) },
      { path: 'app/builder', element: withSuspense(AppProjects) },
      { path: 'app/apps', element: withSuspense(AppsPage) },
      { path: 'app/apps/:id/chat', element: withSuspense(AppChatPage) },
      { path: 'app/diagrams', element: withSuspense(AppDiagrams) },
      { path: 'diagnostics', element: withSuspense(DiagnosticsHome) },
      { path: 'diagnostics/llm-review', element: withSuspense(DiagnosticsLLMReview) },
      { path: 'diagnostics/doctor', element: withSuspense(DiagnosticsDoctor) },
      { path: 'diagnostics/traces', element: withSuspense(DiagnosticsTraces) },
      { path: 'diagnostics/traces/:traceId', element: withSuspense(DiagnosticsTraceDetail) },
      { path: 'diagnostics/graphs', element: withSuspense(DiagnosticsGraphs) },
      { path: 'diagnostics/graphs/:runId', element: withSuspense(DiagnosticsGraphRunDetail) },
      { path: 'diagnostics/links', element: withSuspense(DiagnosticsLinks) },
      { path: 'diagnostics/repo', element: withSuspense(DiagnosticsRepo) },
      { path: 'diagnostics/runs', element: withSuspense(DiagnosticsRuns) },
      { path: 'diagnostics/audit', element: withSuspense(DiagnosticsAudit) },
      { path: 'diagnostics/policies', element: withSuspense(DiagnosticsPolicies) },
      { path: 'diagnostics/syscalls', element: withSuspense(DiagnosticsSyscalls) },
      { path: 'diagnostics/change-control', element: withSuspense(DiagnosticsChangeControl) },
      { path: 'diagnostics/change-control/:changeId', element: withSuspense(DiagnosticsChangeControl) },
      { path: 'diagnostics/routing-replay', element: withSuspense(DiagnosticsRoutingReplayList) },
      { path: 'diagnostics/routing-replay/:routingDecisionId', element: withSuspense(DiagnosticsRoutingReplayDetail) },
      { path: 'diagnostics/routing-dashboard', element: withSuspense(DiagnosticsRoutingDashboard) },
      { path: 'diagnostics/policy-debug', element: withSuspense(DiagnosticsPolicyDebug) },
      { path: 'diagnostics/smoke', element: withSuspense(DiagnosticsSmoke) },
      { path: 'diagnostics/browser-test', element: withSuspense(DiagnosticsBrowserTest) },
      { path: 'releases', element: withSuspense(ReleasesPage) },
      { path: 'approval', element: withSuspense(ApprovalCenter) },
      { path: 'approval/history', element: withSuspense(ApprovalHistory) },
      { path: 'diagnostics/ops', element: withSuspense(DiagnosticsOps) },
      { path: 'diagnostics/context', element: withSuspense(DiagnosticsContext) },
      { path: 'diagnostics/capability-policy', element: withSuspense(DiagnosticsCapabilityPolicy) },
      { path: 'diagnostics/capability-boundary', element: withSuspense(DiagnosticsCapabilityBoundary) },
      { path: 'diagnostics/rag-quality', element: withSuspense(DiagnosticsRAGQuality) },
      { path: 'diagnostics/exec-backends', element: withSuspense(DiagnosticsExecBackends) },
      { path: 'diagnostics/workflows', element: withSuspense(DiagnosticsWorkflows) },
      { path: 'diagnostics/code-intel', element: withSuspense(DiagnosticsCodeIntel) },
      { path: 'diagnostics/capability-graph', element: withSuspense(DiagnosticsCapabilityGraph) },
      { path: 'diagnostics/repairs', element: withSuspense(RepairCenter) },
      { path: 'diagnostics/fde', element: withSuspense(FdeDashboard) },
      { path: 'diagnostics/observability', element: withSuspense(ObservabilityDashboard) },
      { path: 'diagnostics/run-comparison', element: withSuspense(RunComparison) },
      { path: 'diagnostics/model-playground', element: withSuspense(ModelPlayground) },
      { path: 'diagnostics/model-audit', element: withSuspense(ModelAuditPanel) },
      { path: 'diagnostics/safety', element: withSuspense(SafetyPanel) },
      { path: 'diagnostics/eval', element: withSuspense(DiagnosticsEvalDashboard) },
      { path: 'diagnostics/business-value', element: withSuspense(BusinessValueReport) },
      { path: 'diagnostics/knowledge-health', element: withSuspense(DiagnosticsHome) },
      { path: 'diagnostics/drift-status', element: withSuspense(DiagnosticsHome) },
      { path: 'diagnostics/control-profile', element: withSuspense(ControlProfilePanel) },
      { path: 'studio', element: <Navigate to="/app/factory?tab=chat" replace /> },
      { path: 'pentest', element: withSuspense(PentestPage) },
    ],
  },
]);

const App: React.FC = () => {
  return <RouterProvider router={router} future={{ v7_startTransition: true }} />;
};

export default App;
