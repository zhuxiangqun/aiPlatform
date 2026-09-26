/** Client-side fallback boundary hints (mirrors core/apps/common/boundary_hints.py). */

export type AgentDraftLike = {
  skills?: string[];
  tools?: string[];
  mcp_ids?: string[];
  sop_text?: string;
  sop?: string;
  description?: string;
};

const TOOL_LIKE = ['读写文件', '读文件', '写文件', 'http', 'api', '计算器', '抓取网页', 'shell', '数据库'];
/** Concrete integrations only — bare「外部」matches「不引入外部内容」false positives. */
const EXTERNAL = [
  '外部系统',
  '外部对接',
  '对接外部',
  '系统对接',
  '飞书',
  '企微',
  '钉钉',
  '第三方系统',
  '第三方服务',
  'webhook',
  'mcp server',
];
const EXTERNAL_NEGATION = [
  '不引入外部',
  '不补充外部',
  '禁止外部',
  '无外部',
  '不要外部',
  '外部内容',
  '外部素材',
  '外部信息',
];
const EXTERNAL_STRONG = ['飞书', '企微', '钉钉', 'webhook', '第三方系统', '第三方服务'];

function blob(...parts: unknown[]): string {
  return parts.map((p) => String(p || '')).join(' ').toLowerCase();
}

export function mentionsExternalSystem(...parts: unknown[]): boolean {
  const text = blob(...parts);
  if (!text) return false;
  if (EXTERNAL_NEGATION.some((k) => text.includes(k)) && !EXTERNAL_STRONG.some((k) => text.includes(k))) {
    return false;
  }
  return EXTERNAL.some((k) => text.includes(k));
}

export function hintsForAgentDraft(draft: AgentDraftLike, description = ''): string[] {
  const skills = Array.isArray(draft.skills) ? draft.skills : [];
  const tools = Array.isArray(draft.tools) ? draft.tools : [];
  const mcps = Array.isArray(draft.mcp_ids) ? draft.mcp_ids : [];
  const sop = String(draft.sop_text || draft.sop || '');
  const text = blob(description, draft.description, sop);
  const out: string[] = [];
  if (skills.length <= 1 && tools.length === 0 && mcps.length === 0 && sop.length < 200) {
    out.push('绑定偏少：若只是单能力流程，可先建 Skill 再组装；确需数字员工则补 Tool/MCP 或加厚 SOP。');
  }
  if (mentionsExternalSystem(text) && mcps.length === 0) {
    out.push('描述像外部系统对接，但未绑定 MCP：可在 MCP 库创建后重填，或在 SOP 中写 `mcp_server_name` / [[need:mcp:名称]]。');
  }
  if ((text.includes('文件') || text.includes('http') || text.includes('api')) && tools.length === 0) {
    out.push('含文件/HTTP/API 原子操作但未绑 Tool：可在 SOP 引用 `file_operations` / `http` 等。');
  }
  if (!skills.length && !tools.length && !mcps.length) {
    out.push('Skill/Tool/MCP 均为空：确认前请核对绑定，否则 Agent 只能空转对话。');
  }
  return out.slice(0, 4);
}

export function hintsForSkillDraft(
  draft: { description?: string; sop?: string; display_name?: string; permissions?: string[] },
  description = ''
): string[] {
  const text = blob(description, draft.description, draft.sop, draft.display_name);
  const out: string[] = [];
  const sop = String(draft.sop || '');
  if (TOOL_LIKE.some((k) => text.includes(k.toLowerCase())) && sop.length < 120) {
    out.push('更像原子 Tool。若无多步 SOP，建议改建成 Tool。');
  }
  if (text.includes('编排') || text.includes('数字员工')) {
    out.push('含编排/数字员工语义：编排放 Agent；Skill 只做单一可复用能力。');
  }
  const perms = Array.isArray(draft.permissions) ? draft.permissions : [];
  if (perms.some((p) => String(p).includes('tool:')) && !sop.includes('`') && !sop.toLowerCase().includes('tool')) {
    out.push('permissions 含 tool:*，但 SOP 未写具体工具：请写明或去掉多余权限。');
  }
  return out.slice(0, 4);
}
