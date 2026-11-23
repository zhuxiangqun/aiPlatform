/**
 * AboxAclPanel — N07/N22 deepen ABox 实例/字段 ACL 管理端薄 UI。
 *
 * 经 `/api/platform/apps/fde/graph/acl/*`；不宣称 certified / 全量权限产品。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Lock, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type EntityEntry = {
  deny_roles?: Record<string, string[]>;
  allow_roles?: Record<string, string[]>;
};

type FieldEntry = {
  visibility?: string;
  redaction?: string;
  replace_with?: string;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

function parseRoleMap(raw: string): Record<string, string[]> | undefined {
  const t = raw.trim();
  if (!t) return undefined;
  // role:act1|act2,role2:*
  const out: Record<string, string[]> = {};
  for (const part of t.split(',')) {
    const [role, acts] = part.trim().split(':');
    if (!role) continue;
    out[role.trim()] = (acts || '*')
      .split('|')
      .map((a) => a.trim())
      .filter(Boolean);
  }
  return Object.keys(out).length ? out : undefined;
}

function splitCsv(raw: string): string[] {
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

/** H.1 矩阵默认轴（加载 crud_matrix 前兜底；运行时以 SSOT 覆盖）。 */
const H1_MATRIX_ROLES_DEFAULT = ['viewer', 'analyst', 'admin'];
const H1_MATRIX_ACTIONS_DEFAULT = ['read', 'update', 'state_change', 'delete'];

function principalRoleName(p: string): string {
  const s = p.trim();
  return s.toLowerCase().startsWith('role:') ? s.slice(5).trim() : s;
}

/** 共享 principals/actions → 矩阵单元格（薄表单回退；各选中角色同勾）。 */
function matrixCellsFromShared(
  principals: string,
  actions: string,
  roleAxis: string[],
): Record<string, Set<string>> {
  const roles = new Set(splitCsv(principals).map(principalRoleName).filter(Boolean));
  const acts = splitCsv(actions);
  const out: Record<string, Set<string>> = {};
  for (const r of roleAxis) {
    out[r] = new Set(roles.has(r) ? acts : []);
  }
  return out;
}

/** role_actions 优先；缺省时回退共享展开。 */
function matrixCellsFromForm(
  principals: string,
  actions: string,
  roleAxis: string[],
  roleActions?: Record<string, string[]>,
): Record<string, Set<string>> {
  if (roleActions && Object.keys(roleActions).length > 0) {
    const out: Record<string, Set<string>> = {};
    for (const r of roleAxis) {
      const list = roleActions[r] || [];
      out[r] = new Set(list.map(String).filter(Boolean));
    }
    return out;
  }
  return matrixCellsFromShared(principals, actions, roleAxis);
}

/** 矩阵 → principals + actions 并集 + role_actions（保留 per-role 差异）。 */
function formFromMatrixCells(
  cells: Record<string, Set<string>>,
  roleAxis: string[],
): {
  principals: string;
  actions: string;
  roleActions: Record<string, string[]>;
} {
  const principals: string[] = [];
  const actUnion = new Set<string>();
  const roleActions: Record<string, string[]> = {};
  for (const r of roleAxis) {
    const set = cells[r];
    if (set && set.size > 0) {
      principals.push(`role:${r}`);
      const list = Array.from(set);
      roleActions[r] = list;
      list.forEach((a) => actUnion.add(a));
    }
  }
  return {
    principals: principals.join(','),
    actions: Array.from(actUnion).join(',') || 'read',
    roleActions,
  };
}

/** 从 H.1 policy 抽出薄表单字段（含可选 role_actions）。 */
function formFieldsFromH1(policy: Record<string, unknown>): {
  effect: 'allow' | 'deny';
  principals: string;
  actions: string;
  conditionRaw: string;
  masked: string;
  roleActions: Record<string, string[]>;
} {
  const effect = String(policy.effect || 'allow').toLowerCase() === 'deny' ? 'deny' : 'allow';
  const principals = Array.isArray(policy.principals)
    ? (policy.principals as unknown[]).map(String).join(',')
    : '';
  const actions = Array.isArray(policy.actions)
    ? (policy.actions as unknown[]).map(String).join(',')
    : 'read';
  const cond =
    policy.condition && typeof policy.condition === 'object' && !Array.isArray(policy.condition)
      ? JSON.stringify(policy.condition)
      : '{}';
  const masked = Array.isArray(policy.masked_properties)
    ? (policy.masked_properties as unknown[]).map(String).join(',')
    : '';
  const roleActions: Record<string, string[]> = {};
  const rawRa = policy.role_actions;
  if (rawRa && typeof rawRa === 'object' && !Array.isArray(rawRa)) {
    for (const [k, v] of Object.entries(rawRa as Record<string, unknown>)) {
      const role = principalRoleName(k);
      if (!role || !Array.isArray(v)) continue;
      roleActions[role] = v.map(String).filter(Boolean);
    }
  }
  return { effect, principals, actions, conditionRaw: cond, masked, roleActions };
}

function buildH1FromForm(fields: {
  effect: 'allow' | 'deny';
  principals: string;
  actions: string;
  conditionRaw: string;
  masked: string;
  roleActions?: Record<string, string[]>;
}): Record<string, unknown> | { error: string } {
  let condition: Record<string, unknown> = {};
  const ct = fields.conditionRaw.trim();
  if (ct) {
    try {
      const parsed = JSON.parse(ct) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return { error: 'condition 须为 JSON 对象' };
      }
      condition = parsed as Record<string, unknown>;
    } catch {
      return { error: 'condition 须为合法 JSON' };
    }
  }
  const out: Record<string, unknown> = {
    effect: fields.effect,
    principals: splitCsv(fields.principals),
    actions: splitCsv(fields.actions).length ? splitCsv(fields.actions) : ['*'],
    condition,
    masked_properties: splitCsv(fields.masked),
  };
  if (fields.roleActions && Object.keys(fields.roleActions).length > 0) {
    out.role_actions = fields.roleActions;
  }
  return out;
}

const AboxAclPanel: React.FC = () => {
  const [domainId, setDomainId] = useState('lock-service');
  const [entityId, setEntityId] = useState('');
  const [denyRaw, setDenyRaw] = useState('viewer:read');
  const [allowRaw, setAllowRaw] = useState('');
  const [conditionRaw, setConditionRaw] = useState('{"status":{"$in":["open","pending"]}}');
  const [maskedRaw, setMaskedRaw] = useState('ssn,customer_phone');
  const [fieldEntity, setFieldEntity] = useState('');
  const [fieldName, setFieldName] = useState('');
  const [visibility, setVisibility] = useState('role:admin');
  const [redaction, setRedaction] = useState('mask');
  const [entities, setEntities] = useState<Record<string, EntityEntry>>({});
  const [fields, setFields] = useState<Record<string, FieldEntry>>({});
  const [loading, setLoading] = useState(false);
  const [certified, setCertified] = useState(false);
  const [previewEntity, setPreviewEntity] = useState('');
  const [previewRole, setPreviewRole] = useState('viewer');
  const [previewAction, setPreviewAction] = useState('read');
  const [previewPayload, setPreviewPayload] = useState('{"ssn":"123-45-6789","name":"demo"}');
  const [previewOut, setPreviewOut] = useState('');
  const [h1Entity, setH1Entity] = useState('');
  const [h1Effect, setH1Effect] = useState<'allow' | 'deny'>('deny');
  const [h1Principals, setH1Principals] = useState('role:viewer');
  const [h1Actions, setH1Actions] = useState('read');
  const [h1RoleActions, setH1RoleActions] = useState<Record<string, string[]>>({
    viewer: ['read'],
  });
  const [h1ConditionRaw, setH1ConditionRaw] = useState('{"status":"open"}');
  const [h1MaskedForm, setH1MaskedForm] = useState('ssn');
  const [h1Raw, setH1Raw] = useState(
    '{\n  "effect": "deny",\n  "principals": ["role:viewer"],\n  "actions": ["read"],\n  "role_actions": {"viewer": ["read"]},\n  "condition": {"status": "open"},\n  "masked_properties": ["ssn"]\n}',
  );
  const [h1Policies, setH1Policies] = useState<Record<string, unknown>[]>([]);
  const [h1ListOut, setH1ListOut] = useState('');
  // 为什么：矩阵轴来自 GET acl → crud_matrix.h1_matrix_*（env SSOT）；非前端硬编码产品轴
  const [h1MatrixRoles, setH1MatrixRoles] = useState<string[]>(H1_MATRIX_ROLES_DEFAULT);
  const [h1MatrixActions, setH1MatrixActions] = useState<string[]>(H1_MATRIX_ACTIONS_DEFAULT);

  const pushFormToRaw = useCallback(
    (next?: {
      effect?: 'allow' | 'deny';
      principals?: string;
      actions?: string;
      conditionRaw?: string;
      masked?: string;
      roleActions?: Record<string, string[]>;
      clearRoleActions?: boolean;
    }) => {
      const roleActions = next?.clearRoleActions
        ? undefined
        : (next?.roleActions ?? h1RoleActions);
      const built = buildH1FromForm({
        effect: next?.effect ?? h1Effect,
        principals: next?.principals ?? h1Principals,
        actions: next?.actions ?? h1Actions,
        conditionRaw: next?.conditionRaw ?? h1ConditionRaw,
        masked: next?.masked ?? h1MaskedForm,
        roleActions,
      });
      if ('error' in built) return;
      setH1Raw(JSON.stringify(built, null, 2));
    },
    [h1Effect, h1Principals, h1Actions, h1ConditionRaw, h1MaskedForm, h1RoleActions],
  );

  const applyPolicyToForm = useCallback((policy: Record<string, unknown>) => {
    const f = formFieldsFromH1(policy);
    setH1Effect(f.effect);
    setH1Principals(f.principals);
    setH1Actions(f.actions);
    setH1ConditionRaw(f.conditionRaw);
    setH1MaskedForm(f.masked);
    setH1RoleActions(f.roleActions);
    const { certified: _c, ...rest } = policy;
    setH1Raw(JSON.stringify(rest, null, 2));
  }, []);

  const reload = useCallback(async () => {
    if (!domainId.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(API(`/graph/acl/${encodeURIComponent(domainId.trim())}`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const acl = body.acl || {};
      setEntities((acl.entities as Record<string, EntityEntry>) || {});
      setFields((acl.fields as Record<string, FieldEntry>) || {});
      const policies = Array.isArray(body.h1_policies)
        ? (body.h1_policies as Record<string, unknown>[])
        : [];
      setH1Policies(policies);
      setCertified(Boolean(body.certified));
      const cm = (body.crud_matrix || {}) as {
        h1_matrix_roles?: unknown;
        h1_matrix_actions?: unknown;
        roles?: unknown;
        actions?: unknown;
      };
      const rolesRaw = Array.isArray(cm.h1_matrix_roles)
        ? cm.h1_matrix_roles
        : Array.isArray(cm.roles)
          ? cm.roles
          : null;
      const actsRaw = Array.isArray(cm.h1_matrix_actions)
        ? cm.h1_matrix_actions
        : Array.isArray(cm.actions)
          ? (cm.actions as unknown[]).filter((a) => String(a) !== 'admin')
          : null;
      if (rolesRaw && rolesRaw.length) {
        setH1MatrixRoles(
          rolesRaw.map((r) => String(r).trim().toLowerCase()).filter(Boolean),
        );
      }
      if (actsRaw && actsRaw.length) {
        setH1MatrixActions(
          actsRaw.map((a) => String(a).trim().toLowerCase()).filter(Boolean),
        );
      }
    } catch (e: unknown) {
      setEntities({});
      setFields({});
      setH1Policies([]);
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [domainId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const saveEntity = async () => {
    if (!entityId.trim()) {
      toast?.error?.('entity_id 必填');
      return;
    }
    let condition: Record<string, unknown> | undefined;
    const ct = conditionRaw.trim();
    if (ct) {
      try {
        const parsed = JSON.parse(ct) as unknown;
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          toast?.error?.('condition 须为 JSON 对象');
          return;
        }
        condition = parsed as Record<string, unknown>;
      } catch {
        toast?.error?.('condition 须为合法 JSON');
        return;
      }
    }
    // H.1 masked_properties：逗号分隔；空串清除
    const masked_properties = maskedRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    setLoading(true);
    try {
      const r = await fetch(
        API(`/graph/acl/${encodeURIComponent(domainId.trim())}/entities/${encodeURIComponent(entityId.trim())}`),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            deny_roles: parseRoleMap(denyRaw),
            allow_roles: parseRoleMap(allowRaw),
            // 空对象清除 condition；省略则后端不改（此处有输入则总是传）
            condition: condition ?? {},
            masked_properties,
          }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.('已保存实例 ACL');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const saveField = async () => {
    if (!fieldEntity.trim() || !fieldName.trim()) {
      toast?.error?.('field entity / field_name 必填');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        API(
          `/graph/acl/${encodeURIComponent(domainId.trim())}/fields/${encodeURIComponent(fieldEntity.trim())}/${encodeURIComponent(fieldName.trim())}`,
        ),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            visibility: visibility.trim() || 'all',
            redaction,
            replace_with: '[REDACTED]',
          }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.('已保存 ABox 字段 ACL');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const removeEntity = async (id: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const r = await fetch(
        API(`/graph/acl/${encodeURIComponent(domainId.trim())}/entities/${encodeURIComponent(id)}`),
        { method: 'DELETE' },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(d.status === 'ok' ? '已删除实例 ACL' : '未找到');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '删除失败');
    } finally {
      setLoading(false);
    }
  };

  const removeField = async (key: string) => {
    const idx = key.lastIndexOf('.');
    if (idx <= 0) return;
    const eid = key.slice(0, idx);
    const fname = key.slice(idx + 1);
    setLoading(true);
    try {
      const r = await fetch(
        API(
          `/graph/acl/${encodeURIComponent(domainId.trim())}/fields/${encodeURIComponent(eid)}/${encodeURIComponent(fname)}`,
        ),
        { method: 'DELETE' },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(d.status === 'ok' ? '已删除字段 ACL' : '未找到');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '删除失败');
    } finally {
      setLoading(false);
    }
  };

  const loadH1List = async () => {
    if (!domainId.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(API(`/graph/acl/${encodeURIComponent(domainId.trim())}/h1`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const policies = Array.isArray(body.h1_policies)
        ? (body.h1_policies as Record<string, unknown>[])
        : [];
      setH1Policies(policies);
      setH1ListOut(JSON.stringify(body, null, 2));
      if (body.certified) toast?.error?.('异常：H.1 列表返回 certified=true');
    } catch (e: unknown) {
      setH1ListOut('');
      toast?.error?.((e as Error)?.message || 'H.1 列表失败');
    } finally {
      setLoading(false);
    }
  };

  const loadH1Entity = async (eid?: string) => {
    const id = (eid || h1Entity).trim();
    if (!id) {
      toast?.error?.('H.1 entity_id 必填');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        API(
          `/graph/acl/${encodeURIComponent(domainId.trim())}/entities/${encodeURIComponent(id)}/h1`,
        ),
      );
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const policy = (body.h1_policy || {}) as Record<string, unknown>;
      setH1Entity(id);
      // 编辑区不写回 certified 字段，避免误提交宣称
      applyPolicyToForm(policy);
      if (body.certified) toast?.error?.('异常：单实体 H.1 返回 certified=true');
      else toast?.success?.('已加载 H.1 到编辑区');
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '加载 H.1 失败');
    } finally {
      setLoading(false);
    }
  };

  const applyH1 = async () => {
    if (!h1Entity.trim()) {
      toast?.error?.('H.1 entity_id 必填');
      return;
    }
    // 优先薄表单；失败再回退 JSON textarea
    let policy: Record<string, unknown>;
    const fromForm = buildH1FromForm({
      effect: h1Effect,
      principals: h1Principals,
      actions: h1Actions,
      conditionRaw: h1ConditionRaw,
      masked: h1MaskedForm,
    });
    if ('error' in fromForm) {
      toast?.error?.(fromForm.error);
      return;
    }
    policy = fromForm;
    setH1Raw(JSON.stringify(policy, null, 2));
    setLoading(true);
    try {
      const r = await fetch(
        API(`/graph/acl/${encodeURIComponent(domainId.trim())}/entities/${encodeURIComponent(h1Entity.trim())}`),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ h1_policy: policy }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(d.h1_applied ? '已应用 H.1 策略（非 certified）' : '已保存');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || 'H.1 应用失败');
    } finally {
      setLoading(false);
    }
  };

  const runPreview = async () => {
    if (!previewEntity.trim()) {
      toast?.error?.('preview entity_id 必填');
      return;
    }
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(previewPayload || '{}') as Record<string, unknown>;
    } catch {
      toast?.error?.('payload 须为合法 JSON');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(API(`/graph/acl/${encodeURIComponent(domainId.trim())}/preview`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_id: previewEntity.trim(),
          role: previewRole.trim(),
          action: previewAction.trim() || 'read',
          payload,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      setPreviewOut(JSON.stringify(d, null, 2));
      if (d.certified) toast?.error?.('异常：预览返回 certified=true');
    } catch (e: unknown) {
      setPreviewOut('');
      toast?.error?.((e as Error)?.message || '预览失败');
    } finally {
      setLoading(false);
    }
  };

  const entityKeys = Object.keys(entities);
  const fieldKeys = Object.keys(fields);

  return (
    <Card className="border-gray-700/60 bg-gray-900/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-gray-200">
          <Lock className="h-4 w-4 text-amber-400" />
          ABox 实例 ACL（薄面板 · 非 certified）
        </div>
        <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void reload()}>
          <RefreshCw className="h-3.5 w-3.5 mr-1" />
          刷新
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 px-4 pb-4">
        <p className="text-[11px] text-gray-500 leading-relaxed">
          管理域级 <code className="text-gray-400">abox_acl.json</code>（实例 deny/allow + 字段脱敏）。
          API 返回 <code className="text-gray-400">certified=false</code>
          {certified ? '（异常：后端宣称 certified）' : '（当前诚实）'}；与 Wiki field_permissions 薄面板互补，非全量权限产品。
        </p>

        <label className="text-[11px] text-gray-400 space-y-1 block">
          domain_id
          <input
            className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
            value={domainId}
            onChange={(e) => setDomainId(e.target.value)}
          />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-gray-400 space-y-1">
            entity_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="entity-…"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            deny_roles（role:acts,…）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={denyRaw}
              onChange={(e) => setDenyRaw(e.target.value)}
              placeholder="viewer:read|*"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            allow_roles（可空）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={allowRaw}
              onChange={(e) => setAllowRaw(e.target.value)}
              placeholder="admin:*"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1 sm:col-span-2">
            condition（H.1：标量等值 / $eq / $ne / $in / $nin / $all / $elemMatch / $exists / $gt / $gte / $lt / $lte（数值或 str 字典序） / $regex（$options 仅 i） / $and|$or|$nor|$not（深度≤28；$nor≡¬∨；$not 可否定字段/$and|$or|$nor/$not，正规求值再取反，每层≤8）；空=`{}` 清除；非表达式语言）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={conditionRaw}
              onChange={(e) => setConditionRaw(e.target.value)}
              placeholder='{"status":{"$nin":["archived","closed"]}}'
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1 sm:col-span-2">
            masked_properties（H.1：逗号分隔字段名；空=清除；同步 fields visibility=none；非完整策略编辑器）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={maskedRaw}
              onChange={(e) => setMaskedRaw(e.target.value)}
              placeholder="ssn,customer_phone"
            />
          </label>
          <div className="flex items-end">
            <Button type="button" size="sm" disabled={loading} onClick={() => void saveEntity()}>
              保存实例 ACL
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-gray-400 space-y-1">
            field entity_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={fieldEntity}
              onChange={(e) => setFieldEntity(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            field_name
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={fieldName}
              onChange={(e) => setFieldName(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            visibility
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            redaction
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={redaction}
              onChange={(e) => setRedaction(e.target.value)}
            >
              <option value="mask">mask</option>
              <option value="truncate">truncate</option>
              <option value="replace">replace</option>
              <option value="remove">remove</option>
            </select>
          </label>
          <div className="flex items-end">
            <Button type="button" size="sm" disabled={loading} onClick={() => void saveField()}>
              保存字段 ACL
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <div className="text-[12px] text-gray-300 mb-1.5">实例规则（{entityKeys.length}）</div>
            {entityKeys.length === 0 ? (
              <div className="text-[11px] text-gray-500">暂无</div>
            ) : (
              <ul className="space-y-1.5 max-h-40 overflow-auto text-[11px] font-mono text-gray-400">
                {entityKeys.map((id) => (
                  <li
                    key={id}
                    className="rounded border border-gray-800 bg-gray-950/50 px-2 py-1.5 break-all flex flex-wrap items-center justify-between gap-2"
                  >
                    <span>
                      {id}
                      <span className="ml-2 text-gray-500">
                        deny={JSON.stringify(entities[id]?.deny_roles || {})}
                      </span>
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={loading}
                      onClick={() => void removeEntity(id)}
                    >
                      删除
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="text-[12px] text-gray-300 mb-1.5">字段规则（{fieldKeys.length}）</div>
            {fieldKeys.length === 0 ? (
              <div className="text-[11px] text-gray-500">暂无</div>
            ) : (
              <ul className="space-y-1.5 max-h-40 overflow-auto text-[11px] font-mono text-gray-400">
                {fieldKeys.map((key) => (
                  <li
                    key={key}
                    className="rounded border border-gray-800 bg-gray-950/50 px-2 py-1.5 break-all flex flex-wrap items-center justify-between gap-2"
                  >
                    <span>
                      {key}
                      <span className="ml-2 text-gray-500">
                        {fields[key]?.visibility}/{fields[key]?.redaction}
                      </span>
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={loading}
                      onClick={() => void removeField(key)}
                    >
                      删除
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="border-t border-gray-800 pt-3 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[12px] text-gray-300">
              H.1 策略列表（只读投影 · {h1Policies.length} · 非完整策略编辑器 · 非 certified）
            </div>
            <Button type="button" size="sm" variant="secondary" disabled={loading} onClick={() => void loadH1List()}>
              刷新 H.1 列表
            </Button>
          </div>
          {h1Policies.length === 0 ? (
            <div className="text-[11px] text-gray-500">暂无 H.1 投影</div>
          ) : (
            <ul className="space-y-1.5 max-h-32 overflow-auto text-[11px] font-mono text-gray-400">
              {h1Policies.map((p, i) => (
                <li
                  key={`${String(p.resource || i)}-${i}`}
                  className="rounded border border-gray-800 bg-gray-950/50 px-2 py-1.5 flex flex-wrap items-center justify-between gap-2"
                >
                  <span>
                    {String(p.resource || '?')} · {String(p.effect || '')} ·{' '}
                    {JSON.stringify(p.principals || [])}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={loading || !p.resource}
                    onClick={() => void loadH1Entity(String(p.resource))}
                  >
                    加载到编辑区
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {h1ListOut ? (
            <pre className="max-h-32 overflow-auto rounded border border-gray-800 bg-gray-950/70 p-2 text-[11px] text-gray-400 whitespace-pre-wrap">
              {h1ListOut}
            </pre>
          ) : null}
        </div>

        <div className="border-t border-gray-800 pt-3 space-y-2">
          <div className="text-[12px] text-gray-300">
            H.1 薄表单 + per-role 矩阵（role_actions · 配置轴 crud_matrix.h1_matrix_* · 非 certified / 非任意 RBAC）
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-end">
            <label className="text-[11px] text-gray-400 space-y-1 block">
              entity_id
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={h1Entity}
                onChange={(e) => setH1Entity(e.target.value)}
              />
            </label>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={loading}
              onClick={() => void loadH1Entity()}
            >
              加载 H.1
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="text-[11px] text-gray-400 space-y-1">
              effect
              <select
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                value={h1Effect}
                onChange={(e) => {
                  const v = e.target.value === 'deny' ? 'deny' : 'allow';
                  setH1Effect(v);
                  pushFormToRaw({ effect: v });
                }}
              >
                <option value="deny">deny</option>
                <option value="allow">allow</option>
              </select>
            </label>
            <label className="text-[11px] text-gray-400 space-y-1">
              actions（逗号分隔 · 并集；编辑时按 principals 广播为 role_actions）
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={h1Actions}
                onChange={(e) => {
                  const v = e.target.value;
                  setH1Actions(v);
                  const shared = formFromMatrixCells(
                    matrixCellsFromShared(h1Principals, v, h1MatrixRoles),
                    h1MatrixRoles,
                  );
                  setH1RoleActions(shared.roleActions);
                  pushFormToRaw({
                    actions: v,
                    principals: shared.principals,
                    roleActions: shared.roleActions,
                  });
                }}
                placeholder="read,update"
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1 sm:col-span-2">
              principals（逗号分隔，如 role:viewer）
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={h1Principals}
                onChange={(e) => {
                  const v = e.target.value;
                  setH1Principals(v);
                  const shared = formFromMatrixCells(
                    matrixCellsFromShared(v, h1Actions, h1MatrixRoles),
                    h1MatrixRoles,
                  );
                  setH1RoleActions(shared.roleActions);
                  pushFormToRaw({
                    principals: v,
                    actions: shared.actions,
                    roleActions: shared.roleActions,
                  });
                }}
                placeholder="role:viewer,role:analyst"
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1 sm:col-span-2">
              condition（JSON 对象）
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={h1ConditionRaw}
                onChange={(e) => {
                  setH1ConditionRaw(e.target.value);
                  pushFormToRaw({ conditionRaw: e.target.value });
                }}
                placeholder='{"status":"open"}'
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1 sm:col-span-2">
              masked_properties（逗号分隔）
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={h1MaskedForm}
                onChange={(e) => {
                  setH1MaskedForm(e.target.value);
                  pushFormToRaw({ masked: e.target.value });
                }}
                placeholder="ssn,customer_phone"
              />
            </label>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <div className="text-[11px] text-gray-400">
              per-role 矩阵（角色×动作 · 勾选写入 role_actions；actions 为并集 · 配置轴 · 非任意 RBAC）
            </div>
            <div className="overflow-auto rounded border border-gray-800">
              <table className="w-full text-[11px] text-gray-300 border-collapse">
                <thead>
                  <tr className="bg-gray-950/80 text-gray-500">
                    <th className="px-2 py-1.5 text-left font-normal">role</th>
                    {h1MatrixActions.map((a) => (
                      <th key={a} className="px-2 py-1.5 text-center font-normal font-mono">
                        {a}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const cells = matrixCellsFromForm(
                      h1Principals,
                      h1Actions,
                      h1MatrixRoles,
                      h1RoleActions,
                    );
                    return h1MatrixRoles.map((role) => (
                      <tr key={role} className="border-t border-gray-800">
                        <td className="px-2 py-1 font-mono text-gray-400">{role}</td>
                        {h1MatrixActions.map((act) => {
                          const on = cells[role]?.has(act) ?? false;
                          return (
                            <td key={act} className="px-2 py-1 text-center">
                              <input
                                type="checkbox"
                                checked={on}
                                aria-label={`${role}-${act}`}
                                disabled={loading}
                                onChange={() => {
                                  const next: Record<string, Set<string>> = {};
                                  for (const r of h1MatrixRoles) {
                                    next[r] = new Set(cells[r] || []);
                                  }
                                  if (on) next[role].delete(act);
                                  else next[role].add(act);
                                  const folded = formFromMatrixCells(next, h1MatrixRoles);
                                  setH1Principals(folded.principals);
                                  setH1Actions(folded.actions);
                                  setH1RoleActions(folded.roleActions);
                                  pushFormToRaw({
                                    principals: folded.principals,
                                    actions: folded.actions,
                                    roleActions: folded.roleActions,
                                  });
                                }}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    ));
                  })()}
                </tbody>
              </table>
            </div>
          </div>
          <label className="text-[11px] text-gray-400 space-y-1 block">
            h1_policy JSON（与薄表单/per-role 矩阵同步；含 role_actions）
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono min-h-[96px]"
              value={h1Raw}
              onChange={(e) => {
                const v = e.target.value;
                setH1Raw(v);
                try {
                  const parsed = JSON.parse(v || '{}') as unknown;
                  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    const f = formFieldsFromH1(parsed as Record<string, unknown>);
                    setH1Effect(f.effect);
                    setH1Principals(f.principals);
                    setH1Actions(f.actions);
                    setH1ConditionRaw(f.conditionRaw);
                    setH1MaskedForm(f.masked);
                    setH1RoleActions(f.roleActions);
                  }
                } catch {
                  // 输入中：不打断
                }
              }}
            />
          </label>
          <Button type="button" size="sm" disabled={loading} onClick={() => void applyH1()}>
            应用 H.1
          </Button>
        </div>

        <div className="border-t border-gray-800 pt-3 space-y-2">
          <div className="text-[12px] text-gray-300">按角色预览（dry-run · 非 certified）</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="text-[11px] text-gray-400 space-y-1">
              entity_id
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={previewEntity}
                onChange={(e) => setPreviewEntity(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1">
              role
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                value={previewRole}
                onChange={(e) => setPreviewRole(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1">
              action
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                value={previewAction}
                onChange={(e) => setPreviewAction(e.target.value)}
              />
            </label>
            <div className="flex items-end">
              <Button type="button" size="sm" disabled={loading} onClick={() => void runPreview()}>
                预览
              </Button>
            </div>
          </div>
          <label className="text-[11px] text-gray-400 space-y-1 block">
            sample payload (JSON)
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono min-h-[64px]"
              value={previewPayload}
              onChange={(e) => setPreviewPayload(e.target.value)}
            />
          </label>
          {previewOut ? (
            <pre className="max-h-40 overflow-auto rounded border border-gray-800 bg-gray-950/70 p-2 text-[11px] text-gray-400 whitespace-pre-wrap">
              {previewOut}
            </pre>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
};

export default AboxAclPanel;
