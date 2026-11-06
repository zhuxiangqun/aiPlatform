import { describe, expect, it } from 'vitest';
import {
  APPROVAL_GLOSSARY,
  GOVERNANCE_GLOSSARY,
  approvalGlossaryText,
  governanceGlossaryText,
} from './consultantLayerA';

describe('consultantLayerA packs', () => {
  it('governance and approval packs are non-empty', () => {
    expect(GOVERNANCE_GLOSSARY.length).toBeGreaterThan(3);
    expect(APPROVAL_GLOSSARY.length).toBeGreaterThan(3);
    expect(governanceGlossaryText()).toMatch(/治理/);
    expect(approvalGlossaryText()).toMatch(/资产审批/);
  });
});
