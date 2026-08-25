/**
 * AppStage 组件注册表（2026-08-25）
 *
 * 解决"搭积木"硬编码分发：原先 AppPage.tsx 用 if 链硬编码 5 种组件，
 * 新增组件必须改 AppPage 代码。改为注册表后，新增组件 = 注册一项。
 * agent 模式生成的 app_page.json 通过 stage.component 字符串查表渲染。
 *
 * 对齐 frontend_developer AGENT.md 组件清单（8 种）：
 * file_upload / progress_poller / result_dashboard / data_form / data_table /
 * kanban_board / stat_cards / chat_panel（chat_panel 由 AppPage 侧边栏 ChatWidget 承担）。
 */
import type { ComponentType } from 'react';

import { FileUploadStage } from './FileUploadStage';
import { ProgressPoller } from './ProgressPoller';
import { ResultDashboard } from './ResultDashboard';
import { DataFormStage } from './DataFormStage';
import { DataTableStage } from './DataTableStage';
import { MarkdownViewerStage } from './MarkdownViewerStage';
import { StatCardsStage } from './StatCardsStage';
import { KanbanBoardStage } from './KanbanBoardStage';

/**
 * stage.component → React 组件 映射表。
 * LLM 生成 app_page.json 时按此清单选组件（见 frontend_developer AGENT.md 组件表）。
 */
export const APP_STAGE_REGISTRY: Record<string, ComponentType<any>> = {
  file_upload: FileUploadStage,
  progress_poller: ProgressPoller,
  result_dashboard: ResultDashboard,
  data_form: DataFormStage,
  data_table: DataTableStage,
  markdown_viewer: MarkdownViewerStage,
  stat_cards: StatCardsStage,
  kanban_board: KanbanBoardStage,
};

export function resolveStageComponent(component: string): ComponentType<any> | null {
  return APP_STAGE_REGISTRY[component] || null;
}

/** agent 模式可用的组件清单（供 LLM 生成 app_page.json 时选择）。 */
export const APP_STAGE_COMPONENT_LIST = Object.keys(APP_STAGE_REGISTRY).join('|');
