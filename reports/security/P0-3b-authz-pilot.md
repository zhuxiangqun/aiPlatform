# P0-3b：Authz / IDOR / SSRF pilot（Ops）

> 配套：改进方案 §1.2 · `aiPlat-platform/builder/artifact_authz_smoke.py`  
> CLI：`python3 scripts/security_authz_pilot_cli.py`  
> **验收**：2 类 × ≥3 样本 pass + 每类负向阻断 + Owner 书面退出；**≠** `security_certification`

---

## 1. 硬退出条件（不可改口径）

```text
范围：至少 2 类 App（默认 crud、report；Owner 书面可换同类）
每类 ≥ 3 个独立生成样本
每样本 authz_smoke = pass|fail（禁止长期 na）
每类 ≥ 1 负向探针被门禁阻断
通过 =
  (2 类 × ≥3 pass)
  AND (每类 ≥1 负向阻断)
  AND (Security Owner 书面批准)
退出后：该类发布强制 authz 门
超时：启动后 60 自然日未退出 → blocked
```

---

## 2. 干跑（证明退出数学，不写正式账本）

```bash
python3 scripts/security_authz_pilot_cli.py --dry-run-exit
# 期望：after_owner.status == passed；honesty 标明 fixture only
```

---

## 3. 真人样本流程

1. 生成/部署至少 3 个 **crud** 与 3 个 **report** 样本（独立 artifact）。  
2. 对每个样本：

```bash
python3 scripts/security_authz_pilot_cli.py --probe \
  --base-url https://<sample-host> \
  --app-type crud \
  --sample-id crud-001 \
  --record
```

3. 账本默认：`$AIPLAT_HOME/builder/authz_pilot.json`（可用 `AIPLAT_AUTHZ_PILOT_PATH` / `--path`）。  
4. 查看进度：

```bash
python3 scripts/security_authz_pilot_cli.py --status
# 或 GET /platform/builder/security/authz-pilot
```

5. 样本齐备后 Owner 批准：

```bash
python3 scripts/security_authz_pilot_cli.py --approve \
  --owner "Security Owner Name" \
  --note "exit pilot; evidence <ticket-url>"
# 或 POST /platform/builder/security/authz-pilot/approve
```

6. `evaluation.status == passed` 且变更单留证据链接后，勾选 Ops 清单项 3。

---

## 4. 探针族（模板）

| 类 | 负向 | 期望 |
|---|---|---|
| crud | 无 token / 跨租户 IDOR / SSRF metadata | 401/403/404/400/422 |
| report | 无 token / 跨 org IDOR / `file://` SSRF | 同上 |
| 正向 | `/health` | 200/204（证明目标可达） |

不可达 → **fail**（不是 na）。

---

## 5. 诚实锁

- `--dry-run-exit` ≠ 真人样本已跑。  
- Owner 空批准不能 passed（样本不足仍 `in_progress`）。  
- 勾选本清单 ≠ 生成 App「已安全验收」认证。  
- 60 日未退出必须标 `blocked`，禁止无限「试点中」。
