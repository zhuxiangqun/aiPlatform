# Flake 隔离策略（P0 W2）

## 规则

1. **禁止**无 ticket 的 `skip` / `xfail` / `pytest.mark.skip`。  
2. Flake 必须：GitHub issue 或内部 ticket ID + **owner** + **expires**（≤30 天）。  
3. 隔离区：`aiPlat-core/core/tests/flake/`（或标记 `@pytest.mark.flake` + nightly 单独 job）— **目录可后建**；P0 先立规则。  
4. 过期未修：升级为失败（CI 阻断），不得无限续期超过 2 次。  
5. 真假 flake：先复现 3 次；无法复现不得 skip。

## 模板（issue body）

```
flake: <test node id>
owner: @...
expires: YYYY-MM-DD
repro: <command>
hypothesis: ...
```

## 与 G0

本文件落地即满足 P0-13；目录/CI job 接线可在 G0 后第一周补。
