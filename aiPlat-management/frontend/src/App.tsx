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
const CoreMemory = lazy(() => import('./pages/Core/Memory/Memory'));
const PlatformGateway = lazy(() => import('./pages/Platform/Gateway/Gateway'));
const PlatformAuth = lazy(() => import('./pages/Platform/Auth/Auth'));
const PlatformTenant = lazy(() => import('./pages/Platform/Tenant/Tenant'));
const AppChannels = lazy(() => import('./pages/App/Channels/Channels'));
const AppSessions = lazy(() => import('./pages/App/Sessions/Sessions'));

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: withSuspense(Overview) },
      { path: 'overview', element: withSuspense(Overview) },
      { path: 'alerts', element: withSuspense(Alerts) },
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
      { path: 'core/memory', element: withSuspense(CoreMemory) },
      { path: 'platform/gateway', element: withSuspense(PlatformGateway) },
      { path: 'platform/auth', element: withSuspense(PlatformAuth) },
      { path: 'platform/tenant', element: withSuspense(PlatformTenant) },
      { path: 'app/channels', element: withSuspense(AppChannels) },
      { path: 'app/sessions', element: withSuspense(AppSessions) },
    ],
  },
]);

const App: React.FC = () => {
  return <RouterProvider router={router} future={{ v7_startTransition: true }} />;
};

export default App;
