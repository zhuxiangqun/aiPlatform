# H4 配置即代码分发（distribution.yaml）— 设计文档

> 框架一 H 轴（产品化交付）从 L2→L3/L4 的关键缺口。现有基础 (`profile_packager.py`/`hermes-profile-install.sh`) 已可用，需补三个缺口：Cron 条目格式、版本解析、Profile 注册表。

last_synced: 2026-07-07
status: design
owner: H-axis (framework_one)

---

## 0. 现状

- ✅ `profile_packager.py` (`scripts/`) — 打包当前 `~/.aiplat/` 为 `distribution.yaml`（agents/skills/mcp/cron/config）
- ✅ `hermes-profile-install.sh` — 从 `distribution.yaml` 或 Git repo 一键安装
- ❌ Cron 条目格式未定义（目前 `cron: []`）
- ❌ 版本解析不存在（无 `@v1.0.0` / `@latest` 语法）
- ❌ 无 Profile 注册表（`profiles/.registry.yaml` 不存在）

## 1. distribution.yaml 完整格式规范

```yaml
# distribution.yaml — aiPlat Profile Manifest v1.0
name: "my-profile"
version: "1.0.0"
description: "My team's aiPlat configuration — PM + Architect + Backend"
generated_at: "2026-07-07T00:00:00Z"
platform:
  python: "3.13"
  os: "darwin"

agents:
  - name: "architect_agent"
    config: |
      ---
      agent_type: planning
      model: deepseek-v4-pro
      ---
      # System prompt...

skills:
  - name: "code_review"
    config: |
      ---
      name: code_review
      category: development
      execution_type: prompt
      ---
      # SOP...

mcp:
  servers:
    github:
      type: stdio
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]

# ═══ P1.1 新增: Cron 任务定义 ═══
cron:
  - name: "nightly-evolution"
    schedule: "0 3 * * *"
    goal: "run-evolution"
    profile: "default"
    timeout_s: 3600
  - name: "hourly-health-scan"
    schedule: "0 * * * *"
    goal: "health-scan"
    profile: "ops"
    timeout_s: 300

# ═══ P1.1 新增: Profile 元信息 ═══
profiles:
  - name: "default"
    description: "Primary dev profile"
    default: true
  - name: "ops"
    description: "Operations/monitoring profile"
    default: false
```

**Cron 字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|:---:|------|
| `name` | str | ✅ | 任务名（唯一，用于日志/看板） |
| `schedule` | str | ✅ | 标准 cron 表达式（5 字段：分 时 日 月 周） |
| `goal` | str | ✅ | 触发目标——对应 `GoalGoal` 的方法名或 key |
| `profile` | str | — | 任务所属 Profile（默认 `default`） |
| `timeout_s` | int | — | 超时秒数（默认 600） |

## 2. 版本解析规范

```
源代码：
  hermes profile install <source>

  <source> 格式：
    - github.com/<owner>/<repo>                    → latest
    - github.com/<owner>/<repo>@v1.0.0             → 指定版本
    - github.com/<owner>/<repo>@latest             → latest
    - github.com/<owner>/<repo>@aiplat-profile     → 指定分支
    - ./distribution.yaml                          → 本地文件

解析规则：
  1. 检测是否以 "http" 开头 → 网络
     - 检测 @version 后缀 → 版本优先
     - 否则 → @latest 语法
  2. 检测是否以 "./" 开头 → 本地文件
  3. 否则 → 错误

版本解析（GitHub API）：
  - @latest → GET /repos/<owner>/<repo>/releases/latest → 最新 release 的 zipball
  - @v1.0.0 → GET /repos/<owner>/<repo>/releases/tags/v1.0.0
  - @branch → GET /repos/<owner>/<repo>/zipball/branch
```

## 3. 设计变更清单

### 改动 1：扩展 `distribution.yaml` cron 和 profiles 格式（`profile_packager.py`）

```python
# pack_profile() 新增 cron/profile 序列化注入
def pack_profile(output_path: str = "distribution.yaml", profile_name: str = "default") -> dict:
    # ... 现有逻辑 (agents/skills/mcp) ...

    # ═══ 新增: Cron 条目收集 ═══
    cron_dir = os.path.join(config_dir, "cron")
    if os.path.isdir(cron_dir):
        for entry in os.listdir(cron_dir):
            ep = os.path.join(cron_dir, entry)
            if ep.endswith(".yaml") or ep.endswith(".json"):
                with open(ep) as f:
                    cron_data = yaml.safe_load(f) if ep.endswith(".yaml") else json.load(f)
                    dist["cron"].append(cron_data)

    # ═══ 新增: Profile 列表 ═══
    profiles_dir = os.path.join(config_dir, "profiles")
    if os.path.isdir(profiles_dir):
        for entry in os.listdir(profiles_dir):
            ep = os.path.join(profiles_dir, entry)
            if ep.endswith(".yaml") and entry != ".registry.yaml":
                with open(ep) as f:
                    pdata = yaml.safe_load(f)
                    dist["profiles"].append({"name": entry[:-5], "config": pdata})

    return dist
```

### 改动 2：更新 `hermes-profile-install.sh` 支持版本解析

```bash
# 版本解析逻辑 (插入克隆前)
if [[ "$SOURCE" == http* ]]; then
   if [[ "$SOURCE" == *@v* ]]; then
     # @v1.0.0 版本
      TAG=$(echo "$SOURCE" | sed -E 's/.*@(v[0-9.]+)/\1/')
      git clone --branch "$TAG" --depth 1 "$SOURCE_BASE" "$CLONE_DIR"
   elif [[ "$SOURCE" == *@latest ]]; then
     # @latest
     source "$SOURCE_BASE..."
     # git clone latest release (fallback: main branch)
   else
     # default — existing behavior
     git clone "$SOURCE_BASE" "$CLONE_DIR"
   fi
fi
```

### 改动 3：新增 `.registry.yaml` 跟踪已安装版本

```yaml
# ~/.aiplat/profiles/.registry.yaml
registry:
  - name: "default"
    installed_from: "https://github.com/myteam/aiplat-profiles@v1.0.0"
    installed_at: "2026-07-07T00:00:00Z"
    profile_version: "1.0.0"
  - name: "ops"
    installed_from: "https://github.com/ops/aiplat-profiles@latest"
    installed_at: "2026-07-07T12:00:00Z"
    profile_version: "2.3.0"
```

**install.sh 在 install 最后一步追加记录**：

```python
# 插入到 install.sh PYEOF 块末尾
registry_path = os.path.join(target_dir, "profiles", ".registry.yaml")
existing = {}
if os.path.exists(registry_path):
    import yaml
    with open(registry_path) as f:
        existing = yaml.safe_load(f) or {}
records = existing.get("registry", [])
records.append({"name": profile, "installed_from": source_url,
                "installed_at": datetime.utcnow().isoformat() + "Z",
                "profile_version": dist.get("version")})
existing["registry"] = records
with open(registry_path, "w") as f:
    yaml.dump(existing, f)
```

## 4. 改动文件清单

| 文件 | 改动 | 工作量 |
|------|------|:---:|
| `scripts/profile_packager.py` | 扩展 pack_profile 收集 cron + profiles | 约20行 |
| `scripts/hermes-profile-install.sh` | 版本解析 + .registry 写入 | 约40行 |
| `docs/framework/assessment-spec.yaml` | H4.declared_level 从 null→L3 | 1行 |
| 不需要新文件 | — | — |

## 5. 验证

```bash
# 1. 打包当前 profile → distribution.yaml
python3 scripts/profile_packager.py /tmp/dist.yaml
grep "cron\|profiles" /tmp/dist.yaml  # 应非空

# 2. 安装本身 → 生成 .registry.yaml
bash scripts/hermes-profile-install.sh /tmp/dist.yaml
cat ~/.aiplat/profiles/.registry.yaml  # 应有本条目

# 3. 重新评估 H 轴
python3 scripts/compute_assessment.py --quiet \
  && python3 -c "import json; d=json.load(open('docs/framework/assessment-scores.json')); print(d['frameworks']['framework_one']['axes'][8]['declared_level'])"
# → expected: L3 (no longer null)
```

## 6. 对框架评分的即时影响

| 轴 | 之前 | 之后 | 原因 |
|:--|:--|:--|:---|
| H4 | null (gap) | L3 (declared_level) | Cron 格式定义 + version resolution + registry 落地 |
| H 轴综合 | L3 (带 conflict_note) | L3 (clean, no note) | 不再有 null 缺口拖后腿 |

框架一综合分从 3.91 提升到约 4.xx ≈ L4，取决于权重重算后 H 轴贡献。

---

## 7. 依赖关系

```
H4 配置分发（本文档）
    ↓ Cron 条目格式在此定义
A2.3 看板+Cron（下份设计文档）
    ↓ Cron 注册依赖 distribution.yaml 格式
P2 Profile 命名空间隔离（远期）
```

**A2.3 不能先于 H4 实现**，因为 Cron 任务定义格式不统一，A2.3 注册的任务无法分发到多 Profile。
