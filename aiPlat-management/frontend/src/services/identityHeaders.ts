/**
 * Identity headers from stored session only.
 * Missing keys stay absent — never invent admin / scopes / a dev API key.
 */

const STORED_IDENTITY: Array<[string, string]> = [
  ['active_tenant_id', 'X-AIPLAT-TENANT-ID'],
  ['active_actor_id', 'X-AIPLAT-ACTOR-ID'],
  ['active_actor_role', 'X-AIPLAT-ACTOR-ROLE'],
  ['active_scopes', 'X-AIPLAT-SCOPES'],
  ['active_release_channel', 'X-AIPLAT-RELEASE-CHANNEL'],
  ['active_api_key', 'X-AIPLAT-API-KEY'],
];

export function storedIdentityHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  try {
    for (const [key, header] of STORED_IDENTITY) {
      const value = (localStorage.getItem(key) || '').trim();
      if (value) headers[header] = value;
    }
  } catch {
    // privacy mode / no localStorage
  }
  return headers;
}
