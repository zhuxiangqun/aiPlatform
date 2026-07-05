# aiPlat 部署手册

> **新用户？** [15 分钟快速入门 →](docs/getting-started.md)
> **开发者？** [API Reference →](docs/api-reference.md) | [评估报告 →](docs/framework/aiplat-complete-assessment.md)

## 系统要求

- **操作系统**: macOS (Intel/Apple Silicon) 或 Linux (x86_64)
- **Docker Engine**: 20.10 或更高版本
- **Docker Compose**: v2 或更高版本
- **内存**: 至少 4GB
- **磁盘**: 至少 10GB 可用空间

## 部署步骤

### 1. 解压部署包

```bash
unzip deploy-kit-*.zip
cd deploy-kit
```

### 2. 配置环境变量（可选）

编辑 `.env` 文件，修改必要的配置：

```bash
# LLM API 配置（必填！否则 Agent 无法工作）
AIPLAT_LLM_API_KEY=sk-your-api-key

# 可选配置
AIPLAT_LLM_PROVIDER=deepseek
AIPLAT_LLM_BASE_URL=https://api.deepseek.com/v1
```

### 3. 启动服务

```bash
bash run.sh
```

### 4. 访问系统

浏览器打开：**http://localhost:5173**

默认账号：**admin / admin**

## 主要功能

- **平台总览**: 系统健康状态一览
- **全站自动化测试**: 自动遍历网站、生成测试用例、执行并录屏
- **Agent 管理**: 创建和管理 AI Agent
- **Skill 管理**: 创建和绑定能力模块
- **告警中心**: 系统告警集中管理
- **发行管理**: 管理员构建发布新版本

## 日常操作

### 停止服务

```bash
docker compose down
```

### 重新启动

```bash
docker compose up -d
```

### 查看日志

```bash
docker compose logs -f core        # core 服务日志
docker compose logs -f frontend    # 前端日志
docker compose logs -f management  # 管理端日志
```

### 数据备份

所有持久化数据存储在 `./data/` 目录下：

```bash
tar -czf backup-$(date +%Y%m%d).tar.gz ./data/
```

### 恢复数据

```bash
tar -xzf backup-20260523.tar.gz
```

## 版本升级

1. 下载新版本的 `deploy-kit-*.zip`
2. 解压到新的空目录（不要覆盖旧目录）
3. 将旧目录的 `./data/` 复制到新目录（迁移数据）
4. 进入新目录，执行 `bash run.sh`
5. 确认新版本正常运行后，删除旧目录

## 常见问题

### 端口冲突

如果默认端口（5173/8000/8002）已被占用，编辑 `docker-compose.yml` 修改端口映射：

```yaml
ports:
  - "8080:80"  # 将前端 80 端口映射到宿主机 8080
```

### 磁盘空间不足

清理 Docker 缓存：

```bash
docker system prune -a
```

### 镜像加载失败

确认 `.tar` 文件完整，重新加载：

```bash
docker load < images/aiplat-core.tar
```

### 无法访问

检查防火墙，确保端口 5173/8000/8002 允许入站。

## 文档导航

部署只是第一步。了解系统全貌请从 [docs/README.md](docs/README.md) 开始——按 5 分钟 → 30 分钟 → 深入子系统的分层结构引导阅读。

关键入口：
- [能力全景](AIPLAT_CAPABILITIES.md) — 398 项能力 × 代码位置
- [开发规约](CLAUDE.md) — 什么能做、什么不能做
- [路线图](AIPLAT_ROADMAP.md) — 做完了什么、下一步做什么
- [诊断报告](AIPLAT_DIAGNOSTIC_REPORT.md) — 系统健康快照

## 技术支持

如有问题，请联系管理员或查看项目文档。
