# 🚀 应用层运维指南

> aiPlat-app - 部署运维与监控配置

---

## 🎯 运维关注点

作为应用层运维，您需要了解：
- **前端部署**：如何部署和管理 Web 应用
- **CLI 工具维护**：如何维护命令行工具
- **Management运维**：如何运维 Management 管理平面
- **性能优化**：如何优化应用性能
- **故障排查**：如何排查和解决问题

---

## Management 运维指南

### Management 架构

Management 管理平面为应用层提供完整的管理能力：

| 层级 | 职责 | 核心能力 |
|------|------|----------|
| Layer3 App | 应用层管理 | Agent管理、Skill管理、会话管理 |
| Layer2 Platform | 平台层管理 | 编排管理、编排执行、任务调度 |
| Layer1 Core | 核心层管理 | LLM管理、向量库管理、知识库管理 |
| Layer0 Infra | 基础设施管理 | 数据库、缓存、消息队列、对象存储 |

### Management 配置管理

**配置文件位置**：
```bash
config/app/management/
├── infrastructure.yaml   # 基础设施管理配置
├── core.yaml            # 核心层管理配置
├── platform.yaml        # 平台层管理配置
└── app.yaml             # 应用层管理配置
```

**Management 配置示例**：
```yaml
# config/app/management/infrastructure.yaml
management:
  database:
    enabled: true
    monitoring_interval: 60s
    health_check_timeout: 5s
    metrics_retention: 30d
    
  cache:
    enabled: true
    monitoring_interval: 30s
    memory_threshold: 80%
    
  messaging:
    enabled: true
    queue_size_limit: 10000
    consumer_timeout: 30s
    
  storage:
    enabled: true
    bucket_monitoring: true
    size_threshold: 10GB
```

### Management 监控指标

#### 基础设施层监控

| 指标名称 | 说明 | 正常范围 | 警告阈值 |
|----------|------|----------|----------|
| `infra_db_connection_count` | 数据库连接数 | < 80% | > 90% |
| `infra_db_query_duration_seconds` | 查询耗时 | < 100ms | > 500ms |
| `infra_cache_hit_rate` | 缓存命中率 | > 80% | < 60% |
| `infra_cache_memory_usage` | 缓存内存使用 | < 80% | > 90% |
| `infra_messaging_queue_size` | 消息队列大小 | < 1000 | > 5000 |
| `infra_storage_used_bytes` | 存储使用量 | < 80% | > 90% |

#### 核心层监控

| 指标名称 | 说明 | 正常范围 | 警告阈值 |
|----------|------|----------|----------|
| `core_llm_request_duration_seconds` | LLM 请求耗时 | < 5s | > 10s |
| `core_llm_token_usage_total` | Token 使用量 | - | > 配额 80% |
| `core_vector_search_duration_seconds` | 向量搜索耗时 | < 200ms | > 1s |
| `core_knowledge_document_count` | 文档数量 | - | - |

#### 平台层监控

| 指标名称 | 说明 | 正常范围 | 警告阈值 |
|----------|------|----------|----------|
| `platform_orchestration_active_count` | 活跃编排数 | < 100 | > 500 |
| `platform_task_pending_count` | 待执行任务数 | < 50 | > 200 |
| `platform_execution_duration_seconds` | 执行耗时 | < 30s | > 60s |

#### 应用层监控

| 指标名称 | 说明 | 正常范围 | 警告阈值 |
|----------|------|----------|----------|
| `app_agent_active_count` | 活跃 Agent 数 | - | - |
| `app_session_active_count` | 活跃会话数 | < 1000 | > 5000 |
| `app_skill_execution_duration_seconds` | Skill 执行耗时 | < 5s | > 10s |

### Management 告警规则

**告警配置文件**：`deploy/prometheus/alerts-management.yaml`

```yaml
groups:
  - name: management-alerts
    rules:
      # 基础设施告警
      - alert: DatabaseConnectionPoolExhausted
        expr: infra_db_connection_count / infra_db_connection_limit > 0.9
        for: 1m
        labels:
          severity: critical
          layer: infra
        annotations:
          summary: "数据库连接池即将耗尽"
          
      - alert: CacheMemoryHigh
        expr: infra_cache_memory_usage > 0.9
        for: 2m
        labels:
          severity: warning
          layer: infra
        annotations:
          summary: "缓存内存使用过高"
          
      - alert: MessagingQueueSizeHigh
        expr: infra_messaging_queue_size > 5000
        for: 2m
        labels:
          severity: warning
          layer: infra
        annotations:
          summary: "消息队列积压"
          
      # 核心层告警
      - alert: LLMRequestSlow
        expr: core_llm_request_duration_seconds > 10
        for: 2m
        labels:
          severity: warning
          layer: core
        annotations:
          summary: "LLM 请求响应慢"
          
      - alert: TokenQuotaWarning
        expr: core_llm_token_usage_total / core_llm_token_quota > 0.8
        for: 5m
        labels:
          severity: warning
          layer: core
        annotations:
          summary: "Token 配额不足"
          
      # 平台层告警
      - alert: TaskExecutionSlow
        expr: platform_execution_duration_seconds > 60
        for: 2m
        labels:
          severity: warning
          layer: platform
        annotations:
          summary: "任务执行超时"
          
      # 应用层告警
      - alert: ActiveSessionsHigh
        expr: app_session_active_count > 5000
        for: 2m
        labels:
          severity: warning
          layer: app
        annotations:
          summary: "活跃会话数过多"
```

### Management 日常运维

#### 健康检查

```bash
# 检查 Management 服务状态
aiplat management health check

# 检查各层健康状态
aiplat management health check --layer infra
aiplat management health check --layer core
aiplat management health check --layer platform
aiplat management health check --layer app

# 预期输出
{
  "status": "healthy",
  "layers": {
    "infra": "healthy",
    "core": "healthy",
    "platform": "healthy",
    "app": "healthy"
  },
  "last_check": "2026-04-11T10:00:00Z"
}
```

#### 状态查看

```bash
# 查看 Management 总览
aiplat management status

# 查看基础设施层状态
aiplat management status infra

# 查看核心层状态
aiplat management status core

# 预期输出
Layer: infra
Status: healthy
Components:
  - Database: healthy (connections: 45/100)
  - Cache: healthy (hit_rate: 95%)
  - Messaging: healthy (queue_size: 12)
  - Storage: healthy (usage: 25GB/100GB)
```

#### 性能监控

```bash
# 查看 Management 性能指标
aiplat management metrics

# 查看特定层性能
aiplat management metrics --layer core

# 导出性能报告
aiplat management metrics --export performance_report.json
```

#### 日志管理

```bash
# 查看 Management 日志
aiplat management logs --tail 100

# 按层级过滤日志
aiplat management logs --layer infra --level ERROR

# 搜索特定错误
aiplat management logs --search "connection failed"

# 日志文件位置
/var/log/aiplatform/management/
├── infra.log       # 基础设施层日志
├── core.log        # 核心层日志
├── platform.log    # 平台层日志
├── app.log         # 应用层日志
└── management.log  # Management 主日志
```

### Management 故障排查

#### 基础设施层故障

**数据库连接问题**：
```bash
# 检查数据库连接
aiplat management infra database check

# 查看连接池状态
aiplat management infra database pool-status

# 重置连接池
aiplat management infra database pool-reset
```

**缓存问题**：
```bash
# 检查缓存状态
aiplat management infra cache status

# 清理缓存
aiplat management infra cache clear

# 重启缓存服务
aiplat management infra cache restart
```

**消息队列问题**：
```bash
# 检查队列状态
aiplat management infra messaging status

# 查看队列详情
aiplat management infra messaging queues

# 重试失败消息
aiplat management infra messaging retry-failed
```

#### 核心层故障

**LLM 服务问题**：
```bash
# 检查 LLM 服务状态
aiplat management core llm status

# 测试 LLM 连接
aiplat management core llm test --model gpt-4

# 重置 LLM 连接
aiplat management core llm reset
```

**向量库问题**：
```bash
# 检查向量库状态
aiplat management core vector status

# 重建索引
aiplat management core vector rebuild-index

# 清理无效向量
aiplat management core vector cleanup
```

**知识库问题**：
```bash
# 检查知识库状态
aiplat management core knowledge status

# 检查文档处理队列
aiplat management core knowledge queue

# 重新处理失败文档
aiplat management core knowledge reprocess-failed
```

#### 平台层故障

**编排执行问题**：
```bash
# 检查编排状态
aiplat management platform orchestration status

# 查看执行历史
aiplat management platform orchestration history

# 取消挂起的编排
aiplat management platform orchestration cancel-pending
```

**任务调度问题**：
```bash
# 检查任务队列
aiplat management platform task queue

# 清理超时任务
aiplat management platform task cleanup-timeout

# 重试失败任务
aiplat management platform task retry-failed
```

#### 应用层故障

**Agent 服务问题**：
```bash
# 检查 Agent 状态
aiplat management app agent status

# 重启异常 Agent
aiplat management app agent restart --name <agent-name>

# 查看 Agent 日志
aiplat management app agent logs --name <agent-name>
```

**会话问题**：
```bash
# 查看活跃会话
aiplat management app session list --active

# 清理超时会话
aiplat management app session cleanup-timeout

# 强制关闭会话
aiplat management app session close --id <session-id>
```

### Management 最佳实践

#### 监控最佳实践

1. **分层监控**：按层级设置不同的告警阈值
2. **定期巡检**：每日检查健康状态和性能指标
3. **容量规划**：根据监控数据提前规划资源
4. **日志归档**：定期归档和清理日志

#### 运维最佳实践

1. **自动化运维**：使用 Management CLI 自动化日常任务
2. **定期备份**：备份配置和关键数据
3. **故障演练**：定期进行故障恢复演练
4. **文档更新**：及时更新运维文档

---

## 🚀 部署配置

### 环境要求

#### Web 前端

| 组件 | 版本要求 | 用途 | 备注 |
|------|----------|------|------|
| Node.js | 18+ | 构建环境 | 必须 |
| Nginx | 1.20+ | 反向代理 | 生产必须 |
| CDN | - | 静态资源加速 | 可选 |

#### CLI 工具

| 组件 | 版本要求 | 用途 | 备注 |
|------|----------|------|------|
| Python | 3.10+ | 运行环境 | 必须 |

---

### 部署方式

#### 静态部署（Web）

| 配置项 | 最低要求 | 推荐配置 |
|--------|----------|----------|
| CPU | 1核 | 2核 |
| 内存 | 1 GB | 2 GB |
| 磁盘 | 10 GB | 20 GB |

**构建和部署**：
```bash
# 1. 安装依赖
cd aiPlat-app/web
pnpm install

# 2. 构建
pnpm build

# 3. 上传到服务器
scp -r dist/* user@server:/var/www/ai-platform/

# 4. 配置 Nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ai-platform
sudo ln -s /etc/nginx/sites-available/ai-platform /etc/nginx/sites-enabled/
sudo nginx -s reload
```

**Nginx 配置**：
```nginx
# deploy/nginx.conf
server {
    listen 80;
    server_name app.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name app.example.com;
    
    ssl_certificate /etc/ssl/certs/ai-platform.crt;
    ssl_certificate_key /etc/ssl/private/ai-platform.key;
    
    root /var/www/ai-platform;
    index index.html;
    
    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API 代理
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
    
    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

---

#### 容器部署（Web）

**Docker 构建**：
```dockerfile
# Dockerfile.web
FROM node:18-alpine AS builder
WORKDIR /app
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM nginx:1.20-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Docker Compose**：
```yaml
# deploy/docker-compose.web.yaml
version: '3.8'
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile.web
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./ssl:/etc/ssl:ro
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
```

---

#### Kubernetes 部署（Web）

```yaml
# deploy/k8s/web.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-platform-web
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: web
        image: ai-platform/web:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: ai-platform-web
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 80
  selector:
    app: ai-platform-web
```

---

#### CLI 工具部署

**打包和发布**：
```bash
# 1. 构建 CLI
cd aiPlat-app/cli
python -m build

# 2. 发布到 PyPI
twine upload dist/*

# 3. 用户安装
pip install aiplat-cli
```

**配置文件**：
```bash
# 配置文件位置
~/.aiplat/config.yaml

# 初始化配置
aiplat config init

# 编辑配置
vi ~/.aiplat/config.yaml
```

---

### 配置文件

**前端环境配置**：`.env`

```bash
# .env
VITE_API_URL=https://api.example.com
VITE_APP_ENV=production
VITE_APP_VERSION=1.0.0
VITE_ENABLE_ANALYTICS=true
VITE_SENTRY_DSN=https://xxx@sentry.io/xxx
```

**前端构建配置**：`vite.config.ts`

```typescript
// vite.config.ts
export default defineConfig({
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'terser',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          utils: ['lodash', 'axios']
        }
      }
    }
  }
})
```

**CLI 配置**：`config/app/cli.yaml`

```yaml
# config/app/cli.yaml
cli:
  api_url: https://api.example.com
  timeout: 30
  output_format: table
  
logging:
  level: INFO
  file: ~/.aiplat/logs/cli.log
  
cache:
  enabled: true
  ttl: 3600
```

---

## 📊 监控

### 前端监控指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `page_load_time` | 页面加载时间 | < 2s | > 3s | > 5s |
| `first_contentful_paint` | 首屏渲染时间 | < 1s | > 1.5s | > 3s |
| `largest_contentful_paint` | 最大内容渲染 | < 2s | > 3s | > 5s |
| `cumulative_layout_shift` | 布局偏移 | < 0.1 | > 0.25 | > 0.5 |
| `first_input_delay` | 首次输入延迟 | < 100ms | > 300ms | > 500ms |
| `js_error_rate` | JavaScript 错误率 | < 0.1% | > 1% | > 5% |

---

### CLI 监控指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `cli_command_duration_seconds` | 命令执行耗时 | < 5s | > 10s | > 30s |
| `cli_command_success_rate` | 命令成功率 | > 95% | < 90% | < 80% |
| `cli_command_error_total` | 命令错误数 | < 10/min | > 50/min | > 100/min |
| `cli_active_users` | 活跃用户数 | - | - | - |

---

### 网络监控指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `http_request_duration_seconds` | API 请求耗时 | < 500ms | > 1s | > 2s |
| `http_request_errors_total` | API 错误数 | < 10/min | > 50/min | > 100/min |
| `websocket_connection_count` | WebSocket 连接数 | < 100 | > 500 | > 1000 |
| `cdn_hit_rate` | CDN 命中率 | > 90% | < 80% | < 60% |

---

### 监控工具配置

#### Sentry（前端错误监控）

```javascript
// src/sentry.ts
import * as Sentry from '@sentry/react';

Sentry.init({
  dsn: process.env.VITE_SENTRY_DSN,
  environment: process.env.VITE_APP_ENV,
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0.1,
  integrations: [
    new Sentry.BrowserTracing(),
    new Sentry.Replay(),
  ],
});
```

#### Google Analytics（用户行为分析）

```javascript
// src/analytics.ts
import ReactGA from 'react-ga4';

ReactGA.initialize(process.env.VITE_GA_TRACKING_ID);
ReactGA.send('pageview');
```

---

### 告警规则

**告警配置文件**：`deploy/prometheus/alerts-app.yaml`

```yaml
groups:
  - name: app-alerts
    rules:
      - alert: HighPageLoadTime
        expr: page_load_time > 3000
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "页面加载时间过长"
          
      - alert: HighJSErrorRate
        expr: js_error_rate > 0.01
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "JavaScript 错误率过高"
          
      - alert: HighCLICommandDuration
        expr: cli_command_duration_seconds > 10
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "CLI 命令执行时间过长"
```

---

## 🔧 维护

### Web 前端维护

**查看前端状态**：
```bash
# 检查 Nginx 状态
systemctl status nginx

# 检查前端版本
curl https://app.example.com/version

# 检查静态资源
ls -la /var/www/ai-platform/

# 检查 SSL 证书
openssl x509 -in /etc/ssl/certs/ai-platform.crt -text -noout
```

**更新前端**：
```bash
# 1. 构建新版本
cd aiPlat-app/web
pnpm build

# 2. 备份旧版本
mv /var/www/ai-platform /var/www/ai-platform.bak

# 3. 部署新版本
cp -r dist /var/www/ai-platform

# 4. 验证
curl https://app.example.com/health

# 5. 如需回滚
mv /var/www/ai-platform.bak /var/www/ai-platform
```

**清理缓存**：
```bash
# 清理 Nginx 缓存
rm -rf /var/cache/nginx/*

# 清理 CDN 缓存（如使用）
aiplat cdn purge --all
```

---

### CLI 工具维护

**查看 CLI 状态**：
```bash
# 查看 CLI 版本
aiplat --version

# 查看配置
aiplat config show

# 检查 CLI 健康状态
aiplat doctor
```

**更新 CLI**：
```bash
# 更新到最新版本
pip install --upgrade aiplat-cli

# 或使用 pipx
pipx upgrade aiplat-cli
```

**清理缓存**：
```bash
# 清理 CLI 缓存
aiplat cache clear

# 清理日志
rm -rf ~/.aiplat/logs/*.log
```

---

### 性能优化

#### 前端优化

**代码分割**：
```javascript
// 动态导入
const Module = lazy(() => import('./Module'));

// 路由分割
const routes = [
  {
    path: '/dashboard',
    component: lazy(() => import('./pages/Dashboard')),
  },
];
```

**资源优化**：
```bash
# 分析包大小
pnpm build --analyze

# 压缩图片
find public -name "*.png" -exec pngquant --quality=80-90 -- {} --

# 压缩 JS/CSS
pnpm build --minify
```

**CDN 优化**：
```nginx
# Nginx 配置
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    add_header CDN-Cache-Control "max-age=31536000";
}
```

---

### 日志管理

**前端日志收集**：

| 日志类型 | 存储位置 | 保留时长 |
|----------|----------|----------|
| 错误日志 | Sentry | 30天 |
| 性能日志 | 监控服务 | 7天 |
| 用户行为 | Google Analytics | 14个月 |

**CLI 日志管理**：

| 日志类型 | 文件路径 | 保留时长 |
|----------|----------|----------|
| 错误日志 | `~/.aiplat/logs/error.log` | 7天 |
| 运行日志 | `~/.aiplat/logs/cli.log` | 7天 |

**日志查询**：
```bash
# 查看最近的 CLI 错误
grep '"level":"ERROR"' ~/.aiplat/logs/cli.log | tail -50

# 查看特定命令的日志
grep '"command":"agent run"' ~/.aiplat/logs/cli.log

# 统计错误类型
grep '"level":"ERROR"' ~/.aiplat/logs/cli.log | jq .error.type | sort | uniq -c
```

---

## 🐛 故障排查

### 常见问题排查

#### 页面加载失败

**现象**：页面无法加载或白屏

**排查命令**：
```bash
# 1. 检查 Nginx 状态
systemctl status nginx

# 2. 检查静态文件
ls -la /var/www/ai-platform/index.html

# 3. 检查 CDN 状态
curl -I https://cdn.example.com/static/js/main.js

# 4. 检查浏览器控制台（在浏览器中）
# 打开开发者工具 -> Console 标签

# 5. 检查网络请求
curl -I https://app.example.com

# 6. 检查 SSL 证书
openssl s_client -connect app.example.com:443
```

**常见原因与解决**：

| 原因 | 解决方案 |
|------|----------|
| 静态文件不存在 | 重新构建和部署 |
| Nginx 配置错误 | 检查 Nginx 配置 |
| SSL 证书过期 | 更新 SSL 证书 |
| CDN 故障 | 检查 CDN 状态，临时绕过 |

---

#### JavaScript 错误

**现象**：页面出现 JavaScript 错误

**排查命令**：
```bash
# 1. 查看 Sentry 错误
# 登录 Sentry 控制台查看错误详情

# 2. 检查源码版本
curl https://app.example.com/version

# 3. 检查构建产物
ls -la /var/www/ai-platform/static/js/

# 4. 检查环境变量
grep VITE_ .env
```

**解决步骤**：
1. 检查 Sentry 中的错误详情
2. 定位错误源码
3. 修复错误
4. 重新构建和部署

---

#### CLI 命令失败

**现象**：CLI 命令执行失败

**排查命令**：
```bash
# 1. 检查 CLI 版本
aiplat --version

# 2. 检查配置文件
cat ~/.aiplat/config.yaml

# 3. 检查 API 连接
curl https://api.example.com/health

# 4. 检查认证令牌
aiplat auth status

# 5. 查看详细日志
aiplat <command> --verbose

# 6. 检查网络连接
ping api.example.com
```

**常见原因与解决**：

| 原因 | 解决方案 |
|------|----------|
| CLI 版本过低 | 更新 CLI：`pip install --upgrade aiplat-cli` |
| 配置文件错误 | 检查配置文件格式 |
| API 连接失败 | 检查 API 端点配置 |
| 认证令牌过期 | 重新登录：`aiplat auth login` |

---

#### 性能问题

**现象**：页面加载慢或卡顿

**排查命令**：
```bash
# 1. 检查资源大小
du -sh /var/www/ai-platform/static/js/
du -sh /var/www/ai-platform/static/css/

# 2. 检查 Nginx 性能
nginx -t
top -p $(pgrep nginx)

# 3. 检查网络延迟
curl -w "@curl-format.txt" -o /dev/null -s https://app.example.com

# 4. 使用 Lighthouse 分析
lighthouse https://app.example.com --view

# 5. 检查 CDN 命中率
aiplat cdn stats
```

**解决步骤**：
1. 优化资源大小（压缩、代码分割）
2. 启用 CDN 缓存
3. 优化图片和字体
4. 使用懒加载

---

### 健康检查

**健康检查端点**：

| 端点 | 路径 | 说明 |
|------|------|------|
| 前端健康 | `GET /health` | 前端服务状态 |
| 前端版本 | `GET /version` | 前端版本信息 |

**健康检查命令**：
```bash
# 检查前端服务状态
curl https://app.example.com/health

# 检查前端版本
curl https://app.example.com/version

# 检查 CLI 健康状态
aiplat doctor

# 预期响应
{
  "status": "healthy",
  "version": "1.0.0",
  "build_time": "2026-04-09T10:00:00Z"
}
```

---

### 紧急恢复

| 场景 | 操作 | 预计恢复时间 |
|------|------|--------------|
| 前端服务不可用 | 重启 Nginx：`systemctl restart nginx` | 30秒 |
| 静态文件损坏 | 从备份恢复或重新构建 | 5分钟 |
| SSL 证书过期 | 更新证书：`certbot renew` | 5分钟 |
| CDN 故障 | 临时绕过 CDN，直接访问源站 | 2分钟 |
| CLI 无法使用 | 重新安装或降级版本 | 2分钟 |

---

## 📦 备份与恢复

### 备份策略

| 数据类型 | 备份频率 | 保留时长 | 备份方式 |
|----------|----------|----------|----------|
| 静态文件 | 每次部署 | 30天 | 文件复制 |
| 配置文件 | 每次变更 | 永久 | Git |
| SSL 证书 | 每次更新 | 永久 | 文件复制 |
| CDN 缓存 | - | - | 自动刷新 |

### 备份命令

```bash
# 备份静态文件
tar -czf web_backup_$(date +%Y%m%d).tar.gz /var/www/ai-platform/

# 备份配置文件
tar -czf config_backup_$(date +%Y%m%d).tar.gz deploy/ config/

# 备份 SSL 证书
cp /etc/ssl/certs/ai-platform.crt /backup/ssl/
cp /etc/ssl/private/ai-platform.key /backup/ssl/
```

### 恢复命令

```bash
# 恢复静态文件
tar -xzf web_backup_20260409.tar.gz -C /

# 恢复配置文件
tar -xzf config_backup_20260409.tar.gz

# 恢复 SSL 证书
cp /backup/ssl/ai-platform.crt /etc/ssl/certs/
cp /backup/ssl/ai-platform.key /etc/ssl/private/
systemctl restart nginx
```

---

## 🔗 相关链接

- [← 返回应用层文档](../../index.md)
- [架构师指南 →](../architect/index.md)
- [开发者指南 →](../developer/index.md)

---

*最后更新: 2026-04-09*
