/**
 * Collapsible notice for Eval Center page-level banners.
 * Default collapsed to save viewport; preference persisted in localStorage.
 */
import { useCallback, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

type Props = {
  storageKey: string;
  /** Short line always visible when collapsed. */
  summary: ReactNode;
  /** Full body when expanded. */
  children: ReactNode;
  icon?: ReactNode;
  /** Border/bg/text tone classes for the shell. */
  toneClassName: string;
  testId?: string;
  /** Default open when no localStorage yet. Prefer false (collapsed). */
  defaultOpen?: boolean;
  role?: string;
  /** Extra data-* on the shell (e.g. data-error-code). */
  dataAttrs?: Record<string, string>;
  /** Override expanded body layout (default: indented notice text). */
  bodyClassName?: string;
};

function readStored(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === '1') return true;
    if (v === '0') return false;
  } catch {
    /* ignore */
  }
  return fallback;
}

export default function EvalCollapsibleBanner({
  storageKey,
  summary,
  children,
  icon,
  toneClassName,
  testId,
  defaultOpen = false,
  role = 'status',
  dataAttrs,
  bodyClassName = 'mt-2 pl-7 text-sm space-y-1',
}: Props) {
  const [open, setOpen] = useState(() => readStored(storageKey, defaultOpen));

  const toggle = useCallback(() => {
    setOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(storageKey, next ? '1' : '0');
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [storageKey]);

  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <div
      className={`rounded-lg border px-3 py-2 ${toneClassName}`}
      role={role}
      data-testid={testId}
      data-collapsed={open ? 'false' : 'true'}
      {...dataAttrs}
    >
      <button
        type="button"
        onClick={toggle}
        className="w-full flex gap-2 items-start text-left"
        aria-expanded={open}
        data-testid={testId ? `${testId}-toggle` : undefined}
      >
        {icon ? <span className="shrink-0 mt-0.5">{icon}</span> : null}
        <span className="flex-1 min-w-0 text-sm font-medium leading-snug">{summary}</span>
        <Chevron className="w-4 h-4 shrink-0 mt-0.5 opacity-80" aria-hidden />
      </button>
      {open ? <div className={bodyClassName}>{children}</div> : null}
    </div>
  );
}
