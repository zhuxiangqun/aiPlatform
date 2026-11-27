/**
 * Layer A 加深路由必须接线 reportPageData — 防止小朱假阴性（如「没有新建客户」）。
 */
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { LAYER_A_DEEP_ROUTES } from './consultantLayerARoutes';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(HERE, '..');

function listSourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of fs.readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist' || name.startsWith('.')) continue;
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) listSourceFiles(p, out);
    else if (/\.(tsx?|jsx?)$/.test(name) && !name.endsWith('.test.ts') && !name.endsWith('.test.tsx')) {
      out.push(p);
    }
  }
  return out;
}

function corpus(): string {
  return listSourceFiles(SRC_ROOT)
    .map((f) => fs.readFileSync(f, 'utf8'))
    .join('\n');
}

describe('consultant Layer A deep-route coverage', () => {
  it('every LAYER_A_DEEP_ROUTES route has reportPageData(route) in frontend src', () => {
    const text = corpus();
    const missing: string[] = [];
    for (const { route, label } of LAYER_A_DEEP_ROUTES) {
      // allow single or double quotes; optional spaces
      const re = new RegExp(
        `reportPageData\\(\\s*['"]${route.replace(/\//g, '\\/')}['"]`,
      );
      if (!re.test(text)) missing.push(`${route} (${label})`);
    }
    expect(missing, `missing reportPageData for:\n${missing.join('\n')}`).toEqual([]);
  });

  it('FDE deep route glossary mentions 新建客户', () => {
    const fdeGloss = path.join(SRC_ROOT, 'pages/Diagnostics/fdeGlossary.ts');
    const body = fs.readFileSync(fdeGloss, 'utf8');
    expect(body).toMatch(/新建客户/);
    expect(body).toMatch(/业务认知/);
  });

  it('FDE glossary says 交付计划 does not need diagnosis', () => {
    const fdeGloss = path.join(SRC_ROOT, 'pages/Diagnostics/fdeGlossary.ts');
    const body = fs.readFileSync(fdeGloss, 'utf8');
    expect(body).toMatch(/不依赖 hasDiagnosis|不依赖诊断/);
    expect(body).toMatch(/生成计划/);
  });
});
