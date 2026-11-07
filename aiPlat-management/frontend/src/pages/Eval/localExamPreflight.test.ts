import { describe, expect, it } from 'vitest';
import { isLocalModelProvider } from './localExamPreflight';

describe('localExamPreflight', () => {
  it('recognizes common local providers', () => {
    expect(isLocalModelProvider('ollama')).toBe(true);
    expect(isLocalModelProvider('LM Studio')).toBe(true);
    expect(isLocalModelProvider('vllm')).toBe(true);
    expect(isLocalModelProvider('openai_compatible_local')).toBe(true);
  });

  it('rejects remote commercial providers', () => {
    expect(isLocalModelProvider('openai')).toBe(false);
    expect(isLocalModelProvider('deepseek')).toBe(false);
    expect(isLocalModelProvider('anthropic')).toBe(false);
  });
});
