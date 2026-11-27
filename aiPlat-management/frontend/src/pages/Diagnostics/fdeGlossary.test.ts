import { describe, expect, it } from 'vitest';
import { FDE_GLOSSARY, fdeGlossaryPromptText } from './fdeGlossary';

describe('fdeGlossary', () => {
  it('covers 新建客户 and FDE workbench terms', () => {
    expect(FDE_GLOSSARY.length).toBeGreaterThan(5);
    const blob = fdeGlossaryPromptText();
    expect(blob).toMatch(/新建客户/);
    expect(blob).toMatch(/业务认知/);
    expect(blob).toMatch(/交付计划/);
    expect(blob).toMatch(/不依赖 hasDiagnosis|生成计划/);
    expect(blob).toMatch(/Gate0/);
    expect(blob).toMatch(/应用工厂并行/);
    expect(blob).toMatch(/\/diagnostics\/fde/);
    expect(blob).not.toMatch(/没有新建客户/);
    expect(blob.endsWith('…')).toBe(false);
  });
});
