/**
 * API 服务导出
 */

// 基础设施层 API
export { apiClient, dashboardApi, alertingApi, diagnosticsApi, onboardingApi } from './apiClient';
export { nodeApi } from './nodeApi';
export { serviceApi } from './serviceApi';
export { schedulerApi } from './schedulerApi';
export { storageApi } from './storageApi';
export { networkApi } from './networkApi';
export { monitoringApi } from './monitoringApi';
export { modelApi } from './modelApi';

// 核心能力层 API
export {
  agentApi,
  workspaceAgentApi,
  modelsApi,
  skillApi,
  workspaceSkillApi,
  workspaceSkillInstallerApi,
  memoryApi,
  knowledgeApi,
  harnessApi,
  toolApi,
  workspaceToolApi,
  learningApi,
  approvalsApi,
  jobApi,
  skillPackApi,
  runApi,
  auditApi,
  policyApi,
  gatePolicyApi,
  quotaApi,
  mcpApi,
  workspaceMcpApi,
  packageApi,
  gatewayDlqApi,
  opsApi,
  pluginApi,
  promptApi,
  promptAppApi,
  promptEvalApi,
  promptOptimizeApi,
  variablesApi,
  credentialsApi,
  workflowTemplateApi,
  workflowApi,
  appApi,
} from './coreApi';
export { gatewayAdminApi, SKILL_CATEGORIES } from './coreApi';

// Legacy monitoring API (for layer metrics)
export { monitoringApi as layerMonitoringApi } from './apiClient';
export { browserTestApi } from './browserTestApi';

// Types - Infrastructure
export type { Node, GPU, NodeListResponse, AddNodeRequest } from './nodeApi';
export type { Service, Pod, Image, ServiceListResponse, DeployServiceRequest } from './serviceApi';
export type { Quota, Policy, Task, AutoscalingPolicy, ScalingMetric } from './schedulerApi';
export type { VectorCollection, ModelStorage, PVC } from './storageApi';
export type { ServiceEndpoint, ServicePort, Ingress, NetworkPolicy, NetworkRule } from './networkApi';
export type { GPUMetrics, NodeMetrics, AlertRule, Alert, AuditLog, ClusterMetrics } from './monitoringApi';
export type { Model, ModelConfig, ModelStats, Provider, AddModelRequest, ModelListResponse } from './modelApi';

// Types - Core
export type {
  Agent,
  AgentListResponse,
  Skill,
  SkillDetail,
  SkillListResponse,
  ToolInfo,
  ToolListResponse,
  MemorySession,
  MemoryMessage,
  MemorySessionDetail,
  MemorySearchResult,
  LongTermMemoryItem,
  SessionListResponse,
  LearningArtifact,
  LearningArtifactListResponse,
  ApprovalRequestSummary,
  Job,
  JobRun,
  JobDeliveryDLQItem,
  GatewayPairing,
  GatewayToken,
  TenantQuotaSnapshot,
  TenantUsageItem,
  GatewayDeliveryDLQItem,
  PluginRecord,
  SkillPack,
  SkillPackVersion,
  SkillPackInstall,
  PromptTemplateRow,
  RunSummary,
  RunEvent,
  AuditLogEntry,
  TenantPolicy,
  McpServer,
  WorkspaceSkillInstallerPlan,
} from './coreApi';

// 平台服务层 & 应用接入层 API
export { gatewayApi, authApi, tenantApi, channelApi, appSessionApi } from './platformAppApi';
export { builderTeamApi } from './builderTeamApi';
export { projectApi } from './builderTeamApi';
export { insightApi } from './builderTeamApi';
export { chatApi, promptsApi } from './chatApi';

export type { ProjectItem, ProjectRun } from './builderTeamApi';
export type { AgentInsight } from './builderTeamApi';
export type { BuilderSession, PipelineStageConfig, AgentCatalogItem, TeamConfig } from './builderTeamApi';

export type { GatewayRoute, AuthUser, TenantInfo, Channel, AppSession } from './platformAppApi';

export { kbApi } from './kbApi';
export type { KBConversation, KBAnalysisBatch, KBAnalysisRun, KBCollection, KBCategory, KBDocument, KBDocumentSource } from './kbApi';

export { packagesApi } from './coreApi';
