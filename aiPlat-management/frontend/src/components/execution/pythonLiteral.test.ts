import { describe, expect, it } from 'vitest';
import { pythonLiteralToJsonText, tryParseJsonOrPythonLiteral } from './pythonLiteral';

describe('pythonLiteralToJsonText', () => {
  it('decodes \\n inside python string so code newlines survive', () => {
    const src =
      "{'code': '## FILE: api/v1/inspection/reports.py\\n\\n```python\\nfrom fastapi import APIRouter\\n', 'language': 'python'}";
    const jsonText = pythonLiteralToJsonText(src);
    expect(jsonText).toBeTruthy();
    const obj = JSON.parse(jsonText!);
    expect(obj.language).toBe('python');
    expect(obj.code).toContain('\n');
    expect(obj.code).toContain('## FILE: api/v1/inspection/reports.py');
    expect(obj.code).toContain('from fastapi import APIRouter');
    // Must NOT collapse to reports.pynn```pythonnfrom
    expect(obj.code).not.toMatch(/reports\.pynn/);
    expect(obj.code).not.toMatch(/pythonnfrom/);
  });

  it('tryParseJsonOrPythonLiteral returns object', () => {
    const src = "{'code': ' const x = 1\\n', 'language': 'typescript'}";
    const obj = tryParseJsonOrPythonLiteral(src) as { code: string; language: string };
    expect(obj.language).toBe('typescript');
    expect(obj.code).toContain('const x = 1\n');
  });

  it('does not scrape /health JSON from a ## FILE python fence', () => {
    const md = [
      '## FILE: main.py',
      '```python',
      'def health():',
      '    return {"status": "ok", "service": "inspection-report-skeleton"}',
      '```',
    ].join('\n');
    expect(tryParseJsonOrPythonLiteral(md)).toBeNull();
  });
});
