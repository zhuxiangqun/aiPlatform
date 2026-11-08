import { describe, expect, it } from 'vitest';
import { summarizeRuntimeParts } from './examRuntimeTier';

describe('summarizeRuntimeParts', () => {
  it('keeps homogeneous tier and claim rules', () => {
    const same = summarizeRuntimeParts([
      { sub_id: 'a', runtime_tier: 'fixture', runtime_claim: false },
      { sub_id: 'b', runtime_tier: 'fixture', runtime_claim: false },
    ]);
    expect(same.mixed).toBe(false);
    expect(same.runtime_tier).toBe('fixture');
    expect(same.runtime_claim).toBe(false);

    const claimable = summarizeRuntimeParts([
      { sub_id: 'a', runtime_tier: 'pi', runtime_claim: true },
      { sub_id: 'b', runtime_tier: 'pi', runtime_claim: true },
    ]);
    expect(claimable.runtime_claim).toBe(true);
  });

  it('marks heterogeneous parts as mixed without collapsing', () => {
    const mixed = summarizeRuntimeParts([
      { sub_id: 'a', runtime_tier: 'fixture', runtime_claim: false },
      { sub_id: 'b', runtime_tier: 'pi', runtime_claim: true },
    ]);
    expect(mixed.mixed).toBe(true);
    expect(mixed.runtime_tier).toBe('mixed');
    expect(mixed.runtime_claim).toBe(false);
    expect(mixed.runtime_parts).toHaveLength(2);
  });
});
