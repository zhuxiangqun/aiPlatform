# microVM Linux/KVM track v1

> Parent prep: [`MICROVM_PREP.md`](./MICROVM_PREP.md)  
> Honesty: **track ≠ guest boot** · **≠ live skill tools** · **≠ isolation cert** · **`process_split_authorized=false`** · **`accuracy_claim=false`** · Darwin ineligible

## What shipped (v1)

| Piece | State |
|---|---|
| KVM / host probe (`kvm_available`, `microvm_host_ok`) | ✅ |
| Admit non-live runners under `backend=microvm` when `host_ok` + `ADMIT_RUNNERS` | ✅ |
| Allowlisted host CLI (`cli_probe` → `run_allowlisted_cli`) | ✅ |
| `skill_suite` / `security_redteam` | fixture only |
| Firecracker guest rootfs boot | ❌ deferred (`guest_boot=false`) |
| `sandbox_real_isolation` | **false** |
| Score axis `local_independence_with_microvm` | **null on Darwin**; Linux host evidence required for 5 |

## Env

```bash
export AIPLAT_EVAL_SANDBOX_BACKEND=microvm
export AIPLAT_EVAL_MICROVM_ENABLED=1
export AIPLAT_EVAL_MICROVM_BIN=/usr/bin/firecracker   # or on PATH
export AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS=1            # explicit admit
# Optional: AIPLAT_EVAL_MICROVM_CLI_TIMEOUT_SEC=10
```

Admit requires **Linux** + `/dev/kvm` + binary + enable + `ADMIT_RUNNERS=1`.  
Without admit flag: backend=`microvm` still **deny-all** (prep semantics preserved).

## Gate

```bash
# Safe on Darwin — asserts ineligible + honesty locks:
bash packages/aiplat-evaluation/scripts/microvm_linux_track_gate.sh
```

## Health fields

- `microvm_host_ok` / `microvm_admit_runners` / `kvm_available`
- `guest_boot=false`
- `sandbox_isolation=microvm_linux_track|microvm_prep`
- `skill_suite_real_tools=false` / `security_live_attacks=false` on microvm

## Out of scope

- Guest Firecracker boot / rootfs
- Live skill tools / live security attacks
- B4-S staging authorize
- Chart `a3_process_split_authorized=true`
- G2b accuracy unlock
