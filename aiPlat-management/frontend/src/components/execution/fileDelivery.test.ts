import { describe, expect, it } from 'vitest';
import {
  extractCodingDeliveryText,
  parseFileDelivery,
  stripOuterFence,
} from './fileDelivery';

describe('fileDelivery', () => {
  it('splits overview from ## FILE sections', () => {
    const text = [
      '### 步骤1：分析',
      '方案 A。',
      '',
      '## FILE: frontend/src/types.ts',
      '```ts',
      'export type X = 1',
      '```',
      '',
      '## FILE: frontend/src/api/apiClient.ts',
      '```ts',
      '// TODO: auth',
      'export async function f() {}',
      '```',
    ].join('\n');
    const parsed = parseFileDelivery(text);
    expect(parsed).not.toBeNull();
    expect(parsed!.overview).toContain('步骤1');
    expect(parsed!.files.map((f) => f.path)).toEqual([
      'frontend/src/types.ts',
      'frontend/src/api/apiClient.ts',
    ]);
    expect(parsed!.files[0].body).toContain('export type X');
    expect(parsed!.files[0].body).not.toContain('```');
    expect(parsed!.files[1].body).toContain('// TODO: auth');
  });

  it('returns null without FILE headers', () => {
    expect(parseFileDelivery('只是一段说明')).toBeNull();
  });

  it('does not collapse scaffold ## FILE: to inner /health JSON', () => {
    const text = [
      '### 步骤4：最终交付',
      '',
      '## FILE: main.py',
      '```python',
      'from fastapi import FastAPI',
      'app = FastAPI()',
      '@app.get("/health")',
      'def health():',
      '    return {"status": "ok", "service": "inspection-report-skeleton"}',
      '```',
      '',
      '## FILE: README.md',
      '```markdown',
      '# skeleton',
      '```',
    ].join('\n');
    expect(extractCodingDeliveryText(text, { text })).toContain('## FILE: main.py');
    const parsed = parseFileDelivery(extractCodingDeliveryText(text, { text }));
    expect(parsed).not.toBeNull();
    expect(parsed!.files.map((f) => f.path)).toEqual(['main.py', 'README.md']);
    expect(parsed!.files[0].body).toContain('inspection-report-skeleton');
  });

  it('extracts from {text} envelope', () => {
    const body = '## FILE: a.ts\n```ts\nexport const n = 1\n```\n';
    expect(extractCodingDeliveryText('', { text: body })).toContain('## FILE:');
    expect(extractCodingDeliveryText(body, null)).toContain('## FILE:');
  });

  it('extracts nested {output:{code}} envelope', () => {
    const body = '## FILE: a.ts\n```ts\nexport const n = 1\n```\n';
    expect(extractCodingDeliveryText('', { output: { code: body } })).toContain('## FILE:');
    expect(extractCodingDeliveryText('', { text: { code: body } })).toContain('## FILE:');
  });

  it('unwraps python-repr {code, language} string (run-c896745b fullscreen)', () => {
    const body = [
      '### plan',
      '',
      '## FILE: frontend/src/types.ts',
      '```typescript',
      'export type X = string;',
      '```',
      '',
      '## FILE: frontend/src/api/apiClient.ts',
      '```typescript',
      '// TODO: auth',
      'export async function createReport() {}',
      '```',
      '',
      '## FILE: frontend/src/pages/ReportFaultPage.tsx',
      '```tsx',
      'export default function ReportFaultPage() { return null }',
      '```',
      '',
      'DONE',
    ].join('\n');
    // Faithful Python repr(dict): single quotes + \\n escapes + True
    const py =
      "{'code': '" +
      body.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n') +
      "', 'language': 'typescript', '_language_locked': True}";
    const extracted = extractCodingDeliveryText(py, null);
    expect(extracted).toContain('## FILE: frontend/src/types.ts');
    const parsed = parseFileDelivery(extracted);
    expect(parsed).not.toBeNull();
    expect(parsed!.files.map((f) => f.path)).toEqual([
      'frontend/src/types.ts',
      'frontend/src/api/apiClient.ts',
      'frontend/src/pages/ReportFaultPage.tsx',
    ]);
    // Object envelope (already parsed by API)
    expect(extractCodingDeliveryText('', { code: body, language: 'typescript' })).toContain(
      '## FILE: frontend/src/pages/ReportFaultPage.tsx',
    );
  });

  it('parses run-c66b5f style plan + three FILE delivery', () => {
    const text = [
      '### 步骤4：最优方案与关键假设',
      '',
      '**假设（因 api_contracts 未给出字段级细节，按最小可运行切片声明）**：',
      '',
      '## FILE: frontend/src/types.ts',
      '```typescript',
      '/** 约束：本文件不推断 API 格式 */',
      'export interface CreateInspectionReportRequest {',
      '  title: string;',
      '  location: string;',
      '  severity: string;',
      '  description: string;',
      '}',
      '```',
      '',
      '## FILE: frontend/src/api/apiClient.ts',
      '```typescript',
      '// TODO: auth',
      'export async function createReport() {}',
      '```',
      '',
      '## FILE: frontend/src/pages/ReportFaultPage.tsx',
      '```tsx',
      'export function ReportFaultPage() { return null }',
      '```',
    ].join('\n');
    const parsed = parseFileDelivery(text);
    expect(parsed).not.toBeNull();
    expect(parsed!.overview).toContain('步骤4');
    expect(parsed!.files.map((f) => f.path)).toEqual([
      'frontend/src/types.ts',
      'frontend/src/api/apiClient.ts',
      'frontend/src/pages/ReportFaultPage.tsx',
    ]);
    expect(parsed!.files[0].body).toContain('CreateInspectionReportRequest');
    expect(parsed!.files[1].body).toContain('// TODO: auth');
  });

  it('stripOuterFence leaves bare code', () => {
    expect(stripOuterFence('```ts\nconst x = 1\n```')).toBe('const x = 1');
  });
});
