import { describe, expect, it } from 'vitest';
import { buildAgentTaskExamples, buildExampleRefineHint, isGenericExampleSet, sanitizeExecutionExamples } from './executionSamples';

describe('executionSamples role recipes', () => {
  it('PM chips stay PRD and are not generic FE/codegen leftovers', () => {
    const ex = buildAgentTaskExamples({
      displayName: '产品经理',
      description: '与用户对话收集需求，生成结构化PRD',
      skillIds: ['requirement_analysis'],
      toolIds: [],
    });
    const blob = ex.map((e) => e.content).join('\n');
    expect(blob).toContain('requirement_analysis');
    expect(blob).not.toContain('code_generation');
    expect(blob).not.toContain('## FILE:');
    expect(isGenericExampleSet(ex)).toBe(false);
  });
});

describe('executionSamples eval engineer', () => {
  it('uses target_agent_id instead of QA 巡检报障 chips', () => {
    const ex = buildAgentTaskExamples({
      displayName: '评估工程师',
      description: '基于 Amazon Eval Agent 论文方法，自动为 Agent 生成评估代码',
      skillIds: [
        'eval_code_generator',
        'code_review',
        'test_case_generation',
        'code-hygiene',
      ],
      toolIds: [],
    });
    const titles = ex.map((e) => e.title).join('\n');
    const blob = ex.map((e) => e.content).join('\n');
    expect(blob).toContain('target_agent_id');
    expect(blob).toContain('qa_agent');
    expect(titles).toContain('按 agent_id 评估');
    expect(titles).not.toContain('巡检报障·用例集');
    expect(isGenericExampleSet(ex)).toBe(false);
  });
});

describe('executionSamples FE isolated recipe', () => {
  it('does not treat 禁止 FastAPI isolated examples as generic', () => {
    const ex = [
      {
        title: '前端工程师（单独测·可组装切片·无脚手架）',
        content:
          '【单独测·可组装切片】\n使用 `## FILE:`；禁止重写 Vite；禁止 Python/FastAPI\n' +
          '## FILE: frontend/src/types.ts\n## FILE: frontend/src/pages/ReportFaultPage.tsx',
      },
    ];
    expect(isGenericExampleSet(ex)).toBe(false);
  });

  it('frontend engineer fallback chips include four contracts and three pages', () => {
    const ex = buildAgentTaskExamples({
      displayName: '前端工程师',
      description: '根据 Architecture 中的 api_contracts 生成前端代码',
      skillIds: ['code_generation', 'autoreview'],
      toolIds: [],
    });
    const titles = ex.map((e) => e.title).join('\n');
    const blob = ex.map((e) => e.content).join('\n');
    expect(titles).toContain('单独测·可组装切片·无脚手架');
    expect(titles).toContain('有脚手架挂路由');
    expect(blob).toContain('ApproveFaultPage');
    expect(blob).toContain('/approve');
    expect(blob).toContain('/dispatch');
    expect(blob).toContain('body: approved, comment');
    expect(blob).toContain('body: assignee_id');
    expect(blob).toContain('禁止交付 App.tsx');
    expect(isGenericExampleSet(ex)).toBe(false);
  });
});

describe('sanitizeExecutionExamples', () => {
  it('rewrites 示例：description and tiny file_size', () => {
    const schema = {
      file: { type: 'file', required: true, description: '本地视频文件，支持MP4/MOV/AVI/MKV' },
      file_size: { type: 'integer', required: true, description: '文件大小（字节），不超过2GB' },
    };
    const poisoned = [{
      title: 'upload_video（主路径·必填）',
      content: JSON.stringify({
        file: '示例: 本地视频文件，支持MP4/MOV/AVI/MKV',
        file_size: 3,
      }),
    }];
    expect(isGenericExampleSet(poisoned)).toBe(true);
    const out = sanitizeExecutionExamples(poisoned, schema, 'upload_video');
    const obj = JSON.parse(out[0].content);
    expect(obj.file).toMatch(/\.mp4$/);
    expect(obj.file).not.toContain('示例');
    expect(obj.file_size).toBeGreaterThanOrEqual(1024);
    expect(isGenericExampleSet(out)).toBe(false);
  });

  it('buildExampleRefineHint names file and byte fields', () => {
    const hint = buildExampleRefineHint(
      {
        file: { type: 'file', required: true, description: '本地视频' },
        file_size: { type: 'integer', required: true, description: '字节不超过2GB' },
      },
      '{"file":"示例: x"}',
    );
    expect(hint).toContain('file');
    expect(hint).toContain('路径');
    expect(hint).toContain('字节');
    expect(hint).toContain('输入框草稿');
  });
});
