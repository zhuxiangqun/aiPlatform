import { beforeEach, describe, expect, it } from 'vitest';
import { storedIdentityHeaders } from './identityHeaders';

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => (data.has(key) ? data.get(key)! : null),
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
    clear: () => data.clear(),
    removeItem: (key: string) => data.delete(key),
  };
}

beforeEach(() => {
  (globalThis as unknown as { localStorage: ReturnType<typeof memoryStorage> }).localStorage = memoryStorage();
});

describe('storedIdentityHeaders', () => {
  it('does not invent admin identity or a dev API key', () => {
    const headers = storedIdentityHeaders();
    expect(headers).toEqual({});
    expect(JSON.stringify(headers)).not.toContain('admin');
    expect(JSON.stringify(headers)).not.toContain('apl_dev_local');
    expect(JSON.stringify(headers)).not.toContain('kb:read');
  });

  it('forwards only values that were stored', () => {
    localStorage.setItem('active_tenant_id', 'tenant-a');
    localStorage.setItem('active_actor_id', 'user-1');
    localStorage.setItem('active_api_key', 'apl_real');
    expect(storedIdentityHeaders()).toEqual({
      'X-AIPLAT-TENANT-ID': 'tenant-a',
      'X-AIPLAT-ACTOR-ID': 'user-1',
      'X-AIPLAT-API-KEY': 'apl_real',
    });
  });
});
