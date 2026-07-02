import { apiClient } from './apiClient';

export interface ProbeResult {
  probe_id: string;
  dimension: string;
  latency_ms: number;
  token_count: number;
  response_hash: string;
  contains_refusal: boolean;
  format_valid: boolean | null;
  answer_correct: boolean | null;
  error?: string;
}

export interface ModelFingerprintData {
  model_name: string;
  timestamp: number;
  avg_latency_ms: number;
  avg_token_count: number;
  refusal_rate: number;
  format_compliance: number;
  fingerprint_hash: string;
  confidence: number;
  probes: ProbeResult[];
}

export interface ModelIdentity {
  model_name: string;
  detected_family: string;
  detected_variant: string;
  estimated_size: string;
  fingerprint_hash: string;
  confidence: number;
  match_reasons: string[];
}

export interface AuditReportData {
  identity: ModelIdentity;
  fingerprint: ModelFingerprintData;
  recommendations: string[];
  risk_flags: string[];
  generated_at: number;
}

export interface ComparisonData {
  model_a: string;
  model_b: string;
  similarity: number;
  likely_relationship: string;
  dimension_scores: Record<string, number>;
  details: string[];
}

export const modelAuditApi = {
  probe: async (modelName: string, timeoutS?: number) => {
    return apiClient.post<ModelFingerprintData>('/core/model-audit/probe', {
      model_name: modelName,
      timeout_s: timeoutS ?? 30,
    });
  },

  report: async (modelName: string) => {
    return apiClient.post<AuditReportData>('/core/model-audit/report', {
      model_name: modelName,
    });
  },

  compare: async (modelA: string, modelB: string) => {
    return apiClient.post<ComparisonData>('/core/model-audit/compare', {
      model_a: modelA,
      model_b: modelB,
    });
  },

  signatures: async () => {
    return apiClient.get<{ signatures: Record<string, any>; count: number }>('/core/model-audit/signatures');
  },
};
