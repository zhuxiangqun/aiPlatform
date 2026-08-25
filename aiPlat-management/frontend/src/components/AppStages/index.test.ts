/**
 * AppStage 组件注册表测试（2026-08-25）
 *
 * 验证"搭积木"扩展：注册表能解析全部声明组件、未知组件返回 null（AppPage 渲染兜底）、
 * 组件清单与 frontend_developer AGENT.md 声明对齐。
 */
import { describe, it, expect } from 'vitest';
import {
  APP_STAGE_REGISTRY,
  APP_STAGE_COMPONENT_LIST,
  resolveStageComponent,
} from './index';

describe('APP_STAGE_REGISTRY 组件注册表', () => {
  it('覆盖 8 种声明组件（含新增 markdown_viewer/stat_cards/kanban_board）', () => {
    // 此前 AGENT.md 声明了 kanban_board/stat_cards 但前端不存在 → 渲染"未知组件"
    const declared = [
      'file_upload', 'progress_poller', 'result_dashboard',
      'data_form', 'data_table', 'markdown_viewer',
      'stat_cards', 'kanban_board',
    ];
    for (const name of declared) {
      expect(APP_STAGE_REGISTRY[name], `${name} 应已注册`).toBeTruthy();
    }
    expect(Object.keys(APP_STAGE_REGISTRY)).toHaveLength(8);
  });

  it('resolveStageComponent 解析已知组件、未知返回 null', () => {
    expect(resolveStageComponent('data_form')).toBe(APP_STAGE_REGISTRY.data_form);
    expect(resolveStageComponent('markdown_viewer')).toBeTruthy();
    expect(resolveStageComponent('stat_cards')).toBeTruthy();
    expect(resolveStageComponent('kanban_board')).toBeTruthy();
    // 未知组件 → null（AppPage 渲染"未知组件"兜底卡片）
    expect(resolveStageComponent('no_such_component')).toBeNull();
  });

  it('组件清单字符串覆盖全部注册组件', () => {
    const list = APP_STAGE_COMPONENT_LIST.split('|');
    expect(list.sort()).toEqual(Object.keys(APP_STAGE_REGISTRY).sort());
  });

  it('与 frontend_developer AGENT.md 组件清单对齐（除 chat_panel 由侧边栏承担）', () => {
    const agentDeclared = [
      'file_upload', 'progress_poller', 'result_dashboard',
      'data_form', 'data_table', 'kanban_board', 'stat_cards', 'chat_panel',
    ];
    // chat_panel 由 AppPage 侧边栏 ChatWidget 承担，不进注册表
    const registered = Object.keys(APP_STAGE_REGISTRY);
    for (const name of agentDeclared) {
      if (name === 'chat_panel') continue;
      expect(registered, `${name} 应在注册表中`).toContain(name);
    }
  });
});
