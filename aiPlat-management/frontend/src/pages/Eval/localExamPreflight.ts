/**
 * Local-only exam preflight — block suite when no local LLM is available
 * (avoid silently calling remote commercial APIs).
 */
import { modelsApi } from '../../services';

const LOCAL_PROVIDER_HINTS = [
  'ollama',
  'lmstudio',
  'lm_studio',
  'local',
  'omlx',
  'vllm',
  'mlx',
  'llama.cpp',
  'llamacpp',
  'llama_cpp',
  'openai_compatible_local',
];

export function isLocalModelProvider(provider: string): boolean {
  const p = String(provider || '')
    .toLowerCase()
    .replace(/[\s-]+/g, '_');
  if (!p) return false;
  if (LOCAL_PROVIDER_HINTS.some((h) => p === h || p.includes(h))) return true;
  // Heuristic: explicit local markers in provider id
  return p.includes('local') || p.endsWith('_local');
}

export type LocalExamPreflight = {
  ok: boolean;
  message: string;
  local_models: string[];
  remote_only: boolean;
};

/**
 * Require at least one enabled chat LLM from a local/LAN provider.
 */
export async function checkLocalExamPreflight(): Promise<LocalExamPreflight> {
  try {
    const res = await modelsApi.list();
    const models = Array.isArray(res?.models) ? res.models : [];
    const enabled = models.filter((m) => m && m.enabled !== false && String(m.name || '').trim());
    const local = enabled.filter((m) => isLocalModelProvider(String(m.provider || '')));
    const names = local.map((m) => String(m.name));
    if (names.length > 0) {
      return {
        ok: true,
        message: `本机可用模型 ${names.length} 个（如 ${names.slice(0, 3).join(', ')}）。建议服务端 AIPLAT_LOCAL_ONLY=1，避免评测静默走外网。`,
        local_models: names,
        remote_only: false,
      };
    }
    const remoteN = enabled.length;
    return {
      ok: false,
      message:
        remoteN > 0
          ? `检测到 ${remoteN} 个模型但均为远程 provider，本地冒烟已阻断。请接入 Ollama/LM Studio 等本机模型，并设置 AIPLAT_LOCAL_ONLY=1。不要用「外部目标」分区做本地冒烟。`
          : '未发现可用本机 LLM。请先在本机启动 Ollama/LM Studio 等并在模型目录可见，设置 AIPLAT_LOCAL_ONLY=1 后再跑。',
      local_models: [],
      remote_only: remoteN > 0,
    };
  } catch (e: unknown) {
    return {
      ok: false,
      message: `无法检查本机模型：${e instanceof Error ? e.message : String(e)}。本地冒烟需要可达的 /core/models。`,
      local_models: [],
      remote_only: false,
    };
  }
}
