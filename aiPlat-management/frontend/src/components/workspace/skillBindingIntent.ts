/** Catalog filter for Skill bind UI. Match capability text, not just id. */

export type SkillBindIntent = 'upload' | 'file_write' | 'http' | 'search' | 'browser' | 'generic';

const UPLOAD_RE = /对象存储|oss|s3|play_url|minio|cos桶|上传到|put_object|multipart/i;
const FILE_RE = /\.pptx|\.docx|\.xlsx|\.pdf|写文件|落盘|workspace_fs|模版路径/i;
const HTTP_RE = /抓取网页|调用api|http请求|webfetch/i;
const SEARCH_RE = /联网搜索|web_search|检索网页/i;
const BROWSER_RE = /浏览器自动化|打开浏览器/i;
/** Id token: useful when description is empty. Not the only signal. */
const UPLOAD_ID_RE = /upload|oss|s3|minio|put_object/i;
/** Capability phrases in name / 描述 / MCP tools — exclude generic「文件」「HTTP GET」. */
const UPLOAD_CAPABILITY_RE =
  /对象存储|object storage|put_object|play_url|multipart\s*upload|presigned|上传到(对象|oss|s3|存储)|minio|cos桶|s3 bucket/i;

export function detectSkillBindIntent(text: string): SkillBindIntent {
  const t = String(text || '');
  if (UPLOAD_RE.test(t) || /上传/.test(t)) return 'upload';
  if (FILE_RE.test(t)) return 'file_write';
  if (HTTP_RE.test(t)) return 'http';
  if (SEARCH_RE.test(t)) return 'search';
  if (BROWSER_RE.test(t)) return 'browser';
  return 'generic';
}

export function catalogLooksLikeUpload(name: string, extra = ''): boolean {
  const id = String(name || '');
  const blob = `${id} ${extra}`;
  if (UPLOAD_ID_RE.test(id)) return true;
  return UPLOAD_CAPABILITY_RE.test(blob);
}

/** @deprecated use catalogLooksLikeUpload — kept for call sites */
export function catalogNameMatchesUpload(name: string, extra = ''): boolean {
  return catalogLooksLikeUpload(name, extra);
}

export function toolMatchesIntent(
  name: string,
  description: string,
  intent: SkillBindIntent,
): boolean {
  const blob = `${name} ${description}`;
  if (intent === 'upload') return catalogLooksLikeUpload(name, description);
  if (intent === 'file_write') return /file_operations|workspace_fs|写文件|落盘/i.test(blob);
  if (intent === 'http') return /webfetch|http|fetch|request/i.test(blob);
  if (intent === 'search') return /web_search|search/i.test(blob) && !/skill_find|tool_search/i.test(name);
  if (intent === 'browser') return /browser/i.test(blob);
  return !/^sysgraph_|^sys_lsp_|^mcp\./i.test(name);
}

export function mcpMatchesIntent(
  name: string,
  allowedTools: string[],
  description: string,
  intent: SkillBindIntent,
): boolean {
  const extra = `${description} ${allowedTools.join(' ')}`;
  if (intent === 'upload') return catalogLooksLikeUpload(name, extra);
  if (intent === 'browser') return /browser/i.test(`${name} ${extra}`);
  if (intent === 'http') return /http|fetch|api/i.test(`${name} ${extra}`);
  if (intent === 'generic' || intent === 'file_write' || intent === 'search') {
    return !/browser/i.test(name);
  }
  return true;
}

export function ioHintForIntent(intent: SkillBindIntent): { in: string; out: string; example: string } {
  if (intent === 'upload') {
    return {
      in: '入参 = 执行时要给的视频。必填通常是本地文件路径/文件对象和大小上限。',
      out: '出参 = 上传成功后系统返回的结构。play_url 必须由已绑定的上传 Tool/MCP 产出，模型不能编一条假链接。',
      example: '不要套用生成幻灯片的字段。标题、时长、清晰度一般是可选结果字段，不是你再填一遍的表单。',
    };
  }
  if (intent === 'file_write') {
    return {
      in: '入参 = 执行时要填的内容。只有勾了「必填」的才必须填。',
      out: '出参 = 跑完返回什么。日常不必手填；建议保留结果路径 + markdown。',
      example: '生成本地文件时：入参真正必填通常是大纲/正文；模版路径、字数上限多为可选。',
    };
  }
  return {
    in: '入参 = 执行时要填的内容。只有勾了「必填」的才必须填。',
    out: '出参 = 跑完系统返回什么（给程序/诊断看）。日常执行不必手填。',
    example: '按本 Skill 的描述填字段名，不要套用其它技能的模板字段。',
  };
}

export type PermChip = { id: string; label: string; hint: string };

export function permissionChipsForIntent(intent: SkillBindIntent): {
  intro: string;
  chips: PermChip[];
  confirmLabel: string;
  confirmHint: string;
} {
  if (intent === 'upload') {
    return {
      intro: '真上传需要已注册的上传/OSS Tool 或 MCP，并勾选调用权限。写 pptx、联网搜索与本 Skill 无关。',
      chips: [
        { id: 'llm:generate', label: '调用模型', hint: '按手册组织参数；真正传文件靠下面绑的 Tool/MCP' },
        { id: 'mcp:invoke', label: '调用 MCP', hint: '对象存储走 MCP 时勾选' },
      ],
      confirmLabel: '上传前二次确认',
      confirmHint: '生产更安全；本机自测可不勾',
    };
  }
  if (intent === 'file_write') {
    return {
      intro: '生成本地文件时勾选「写文件」。不要勾无关的搜索/跑命令。',
      chips: [
        { id: 'llm:generate', label: '调用模型', hint: '按手册生成内容' },
        { id: 'tool:workspace_fs_write', label: '写文件', hint: '写出 pptx/docx 等到工作区' },
      ],
      confirmLabel: '写文件前二次确认',
      confirmHint: '生产更安全；本机自测可不勾',
    };
  }
  if (intent === 'http') {
    return {
      intro: '抓取/调 HTTP 时勾选抓取网页；不要勾写盘除非 SOP 也要落盘。',
      chips: [
        { id: 'llm:generate', label: '调用模型', hint: '整理请求与结果' },
        { id: 'tool:webfetch', label: '抓取网页', hint: '已绑定 webfetch 时需要' },
      ],
      confirmLabel: '外部请求前二次确认',
      confirmHint: '生产更安全；本机自测可不勾',
    };
  }
  return {
    intro: '只勾本 Skill 真正会用到的能力。',
    chips: [
      { id: 'llm:generate', label: '调用模型', hint: '按手册回答或编排' },
      { id: 'tool:workspace_fs_write', label: '写文件', hint: '仅当要落盘时勾选' },
      { id: 'tool:websearch', label: '联网搜索', hint: '仅当 SOP 要搜索时勾选' },
      { id: 'tool:webfetch', label: '抓取网页', hint: '仅当 SOP 要 HTTP GET 时勾选' },
    ],
    confirmLabel: '高风险操作前二次确认',
    confirmHint: '生产更安全；本机自测可不勾',
  };
}
