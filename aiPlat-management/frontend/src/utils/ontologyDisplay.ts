/** Ontology bilingual display: English（中文） — 仅当副标题为中文时才括注 */

export function localKey(ref: string): string {
  if (!ref) return '';
  const s = String(ref).trim();
  const cut = s.replace(/^.*[#/]/, '');
  return cut || s;
}

/** True if string contains CJK characters. */
export function hasCjk(s: string): boolean {
  return /[\u3400-\u9fff]/.test(s || '');
}

/**
 * Format as ``English（中文）`` only when the second part is actually Chinese.
 * Avoids ``InstallTicket（install_tickets）`` style English（English）.
 */
export function bilingual(en?: string, zh?: string): string {
  const e = String(en || '').trim();
  const z = String(zh || '').trim();
  if (e && z && e !== z && hasCjk(z)) return `${e}（${z}）`;
  // 类 id 已是中文、label 是英文表名 → 只显示中文 id
  if (e && hasCjk(e)) return e;
  return e || z || '';
}

/** Soft Chinese for known class ids / table aliases when YAML label is still English. */
const CLASS_ZH: Record<string, string> = {
  InstallTicket: '安装票据',
  install_tickets: '安装票据',
  AlertEvent: '告警事件',
  alert_events: '告警事件',
  DeviceModel: '设备型号',
  InstallOrder: '安装工单',
  FaultType: '故障类型',
  RepairRecord: '维修记录',
  Technician: '安装师傅',
  CustomerSite: '客户现场',
};

/** Class title from API row (uri + Chinese label). */
export function classDisplay(cls: { uri?: string; label?: string; name?: string }): string {
  const en = localKey(cls.uri || '') || String(cls.name || '').trim();
  let zh = String(cls.label || '').trim();

  // label 不是中文（常见：表名 install_tickets）→ 用对照表，否则不加括注
  if (zh && !hasCjk(zh)) {
    zh = CLASS_ZH[en] || CLASS_ZH[zh] || CLASS_ZH[localKey(zh)] || '';
  }
  if (!zh && en) {
    zh = CLASS_ZH[en] || '';
  }

  if (en && zh && hasCjk(zh) && en !== zh) return `${en}（${zh}）`;
  if (en && hasCjk(en)) return en;
  return en || zh || '—';
}

/** Relation / object-property title. */
export function propDisplay(prop: { uri?: string; name?: string; label?: string }): string {
  const en = localKey(prop.uri || '') || String(prop.name || '').trim();
  const zh = String(prop.label || '').trim();
  return bilingual(en, hasCjk(zh) ? zh : '') || en || zh || '—';
}

/** Soft hints when YAML fields have no label (optional, non-authoritative). */
const FIELD_ZH: Record<string, string> = {
  name: '名称',
  title: '标题',
  body: '正文',
  description: '描述',
  status: '状态',
  state: '状态',
  order_id: '工单号',
  record_id: '记录号',
  ticket_id: '票据号',
  customer_name: '客户名',
  device_model: '设备型号',
  technician: '师傅',
  tech_name: '师傅姓名',
  site_name: '现场名称',
  service_name: '服务名',
  address: '地址',
  scheduled_date: '预约日期',
  completed_date: '完成日期',
  notes: '备注',
  urgency: '紧急度',
  brand: '品牌',
  lock_type: '锁类型',
  category: '类别',
  severity: '严重级别',
  symptoms: '症状',
  root_causes: '根因',
  fix_steps: '修复步骤',
  estimated_minutes: '预估分钟',
  required_parts: '所需配件',
  fault_type: '故障类型',
  diagnosis: '诊断',
  fix_action: '修复动作',
  duration_minutes: '耗时分钟',
  parts_used: '所用配件',
  resolved: '已解决',
  phone: '电话',
  skills: '技能',
  load: '负载',
  site_id: '现场编号',
  contact: '联系人',
  id: '标识',
  door_type: '门型',
  installed_devices: '已装设备',
  maintenance_history: '维保历史',
  key_contact: '关键联系人',
  access_notes: '门禁备注',
  compatible_doors: '适配门型',
  install_method: '安装方式',
  manual_url: '说明书链接',
  power_type: '供电方式',
  warranty_months: '质保月数',
  spec_version: '规格版本',
};

export function fieldDisplay(
  fieldName: string,
  fieldsMeta?: Array<{ name?: string; id?: string; label?: string; description?: string }>,
): string {
  const name = String(fieldName || '').trim();
  if (!name) return '';
  const meta = (fieldsMeta || []).find(
    (f) => f.name === name || f.id === name || localKey(String(f.name || '')) === name,
  );
  const fromMeta = String(meta?.label || '').trim();
  const zh = (fromMeta && hasCjk(fromMeta) ? fromMeta : '') || FIELD_ZH[name] || '';
  return bilingual(name, zh);
}

/** 说明书「类」卫生检查：疑似把实例抬成了类（脏类） */
export type ClassHygiene = {
  dirty: boolean;
  reasons: string[];
};

const KNOWN_TYPE_ZH = new Set([
  ...Object.values(CLASS_ZH),
  '设备型号', '安装工单', '故障类型', '维修记录', '安装师傅', '客户现场',
  '告警事件', '安装票据',
]);

function isThinSchema(cls: {
  required_fields?: string[];
  optional_fields?: string[];
  states?: { enum?: unknown[] } | null;
}): boolean {
  const req = (cls.required_fields || []).map(String);
  const opt = cls.optional_fields || [];
  const onlyName = req.length === 0 || (req.length === 1 && ['name', 'title', 'id'].includes(req[0]));
  const noStates = !(cls.states?.enum && cls.states.enum.length > 0);
  return onlyName && opt.length === 0 && noStates;
}

/**
 * 启发式识别「脏类」——YAML 里登记成类、实为某个具体实例/表名残渣。
 * 与孤儿类不同：孤儿=有类无实体；脏类=类本身像实例名。
 */
export function assessClassHygiene(cls: {
  uri?: string;
  label?: string;
  name?: string;
  required_fields?: string[];
  optional_fields?: string[];
  states?: { enum?: unknown[] } | null;
}): ClassHygiene {
  const reasons: string[] = [];
  const key = localKey(cls.uri || '') || String(cls.name || '').trim();
  const label = String(cls.label || '').trim();
  const thin = isThinSchema(cls);

  // ① URI/key 是中文类型词，label 却是另一个中文专名 → 画面常显示成「安装工单（王五式实例）」
  if (key && label && hasCjk(key) && hasCjk(label) && key !== label) {
    if (KNOWN_TYPE_ZH.has(key) || thin) {
      reasons.push(`类名「${key}」+ 标签「${label}」像类型套实例`);
    }
  }

  // ② label 自身写成「类型（实例）」且骨架极薄
  const paren = label.match(/^(.+?)[（(]([^）)]+)[）)]$/);
  if (paren) {
    const outer = paren[1].trim();
    const inner = paren[2].trim();
    if (
      thin &&
      hasCjk(outer) &&
      inner &&
      inner !== key &&
      (hasCjk(inner) || /[A-Za-z]{2,}/.test(inner))
    ) {
      reasons.push(`标签「${label}」像类型（实例名）`);
    }
  }

  // ③ 纯中文专名当类、且几乎无字段（王五 / EZVIZ茧石 / 智能锁安装服务）
  if (thin && hasCjk(label) && !KNOWN_TYPE_ZH.has(label) && !/^[A-Z][a-zA-Z0-9]+$/.test(key)) {
    if (!key || hasCjk(key) || key === label) {
      reasons.push('专名式标签且几乎无字段，疑似实例误登记为类');
    }
  }

  // ④ 英文蛇形表名 + 薄骨架（install_tickets）
  if (thin && /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/.test(key)) {
    reasons.push('英文表名式类名且几乎无字段');
  }

  // 去重
  const uniq = [...new Set(reasons)];
  return { dirty: uniq.length > 0, reasons: uniq };
}
