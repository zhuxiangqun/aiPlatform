import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, Wrench, Server, FileText, Database, Layers, Key, Settings2, Globe, Activity, Box } from 'lucide-react';
import { skillApi, toolApi, mcpApi, knowledgeApi } from '../../../services';

interface ResourceCard {
  title: string;
  icon: React.ReactNode;
  count: number;
  desc: string;
  path: string;
  color: string;
}

const Resources: React.FC = () => {
  const navigate = useNavigate();
  const [counts, setCounts] = useState({ skills: 0, tools: 0, mcp: 0, kb: 0 });

  useEffect(() => {
    Promise.all([
      skillApi.list({ limit: 500 }).catch(() => ({ skills: [] })),
      toolApi.list({ limit: 200 }).catch(() => ({ tools: [] })),
      mcpApi.listServers().catch(() => ({ servers: [] })),
      knowledgeApi.listCollections().catch(() => ({ collections: [] })),
    ]).then(([sRes, tRes, mRes, kRes]: any[]) => {
      setCounts({
        skills: sRes?.total || sRes?.skills?.length || 0,
        tools: tRes?.total || tRes?.tools?.length || 0,
        mcp: (mRes as any)?.servers?.length || 0,
        kb: (kRes as any)?.total || (kRes as any)?.collections?.length || 0,
      });
    });
  }, []);

  const resources: ResourceCard[] = [
    { title: 'Skills', icon: <Zap className="w-8 h-8" />, count: counts.skills, desc: 'AI 能力单元：引擎内置 25 + 工作区 19，声明式 SKILL.md 配置', path: '/core/skills', color: 'text-amber-400 border-amber-500/30 bg-amber-500/5' },
    { title: 'Tools', icon: <Wrench className="w-8 h-8" />, count: counts.tools, desc: '原子操作工具：搜索引擎/计算器/HTTP/数据库/代码执行/文件操作', path: '/core/tools', color: 'text-purple-400 border-purple-500/30 bg-purple-500/5' },
    { title: 'MCP Servers', icon: <Server className="w-8 h-8" />, count: counts.mcp, desc: 'Model Context Protocol 服务器：连接外部工具服务到 Agent 和工作流', path: '/core/mcp', color: 'text-cyan-400 border-cyan-500/30 bg-cyan-500/5' },
    { title: 'Prompts', icon: <FileText className="w-8 h-8" />, count: 0, desc: 'Prompt 模板库：可复用的提示词模板，支持变量插入和版本管理', path: '/core/prompts', color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/5' },
    { title: 'Memory', icon: <Database className="w-8 h-8" />, count: 0, desc: '记忆系统：Working/Episodic/Semantic 三层架构，会话上下文持久化', path: '/core/memory', color: 'text-rose-400 border-rose-500/30 bg-rose-500/5' },
    { title: 'Workflow', icon: <Layers className="w-8 h-8" />, count: 0, desc: '工作流编辑器：拖拽排序 Pipeline 阶段，配置 Agent/Skill/Model', path: '/core/workflow-editor', color: 'text-blue-400 border-blue-500/30 bg-blue-500/5' },
    { title: 'Workflow 画布', icon: <Box className="w-8 h-8" />, count: 0, desc: 'ReactFlow 可视化画布：自由拖拽节点+连线+Agent面板+双击编辑', path: '/core/workflow-canvas', color: 'text-violet-400 border-violet-500/30 bg-violet-500/5' },
    { title: 'Credentials', icon: <Key className="w-8 h-8" />, count: 0, desc: '凭证管理：API Key / Token 集中管理，绑定到工具后 Agent 自动调用外部服务', path: '/core/credentials', color: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/5' },
    { title: 'Variables', icon: <Settings2 className="w-8 h-8" />, count: 0, desc: '变量管理：全局/工作流变量定义，通过 {{{{变量名}}}} 在 Agent SOP 中引用', path: '/core/variables', color: 'text-indigo-400 border-indigo-500/30 bg-indigo-500/5' },
    { title: 'Knowledge Base', icon: <Globe className="w-8 h-8" />, count: counts.kb, desc: '知识库管理：文档上传/索引/检索，RAG Pipeline 完整支持', path: '/platform/kb', color: 'text-teal-400 border-teal-500/30 bg-teal-500/5' },
    { title: 'Runs History', icon: <Activity className="w-8 h-8" />, count: 0, desc: '运行历史：Agent 和 Pipeline 的执行记录、通过率、耗时分析', path: '/diagnostics/runs', color: 'text-red-400 border-red-500/30 bg-red-500/5' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">资源管理</h1>
        <p className="text-sm text-gray-400 mt-1">统一管理所有 AI 资源：Skills、Tools、MCP、Prompts、Memory、Workflow</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {resources.map((r, i) => (
          <motion.div
            key={r.path}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            onClick={() => navigate(r.path)}
            className={`rounded-xl border p-5 cursor-pointer hover:scale-[1.02] transition-all ${r.color}`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className={r.color.split(' ')[0]}>{r.icon}</div>
              <span className="text-2xl font-bold text-gray-100">{r.count > 0 ? r.count : '—'}</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-100 mb-1">{r.title}</h3>
            <p className="text-xs text-gray-400 leading-relaxed">{r.desc}</p>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default Resources;
