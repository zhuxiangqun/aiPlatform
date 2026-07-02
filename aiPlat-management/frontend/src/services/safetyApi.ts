import { apiClient } from './apiClient';

export interface CrisisSignal {
  rule_id: string;
  severity: string;
  pattern_matched: string;
}

export interface CrisisCheckResult {
  is_crisis: boolean;
  severity: string;
  escalation_required: boolean;
  recommended_action: string;
  signals: CrisisSignal[];
  signal_count: number;
}

export interface EmotionSnapshot {
  session_id: string;
  timestamp: number;
  dominant_tone: string;
  intensity: number;
  keywords: string[];
}

export interface EmotionStateData {
  tenant_id: string;
  session_id: string;
  current_tone: string;
  trend: string;
  dependency_risk: string;
  sessions_24h: number;
  avg_session_length_min: number;
  history: EmotionSnapshot[];
}

export interface FlaggedSessionsResponse {
  tenant_id: string;
  count: number;
  sessions: EmotionStateData[];
}

export const safetyApi = {
  crisisCheck: async (text: string, sessionId?: string) => {
    return apiClient.post<CrisisCheckResult>('/core/safety/crisis-check', {
      text,
      session_id: sessionId || '',
    });
  },

  sessionCheck: async (messages: Record<string, unknown>[], sessionId?: string) => {
    return apiClient.post<any>('/core/safety/session-check', {
      messages,
      session_id: sessionId || '',
    });
  },

  getEmotionState: async (sessionId: string, tenantId?: string) => {
    return apiClient.post<any>('/core/safety/emotion-state', {
      session_id: sessionId,
      tenant_id: tenantId || 'default',
    });
  },

  dependencyCheck: async (sessionId: string, tenantId?: string) => {
    return apiClient.post<any>('/core/safety/dependency-check', {
      session_id: sessionId,
      tenant_id: tenantId || 'default',
    });
  },

  getFlaggedSessions: async (tenantId?: string) => {
    return apiClient.get<FlaggedSessionsResponse>(
      `/core/safety/flagged-sessions?tenant_id=${encodeURIComponent(tenantId || 'default')}`
    );
  },

  trackEmotion: async (sessionId: string, messages: Record<string, unknown>[], tenantId?: string, durationS?: number) => {
    return apiClient.post<any>('/core/safety/track-emotion', {
      session_id: sessionId,
      messages,
      tenant_id: tenantId || 'default',
      duration_s: durationS || 0,
    });
  },
};
