import React from 'react';

export type AssetKind = 'agent' | 'skill' | 'tool' | 'mcp' | 'team';

const LINES: Record<AssetKind, { title: string; bullets: string[] }> = {
  agent: {
    title: 'Agent = 数字员工（编排层）',
    bullets: [
      '负责多步推理与编排，绑定 Skill / Tool / MCP',
      '不要把单次原子动作做成 Agent（应建 Tool）',
      '不要只塞一段 SOP 却零绑定（应先建 Skill 再组装）',
    ],
  },
  skill: {
    title: 'Skill = 可复用流程/能力模块',
    bullets: [
      '有明确输入输出、可被多个 Agent 调用',
      '可声明 permissions 并调用 Tool；不可再调另一个 Skill',
      '纯读写文件 / HTTP / 计算 → 优先建 Tool，而不是 Skill',
    ],
  },
  tool: {
    title: 'Tool = 原子外部能力',
    bullets: [
      '单次副作用或外部资源访问（文件、HTTP、代码沙箱等）',
      '必须可被 sys_tool_call 调用；不做多步业务编排',
      '能力在外部进程/第三方服务 → 用 MCP，而不是本进程 Tool',
    ],
  },
  mcp: {
    title: 'MCP = 外部服务协议接入',
    bullets: [
      '对接另一进程/第三方的工具面（stdio / sse / http）',
      '由 Agent 绑定使用；Skill 一般不直接绑 MCP Server',
      '本机原子读写/计算 → 用 Tool，不必上 MCP',
    ],
  },
  team: {
    title: 'Team = Agent 流水线组装',
    bullets: [
      '把多个 Agent 按阶段串成团队，不是单资源落盘',
      '对话组装只写入画布，保存后才落库',
      '缺能力时先去应用库补 Agent/Skill，再组装',
    ],
  },
};

/** Compact boundary reminder for create dialogs / forms. */
export const AssetBoundaryHint: React.FC<{ kind: AssetKind; className?: string }> = ({
  kind,
  className = '',
}) => {
  const cfg = LINES[kind];
  return (
    <details
      className={`rounded-lg border border-dark-border bg-dark-card/60 px-3 py-2 text-xs text-gray-400 ${className}`}
    >
      <summary className="cursor-pointer select-none text-gray-300 hover:text-gray-100">
        边界说明 · {cfg.title}
      </summary>
      <ul className="mt-2 list-disc pl-4 space-y-1 text-gray-500">
        {cfg.bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>
      <div className="mt-2 text-[11px] text-gray-600">
        Agent 编排 → Skill 流程 → Tool 原子 → MCP 外部服务。详见 Core CLAUDE.md §5.9–5.11。
      </div>
    </details>
  );
};

export default AssetBoundaryHint;
