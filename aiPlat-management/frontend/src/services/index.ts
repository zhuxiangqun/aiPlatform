/**
 * API 服务导出
 */

// 基础设施层 API
export { apiClient, dashboardApi, alertingApi, diagnosticsApi } from './apiClient';
export { nodeApi } from './nodeApi';
export { serviceApi } from './serviceApi';
export { schedulerApi } from './schedulerApi';
export { storageApi } from './storageApi';
export { networkApi } from './networkApi';
export { monitoringApi } from './monitoringApi';
export { modelApi } from './modelApi';

// 核心能力层 API
export { agentApi, skillApi, memoryApi, knowledgeApi, harnessApi, toolApi, learningApi, approvalsApi, jobApi, skillPackApi, runApi } from './coreApi';
export { gatewayAdminApi } from './coreApi';

// Legacy monitoring API (for layer metrics)
export { monitoringApi as layerMonitoringApi } from './apiClient';

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
  SkillPack,
  SkillPackVersion,
  SkillPackInstall,
  RunSummary,
  RunEvent,
} from './coreApi';

// 平台服务层 & 应用接入层 API
export { gatewayApi, authApi, tenantApi, channelApi, appSessionApi } from './platformAppApi';

// Types - Platform & App
export type { GatewayRoute, GatewayRouteListResponse, AuthUser, AuthUserListResponse, TenantInfo, TenantListResponse, Channel, ChannelListResponse, AppSession, AppSessionListResponse } from './platformAppApi';
