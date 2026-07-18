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

- [API Reference](api-reference.md) — 完整 API 文档
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
