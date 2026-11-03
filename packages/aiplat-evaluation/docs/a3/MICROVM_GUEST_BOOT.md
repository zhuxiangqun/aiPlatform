# microVM guest_boot + authorize (v2)

> Parent track: [`MICROVM_LINUX_TRACK.md`](./MICROVM_LINUX_TRACK.md)  
> Honesty: **guest_boot authorize ≠ `process_split_authorized`** · **≠ live skill tools** · **≠ isolation cert** · **`accuracy_claim=false`** · Darwin ineligible

## What shipped

| Piece | State |
|---|---|
| Explicit guest_boot authorize flag `AIPLAT_EVAL_MICROVM_GUEST_BOOT=1` | ✅ |
| Kernel + rootfs assets (`AIPLAT_EVAL_MICROVM_KERNEL` / `_ROOTFS`) | ✅ required |
| Firecracker API probe (`probe_guest_boot` → `InstanceStart`) | ✅ |
| `guest_boot=true` only after successful InstanceStart (process cache) | ✅ |
| Darwin / no-KVM | always `guest_boot=false` / not authorized |
| `process_split_authorized` | **false** (staging checklist + signed live still required) |
| `sandbox_real_isolation` | **false** |

## Env

```bash
export AIPLAT_EVAL_SANDBOX_BACKEND=microvm
export AIPLAT_EVAL_MICROVM_ENABLED=1
export AIPLAT_EVAL_MICROVM_BIN=/usr/bin/firecracker
export AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS=1
# Authorize guest boot attempt (microVM-track authorize — NOT process_split):
export AIPLAT_EVAL_MICROVM_GUEST_BOOT=1
export AIPLAT_EVAL_MICROVM_KERNEL=/path/to/vmlinux
export AIPLAT_EVAL_MICROVM_ROOTFS=/path/to/rootfs.ext4
# Optional: AIPLAT_EVAL_MICROVM_BOOT_TIMEOUT_SEC=15
```

Authorize requires **Linux** + `/dev/kvm` + binary + enable + kernel/rootfs files + `GUEST_BOOT=1`.

## Gate

```bash
# Safe on Darwin — asserts not authorized + process_split locked:
bash packages/aiplat-evaluation/scripts/microvm_guest_boot_gate.sh
```

## process_split authorize (still locked)

```bash
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
# ready_to_authorize remains false until SPLIT_CHECKLIST all ✅ + signed live
# Do NOT confuse guest_boot authorize with chart a3_process_split_authorized=true
```

## Out of scope

- Live skill tools / live security attacks
- B4-S staging host + PITR live (needed for process_split flip)
- Chart `a3_process_split_authorized=true` without checklist
- G2b accuracy unlock
- Claiming `sandbox_real_isolation=true`
