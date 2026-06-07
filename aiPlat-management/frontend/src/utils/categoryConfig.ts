/**
 * Shared category badge configuration for Skills and Tools.
 * Both Core and Workspace pages reference the same config.
 */
export const SKILL_CATEGORIES: Record<string, { color: string; text: string }> = {
  general: { color: 'bg-dark-hover text-gray-300 border-gray-200', text: '通用' },
  reasoning: { color: 'bg-blue-50 text-blue-300 border-blue-200', text: '推理' },
  coding: { color: 'bg-green-50 text-green-300 border-green-200', text: '编程' },
  search: { color: 'bg-amber-50 text-amber-300 border-amber-200', text: '搜索' },
  tool: { color: 'bg-purple-50 text-purple-300 border-purple-200', text: '工具' },
  communication: { color: 'bg-cyan-50 text-cyan-300 border-cyan-200', text: '通信' },
  execution: { color: 'bg-orange-50 text-orange-300 border-orange-200', text: '执行' },
  retrieval: { color: 'bg-teal-50 text-teal-300 border-teal-200', text: '检索' },
  analysis: { color: 'bg-indigo-50 text-indigo-300 border-indigo-200', text: '分析' },
  generation: { color: 'bg-pink-50 text-pink-300 border-pink-200', text: '生成' },
  transformation: { color: 'bg-yellow-50 text-yellow-300 border-yellow-200', text: '转换' },
};

export const TOOL_CATEGORIES: Record<string, { color: string; text: string }> = {
  general: { color: 'bg-dark-hover text-gray-300 border-dark-border', text: '通用' },
  search: { color: 'bg-blue-50 text-blue-300 border-blue-200', text: '搜索' },
  calculation: { color: 'bg-green-50 text-green-300 border-green-200', text: '计算' },
  file_operations: { color: 'bg-amber-50 text-amber-300 border-amber-200', text: '文件操作' },
  code_execution: { color: 'bg-purple-50 text-purple-300 border-purple-200', text: '代码执行' },
  api: { color: 'bg-cyan-50 text-cyan-300 border-cyan-200', text: 'API调用' },
  data: { color: 'bg-rose-50 text-rose-300 border-rose-200', text: '数据处理' },
};

export function getCategoryBadge(category: string, type: 'skill' | 'tool' = 'skill') {
  const config = type === 'skill' ? SKILL_CATEGORIES : TOOL_CATEGORIES;
  const cfg = config[category] || { color: 'bg-dark-hover text-gray-300 border-dark-border', text: category || '-' };
  return (
    `<span class="inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}">${cfg.text}</span>`
  );
}
