/** 业务域列表分类：说明书三 Tab / FDE 共用，避免平铺 20+ 样例 */

export const PREFERRED_DOMAIN_IDS = [
  'lock-service',
  'it-ops',
  'supply-chain',
  'procurement-mvo',
  'service-domain',
] as const;

export const PLATFORM_DOMAIN_IDS = new Set([
  'default',
  'ai-knowledge',
  'ai-solution',
  'aiplat-system',
  'enterprise-terms',
  'fde-delivery',
  'knowledge-atom',
]);

export type DomainBucket = 'preferred' | 'industry' | 'bell' | 'platform';
export type DomainFilter = DomainBucket | 'all';

export function domainBucket(id: string): DomainBucket {
  if ((PREFERRED_DOMAIN_IDS as readonly string[]).includes(id)) return 'preferred';
  if (id.startsWith('bell-')) return 'bell';
  if (PLATFORM_DOMAIN_IDS.has(id)) return 'platform';
  return 'industry';
}

export const DOMAIN_FILTER_CHIPS: {
  id: DomainFilter;
  label: string;
  hint: string;
}[] = [
  { id: 'preferred', label: '常用交付', hint: '锁服务/IT运维/供应链等，日常只看这些' },
  { id: 'industry', label: '其他行业', hint: '金融/政务/船舶等样例' },
  { id: 'bell', label: 'Bell 业务线', hint: '演示客户多线种子，非必维护' },
  { id: 'platform', label: '平台/系统', hint: '系统自用，勿当客户业务域' },
  { id: 'all', label: '全部', hint: '注册表全量' },
];
