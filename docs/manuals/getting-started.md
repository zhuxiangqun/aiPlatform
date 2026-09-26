# aiPlat 快速入门指南

> 15 分钟从零启动到运行第一个 Agent。

## 前置条件

- Python 3.11+
- pip
- 至少一个 LLM API Key (DeepSeek/OpenAI/Qwen 等)

## Step 1: 克隆与安装 (2 分钟)

```bash
git clone https://github.com/zhuxiangqun/aiPlatform.git
cd aiPlatform
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
pip install -e aiPlat-core/ aiPlat-infra/ aiPlat-platform/ aiPlat-management/
```

## Step 2: 配置 API Key (1 分钟)

```bash
export DEEPSEEK_API_KEY="sk-your-key-here"
# 或 OpenAI:
export OPENAI_API_KEY="sk-your-key-here"
```

## Step 3: 启动服务 (2 分钟)

```bash
./start.sh
```

服务启动后：

| 端口 | 服务 | 用途 |
|:---|:---|:---|
| 8000 | Management | API 网关 + 诊断面板 |
| 8001 | Infra | 模型管理 + 基础设施 |
| 8002 | Core | Agent 引擎 + Pipeline |
| 8003 | Platform | 知识库 + Builder |

## Step 4: 验证安装 (1 分钟)

```bash
# 健康检查
curl http://localhost:8000/api/diagnostics/health/all

# 运行验证脚本
bash scripts/verify-l4-pyramid.sh
# → 预期: L5 (元循环工程)
```

## Step 5: 运行第一个 Agent (3 分钟)

```bash
# 列出可用 Agent
curl http://localhost:8000/api/core/workspace/agents

# 执行一个 Agent 任务
curl -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"用三句话解释 L4 循环工程是什么"}]}'
```

## Step 6: 查看诊断面板

浏览器打开 `http://localhost:8000/docs` → 查看全部 API 文档。

```bash
# 架构守卫检查
curl -X POST http://localhost:8000/api/diagnostics/guard/run

# 全量诊断
curl -X POST http://localhost:8000/api/diagnostics/run-all
```

## 下一步

管理端 UI（`./start.sh` 后通常为前端端口，如 `http://localhost:5173`）：

| 你要做的事 | 打开 |
|------------|------|
| 建域 / 改说明书 / 提案 apply | **知识 → 业务本体** `/knowledge/business` |
| 文档入库与检索 | **知识 → 知识库** `/knowledge/library` |
| 一句话生成应用 | **AI 应用工厂** `/app/factory` |
| FDE 现场八步交付 | **FDE 工作台** `/diagnostics/fde` |
| it-ops 组织试点 / 签收准备 | **组织试点** `/org/pilot` |

操作手册入口：[`manuals/README.md`](README.md) · 合册 [`../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md`](../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) · Org [`../contracts/ORG_L5_RUNBOOK.md`](../contracts/ORG_L5_RUNBOOK.md)。

- [API Reference](api-reference.md) — 完整 API 文档（若仓库内仍保留）
- [自主性评估报告](../framework/aiplat-complete-assessment.md) — 系统能力评估
- [验证协议](../framework/verification-protocol.md) — 独立复现验证

## 常见问题

**Q: 启动失败？**
```bash
# 检查端口占用
lsof -i :8000 -i :8001 -i :8002 -i :8003
kill <PID>
```

**Q: Agent 执行返回错误？**
```bash
# 检查 API Key
echo $DEEPSEEK_API_KEY
# 查看日志
tail -f ~/.aiplat/logs/core.log
```

**Q: 如何升级？**
```bash
git pull origin main
./start.sh  # 重启服务
```
