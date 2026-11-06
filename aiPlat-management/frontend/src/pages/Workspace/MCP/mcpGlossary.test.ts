import { describe, expect, it } from 'vitest';
import { MCP_GLOSSARY, mcpGlossaryPromptText } from './mcpGlossary';

describe('mcpGlossary', () => {
  it('has meanings and prompt pack', () => {
    expect(MCP_GLOSSARY.length).toBeGreaterThan(5);
    for (const e of MCP_GLOSSARY) {
      expect(e.meaning.trim().length, e.term).toBeGreaterThan(8);
    }
    expect(mcpGlossaryPromptText()).toMatch(/MCP/);
  });
});
