/**
 * FDE 工作台 glossary — Layer A for 小朱 (XIAOZHU.md §1.2–1.4)。
 * 未上报时顾问禁止臆造本页按钮；本包把「新建客户」等入口写成可核验科目。
 */
export type FdeGlossEntry = { term: string; aliases?: string[]; meaning: string };

export const FDE_GLOSSARY: FdeGlossEntry[] = [
  {
    term: 'FDE 工作台',
    aliases: ['/diagnostics/fde', 'FDE Dashboard', '现场交付'],
    meaning:
      '现场交付操作系统：①业务认知→交付计划→②评估域→…→⑧运营监控；不是 CRM，也不是租户/组织试点页',
  },
  {
    term: '新建客户',
    aliases: ['新建', '新建客户 Profile', '创建客户', '客户建档', '客户 Profile'],
    meaning:
      '在①业务认知 Tab 右上角「新建」或空列表「新建客户」打开「新建客户 Profile」表单；创建的是 FDE 客户 Profile（name/namespace/行业/部署模式），不是 /platform/tenant 租户，也不是 ERP/Salesforce 外部客户表',
  },
  {
    term: '业务认知',
    aliases: ['①', 'customers', '客户列表'],
    meaning: 'Tab①：查看/新建/编辑/删除客户 Profile，并「切换至此」绑定后续步骤上下文',
  },
  {
    term: '切换至此',
    aliases: ['切换客户', '选中客户', 'switch-profile'],
    meaning: '在客户卡片上切换当前 Profile；交付计划/评估域/诊断等会带上该客户 namespace',
  },
  {
    term: '交付计划',
    aliases: ['plan', '实施计划', '生成计划', '上传需求'],
    meaning:
      'Tab「交付计划」：①先选用客户 → 本页粘贴或上传需求文本(≥20字) → 点「生成计划」。不依赖 hasDiagnosis/问题重构；上传只读入浏览器不落盘原文；完成度≠⑦签收',
  },
  {
    term: 'Gate0 决策锁定',
    aliases: ['Gate0', '决策锁定', 'gate0'],
    meaning:
      '交付计划插段（非①–⑧编号）：进场前锁定部署模式/性能口径/合规授权/一期 InOut；在①改客户 Profile 后手勾；未锁定勿承诺生产验收',
  },
  {
    term: '应用工厂并行',
    aliases: ['factory', '应用工厂项目'],
    meaning:
      '交付计划插段：与③④并行在 /app/factory 建项目做最小可演示路径；手勾；不替代 FDE④POC/⑤打包/⑦签收，也不代点部署审批',
  },
  {
    term: '评估域',
    aliases: ['②', 'capability', '选域', '江苏锁安', 'lock-service'],
    meaning:
      'Tab②：选业务域（全平台域目录）。「江苏锁安」等是域显示名≠客户；当前客户看页顶绿条。切换客户会清空/重绑上一客户残留的域',
  },
  {
    term: '问题重构',
    aliases: ['③', 'assess', '诊断'],
    meaning: 'Tab③：运行现场诊断，把表层需求翻译为深层问题与方案',
  },
  {
    term: '客户 Profile',
    aliases: ['customer profile', 'namespace', '部署模式'],
    meaning:
      'FDE 交付上下文对象：名称、命名空间、描述、行业、部署模式 online/hybrid/airgap；存平台 FDE customers API，勿与 CRM 客户或租户混淆',
  },
  {
    term: '客户卡片重复',
    aliases: ['两个一样的客户', '相同的两个客户', '列表重复', '出现两个客户'],
    meaning:
      '多为 name≠namespace（如 MTW-syu vs mtw-syu）时 ProfileManager 曾双键缓存导致列表重复显示；磁盘通常只有一份 YAML；应只显示一张卡；已按 namespace 去重。不是真的建了两个客户',
  },
  {
    term: 'customerListCount',
    aliases: ['客户列表数', '共N个', 'customerListSummary'],
    meaning:
      'pageData 中的①客户列表实况：条数与 name@namespace 摘要；「当前选用」customerName 只是选中项，不等于列表只有这一家',
  },
  {
    term: '组织试点',
    aliases: ['/org/pilot', 'Org M4'],
    meaning: 'it-ops 组织签收准备页；与 FDE 项目签收/客户 Profile 不是同一套流程',
  },
  {
    term: '应用工厂',
    aliases: ['/app/factory'],
    meaning: '应用交付流水线；FDE 交付计划中的工厂步会链到这里，但客户 Profile 仍在 FDE①创建',
  },
];

export function fdeGlossaryPromptText(maxLen = 2800): string {
  // 每条只写一次 meaning；别名缩进附在 term 后，避免 alias 全量复制把 Gate0/工厂等裁掉
  const parts: string[] = [];
  for (const e of FDE_GLOSSARY) {
    const aliases = (e.aliases || []).slice(0, 4).join('/');
    parts.push(aliases ? `${e.term}(${aliases})=${e.meaning}` : `${e.term}=${e.meaning}`);
  }
  const text = parts.join('；');
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}
