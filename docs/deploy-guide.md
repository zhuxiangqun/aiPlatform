# aiPlat 部署指南

## 部署方式

| 方式 | 环境 | 命令 | 适用 |
|:---|:---|:---|:---|
| docker-compose | 本地开发 | `docker-compose up -d` | 单机开发/测试 |
| Helm | K8s 集群 | `helm install aiplat ./deploy/helm/aiplat` | 生产/准生产 |
| 多 AZ | K8s 跨区 | `helm install aiplat . -f values.yaml -f values-multi-az.yaml` | 生产高可用 |

## CI/CD 流程

```
git push main
  → CI: lint + test + depth + benchmark + DAST
  → Docker build & push → ghcr.io/aiplat-core:{sha}
  → [手动] helm upgrade aiplat ./deploy/helm/aiplat --set core.image.tag={sha}
  → notify-release.sh → Slack/Feishu webhook
```

## 手动部署步骤 (K8s)

```bash
# 1. 构建镜像 (CI 已完成 docker build)
# 2. 部署到 K8s
export IMAGE_TAG=$(git rev-parse --short HEAD)
helm upgrade --install aiplat ./deploy/helm/aiplat \
  --set global.imageTag=$IMAGE_TAG \
  --namespace aiplat --create-namespace

# 3. 验证部署
bash scripts/verify-deploy.sh aiplat

# 4. 回滚 (如需)
bash scripts/rollback.sh aiplat-core
```

## Docker Compose 快速部署

```bash
docker-compose up -d

# 验证
curl http://localhost:8000/health
curl http://localhost:8000/api/diagnostics/health/all
bash scripts/verify-l4-pyramid.sh
```

## 生产部署检查清单

- [ ] Helm chart 已通过 `helm lint`
- [ ] values-multi-az.yaml 已配置跨 AZ
- [ ] ArgoCD Application 已同步 (可选)
- [ ] `bash scripts/verify-deploy.sh` 全部通过
- [ ] `bash scripts/stress-test.sh` 压力测试通过
- [ ] `bash scripts/fault-injection.sh` 故障演练通过
- [ ] Grafana 仪表盘可访问
- [ ] Prometheus metrics 可抓取
