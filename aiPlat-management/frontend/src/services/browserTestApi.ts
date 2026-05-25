/**
 * Browser Test API — 全功能浏览器自动化测试
 */
import { apiClient } from './apiClient';

export interface TestConfig {
  base_url: string;
  login_url?: string;
  accounts?: Array<{ username: string; password: string; label?: string }>;
  routes?: string[];
  exclude_patterns?: string[];
  include_patterns?: string[];
  max_recursion_depth?: number;
  allow_writes?: boolean;
  allow_delete?: boolean;
  action_timeout_ms?: number;
  page_load_timeout_ms?: number;
  screenshot_dir?: string;
  video_enabled?: boolean;
  headless?: boolean;
}

export interface TestStatus {
  running: boolean;
  status: string;  // 'not_started' | 'running' | 'finished'
  summary: {
    total_pages: number;
    total_actions: number;
    passed: number;
    failed: number;
    skipped: number;
    duration_ms: number;
    errors: number;
  };
}

export interface ActionDetail {
  step_id: number;
  action: string;
  element_role: string;
  element_text: string;
  result: string;  // 'passed' | 'failed' | 'skipped'
  error?: string;
  duration_ms?: number;
  screenshot_before?: string;
  screenshot_after?: string;
}

export interface PageDetail {
  url: string;
  depth: number;
  loaded: boolean;
  elements_found: number;
  screenshot?: string;
  modals_detected: number;
  actions: ActionDetail[];
}

export interface TestReport {
  started_at: string;
  finished_at: string;
  total_pages: number;
  total_actions: number;
  passed: number;
  failed: number;
  skipped: number;
  total_duration_ms: number;
  errors: string[];
  pages?: PageDetail[];
}

export const browserTestApi = {
  start: (config: TestConfig) =>
    apiClient.post<{ ok: boolean; message: string; config: Record<string, unknown> }>(
      '/core/browser/test/start',
      config,
    ),

  status: () =>
    apiClient.get<TestStatus>('/core/browser/test/status'),

  report: (detail: boolean = false) =>
    apiClient.get<TestReport>(`/core/browser/test/report?detail=${detail}`),

  stop: () =>
    apiClient.post<{ ok: boolean; message: string; summary: Record<string, unknown> }>(
      '/core/browser/test/stop',
      {},
    ),

  generateCases: (config: TestConfig) =>
    apiClient.post<{ ok: boolean; message: string; xlsx_path: string; total_cases: number }>(
      '/core/browser/test/generate-cases',
      config,
    ),

  executeCases: (xlsxPath: string, options?: { headless?: boolean; auto_approve?: boolean }) =>
    apiClient.post<{ ok: boolean; message: string }>(
      '/core/browser/test/execute-cases',
      { xlsx_path: xlsxPath, headless: options?.headless ?? false, auto_approve: options?.auto_approve ?? false },
    ),

  caseExecutionStatus: () =>
    apiClient.get<{ running: boolean; status: string }>('/core/browser/test/execute-cases/status'),

  stopCaseExecution: () =>
    apiClient.post<{ ok: boolean; message: string }>('/core/browser/test/execute-cases/stop', {}),

  uploadCases: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch('/api/core/browser/test/upload-cases', {
      method: 'POST',
      body: formData,
    });
    return resp.json() as Promise<{ ok: boolean; path: string; filename: string }>;
  },
};
