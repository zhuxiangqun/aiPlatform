/**
 * Models page glossary — Layer A for 小朱 (XIAOZHU.md §1.2–1.4).
 */
export type ModelsGlossEntry = { term: string; aliases?: string[]; meaning: string };

export const MODELS_GLOSSARY: ModelsGlossEntry[] = [
  {
    term: '模型管理',
    aliases: ['/infra/models'],
    meaning: 'infra 模型目录：启用/禁用/健康；选模权威在 ModelManager，不在业务代码写死',
  },
  {
    term: 'unified_pipeline',
    aliases: ['选模链路', 'best_model_for_purpose'],
    meaning: '唯一选模链：purpose → unified_pipeline 打分；顾问用 purpose=auto',
  },
  {
    term: 'purpose',
    aliases: ['chat', 'code_gen', 'auto'],
    meaning: '选模用途名；开放问答走 auto，禁止业务点名具体权重',
  },
  {
    term: '扫描本地模型',
    aliases: ['Ollama', '本地模型'],
    meaning: '扫描本机 Ollama 等本地模型并登记；扫描≠已对业务启用',
  },
  {
    term: 'enabled',
    aliases: ['已启用'],
    meaning: '进程内对该模型开放选用；名单以本页/简报为准',
  },
  {
    term: 'disabled',
    aliases: ['已禁用'],
    meaning: '已登记但禁用，选模不应命中',
  },
  {
    term: 'unhealthy',
    aliases: ['不健康', 'error'],
    meaning: '健康检查失败或错误态；勿推荐给生产路径',
  },
  {
    term: 'provider',
    aliases: ['providerCount', '提供商'],
    meaning: '模型来源/提供方计数；OpenAI 兼容等多走同一适配器',
  },
  {
    term: 'totalModels',
    aliases: ['模型数量', '几个模型'],
    meaning: '本页模型条数；以页面上报为准，勿用 Wiki 猜',
  },
];

export function modelsGlossaryPromptText(maxLen = 1200): string {
  const parts: string[] = [];
  for (const e of MODELS_GLOSSARY) {
    parts.push(`${e.term}=${e.meaning}`);
    for (const a of e.aliases || []) parts.push(`${a}=${e.meaning}`);
  }
  const text = parts.join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}
