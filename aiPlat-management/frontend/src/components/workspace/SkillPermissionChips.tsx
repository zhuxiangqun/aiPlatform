import React, { useMemo } from 'react';
import { detectSkillBindIntent, permissionChipsForIntent } from './skillBindingIntent';

export function SkillPermissionChips({
  intentText,
  permissions,
  onChange,
  requireConfirmation,
  onRequireConfirmationChange,
}: {
  intentText: string;
  permissions: string[];
  onChange: (next: string[]) => void;
  requireConfirmation?: boolean;
  onRequireConfirmationChange?: (v: boolean) => void;
}) {
  const intent = useMemo(() => detectSkillBindIntent(intentText || ''), [intentText]);
  const ui = useMemo(() => permissionChipsForIntent(intent), [intent]);
  const extra = permissions.filter((p) => !ui.chips.some((c) => c.id === p));

  const toggle = (id: string) => {
    onChange(permissions.includes(id) ? permissions.filter((x) => x !== id) : [...permissions, id]);
  };

  return (
    <div className="rounded-xl border border-dark-border p-4 space-y-3">
      <div className="text-sm text-gray-200 font-medium">允许做什么？</div>
      <div className="text-xs text-gray-500">{ui.intro}</div>
      <div className="space-y-2">
        {ui.chips.map((p) => (
          <label
            key={p.id}
            className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
              permissions.includes(p.id)
                ? 'border-primary/40 bg-primary/5'
                : 'border-dark-border hover:border-gray-600'
            }`}
          >
            <input
              type="checkbox"
              className="mt-1"
              checked={permissions.includes(p.id)}
              onChange={() => toggle(p.id)}
            />
            <span>
              <span className="text-sm text-gray-100 block">{p.label}</span>
              <span className="text-[11px] text-gray-500">{p.hint}</span>
            </span>
          </label>
        ))}
        {extra.map((id) => (
          <label
            key={id}
            className="flex items-start gap-3 rounded-lg border px-3 py-2.5 border-dark-border opacity-80"
          >
            <input type="checkbox" className="mt-1" checked onChange={() => toggle(id)} />
            <span>
              <span className="text-sm text-gray-100 block">{id}</span>
              <span className="text-[11px] text-gray-500">历史勾选，与当前描述不太相关，可取消</span>
            </span>
          </label>
        ))}
      </div>
      {onRequireConfirmationChange ? (
        <label className="flex items-start gap-2 text-xs text-amber-200/90 pt-1 cursor-pointer">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={!!requireConfirmation}
            onChange={(e) => onRequireConfirmationChange(e.target.checked)}
          />
          <span>
            {ui.confirmLabel}
            <span className="block text-gray-500 mt-0.5">{ui.confirmHint}</span>
          </span>
        </label>
      ) : null}
    </div>
  );
}
