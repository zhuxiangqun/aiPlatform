import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

const RELOAD_KEY = 'aiplat_chunk_reload';

function isChunkLoadError(err: unknown): boolean {
  const msg = String((err as Error)?.message || err || '');
  return /Failed to fetch dynamically imported module|Loading chunk [\d]+ failed|Importing a module script failed|error loading dynamically imported module/i.test(
    msg,
  );
}

/** Once per tab session: hard reload when a hashed chunk 404s after rebuild. */
export function reloadOnceOnChunkError(err: unknown): boolean {
  if (!isChunkLoadError(err)) return false;
  try {
    if (sessionStorage.getItem(RELOAD_KEY) === '1') return false;
    sessionStorage.setItem(RELOAD_KEY, '1');
  } catch {
    /* ignore */
  }
  window.location.reload();
  return true;
}

export function clearChunkReloadFlag(): void {
  try {
    sessionStorage.removeItem(RELOAD_KEY);
  } catch {
    /* ignore */
  }
}

/** React.lazy that retries once via full reload when vite hashed assets go stale. */
export function lazyWithRetry<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(async () => {
    try {
      const mod = await factory();
      clearChunkReloadFlag();
      return mod;
    } catch (err) {
      reloadOnceOnChunkError(err);
      throw err;
    }
  });
}
