import { describe, expect, it } from 'vitest';
import { TOOLS_GLOSSARY, toolsGlossaryPromptText } from './toolsGlossary';

describe('toolsGlossary', () => {
  it('has meanings and prompt pack', () => {
    expect(TOOLS_GLOSSARY.length).toBeGreaterThan(5);
    for (const e of TOOLS_GLOSSARY) {
      expect(e.meaning.trim().length, e.term).toBeGreaterThan(8);
    }
    expect(toolsGlossaryPromptText()).toMatch(/Tool/);
  });
});
