import { describe, expect, it } from 'vitest';
import { executeProductAsText, unwrapExecuteProduct } from './executeProduct';

const cases = [
  { id: 'SMK-001', ac_ref: 'FR-1', category: 'happy_path', question: '上报主路径', min_expectation: '成功' },
  { id: 'SMK-002', ac_ref: 'FR-2', category: 'boundary', question: '空照片', min_expectation: '拒绝' },
];

describe('unwrapExecuteProduct', () => {
  it('peels {"type":"done","answer": product-object}', () => {
    const raw = { type: 'done', answer: { mode: 'agent_conversation', test_questions: cases, total_test_cases: 2 } };
    const out = unwrapExecuteProduct(raw) as Record<string, unknown>;
    expect(out.test_questions).toHaveLength(2);
    expect((out.test_questions as { id: string }[])[0].id).toBe('SMK-001');
    expect(out).not.toHaveProperty('type');
  });

  it('peels nested {text: done-envelope-string} and pretty-prints JSON', () => {
    const product = { test_questions: cases, total_test_cases: 2 };
    const raw = { text: JSON.stringify({ type: 'done', answer: JSON.stringify(product) }) };
    const text = executeProductAsText(raw);
    expect(text).not.toContain('"type": "done"');
    expect(text).toContain('SMK-001');
    expect(text).toContain('test_questions');
    const parsed = JSON.parse(text);
    expect(parsed.test_questions).toHaveLength(2);
  });

  it('recovers truncated done envelope mid test_questions array', () => {
    const blob =
      '{"type":"done","answer":"{\\"test_questions\\":[' +
      JSON.stringify(cases[0]) +
      ',' +
      JSON.stringify(cases[1]).slice(0, 40);
    const out = unwrapExecuteProduct(blob) as Record<string, unknown>;
    expect(Array.isArray(out.test_questions)).toBe(true);
    expect((out.test_questions as unknown[]).length).toBeGreaterThanOrEqual(1);
    expect(JSON.stringify(out)).not.toMatch(/"type":"done"/);
  });
});
