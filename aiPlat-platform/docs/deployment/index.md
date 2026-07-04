# deployment 模块（Platform Layer 2：部署与运维）

## 定位

`deployment/` 管理 aiPlat 平台的服务部署、配置和生命周期。

## 已实现能力

| 能力 | 状态 |
|------|:--:|
| 一键启动/停止（start.sh / stop.sh） | ✅ |
| 多服务并行启动（core + platform + management + frontend） | ✅ |
| 健康检查（core / platform / management） | ✅ |
| 端口管理（自动检测和释放） | ✅ |
| 进程监控（ProcessRegistry + 健康检查） | ✅ |
| 灾备脚本（backup + restore + verify） | ✅ |

## 边界

- 不管理容器化部署（Docker/K8s 为可选方案）
- 日志通过 Python logging 模块，不依赖外部收集器
- 配置文件通过环境变量和环境变量文件管理
