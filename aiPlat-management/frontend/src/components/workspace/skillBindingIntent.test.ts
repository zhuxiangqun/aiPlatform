import { describe, expect, it } from 'vitest';
import {
  detectSkillBindIntent,
  ioHintForIntent,
  mcpMatchesIntent,
  permissionChipsForIntent,
  toolMatchesIntent,
} from './skillBindingIntent';

describe('skillBindingIntent', () => {
  it('detects upload from play_url / 对象存储, not as local file write', () => {
    expect(detectSkillBindIntent('接收用户上传的视频，生成 play_url')).toBe('upload');
    expect(detectSkillBindIntent('上传文件到对象存储')).toBe('upload');
  });

  it('does not match file_operations for upload intent', () => {
    expect(toolMatchesIntent('file_operations', '读写本地文件', 'upload')).toBe(false);
    expect(toolMatchesIntent('webfetch', 'HTTP GET', 'upload')).toBe(false);
    expect(toolMatchesIntent('oss_upload', 'put object', 'upload')).toBe(true);
    expect(mcpMatchesIntent('browser_server', ['browser_click'], '', 'upload')).toBe(false);
    expect(mcpMatchesIntent('aliyun_oss', ['put_object'], '', 'upload')).toBe(true);
  });

  it('upload permission chips omit pptx write / websearch', () => {
    const ids = permissionChipsForIntent('upload').chips.map((c) => c.id);
    expect(ids).toContain('llm:generate');
    expect(ids).toContain('mcp:invoke');
    expect(ids).not.toContain('tool:workspace_fs_write');
    expect(ids).not.toContain('tool:websearch');
    expect(ids).not.toContain('tool:run_command');
  });

  it('upload IO hint does not talk about pptx outline', () => {
    const h = ioHintForIntent('upload');
    expect(h.out).toMatch(/play_url/);
    expect(h.example.toLowerCase()).not.toMatch(/outline/);
  });
});
