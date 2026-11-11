---
doc_type: Reference
---

# microVM Linux/KVM track v1 (+ guest_boot v2)

> Parent prep: [`MICROVM_PREP.md`](./MICROVM_PREP.md)  
> Guest boot authorize: [`MICROVM_GUEST_BOOT.md`](./MICROVM_GUEST_BOOT.md)  
> Honesty: **track ≠ live skill tools** · **≠ isolation cert** · **`process_split_authorized=false`** · **`accuracy_claim=false`** · Darwin ineligible

## What shipped

| Piece | State |
|---|---|
| KVM / host probe (`kvm_available`, `microvm_host_ok`) | ✅ |
| Admit non-live runners under `backend=microvm` when `host_ok` + `ADMIT_RUNNERS` | ✅ |
| Allowlisted host CLI (`cli_probe` → `run_allowlisted_cli`) | ✅ |
| `skill_suite` / `security_redteam` | fixture only |
| Firecracker guest boot (`GUEST_BOOT` + KERNEL/ROOTFS + InstanceStart) | ✅ see [`MICROVM_GUEST_BOOT.md`](./MICROVM_GUEST_BOOT.md) |
| `sandbox_real_isolation` | **false** |
| Score axis `local_independence_with_microvm` | **null on Darwin**; Linux host + guest_boot evidence for 5 |
| `process_split_authorized` | **false** (staging checklist) |

## Env

```bash
export AIPLAT_EVAL_SANDBOX_BACKEND=microvm
export AIPLAT_EVAL_MICROVM_ENABLED=1
export AIPLAT_EVAL_MICROVM_BIN=/usr/bin/firecracker   # or on PATH
export AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS=1            # explicit admit
# Guest boot authorize (optional; see MICROVM_GUEST_BOOT.md):
# export AIPLAT_EVAL_MICROVM_GUEST_BOOT=1
# export AIPLAT_EVAL_MICROVM_KERNEL=/path/to/vmlinux
# export AIPLAT_EVAL_MICROVM_ROOTFS=/path/to/rootfs.ext4
# Optional: AIPLAT_EVAL_MICROVM_CLI_TIMEOUT_SEC=10
```

Admit requires **Linux** + `/dev/kvm` + binary + enable + `ADMIT_RUNNERS=1`.  
Without admit flag: backend=`microvm` still **deny-all** (prep semantics preserved).

## Gate

```bash
bash packages/aiplat-evaluation/scripts/microvm_linux_track_gate.sh
bash packages/aiplat-evaluation/scripts/microvm_guest_boot_gate.sh
```

## Health fields

- `microvm_host_ok` / `microvm_admit_runners` / `kvm_available`
- `guest_boot_authorized` / `guest_boot` (true only after InstanceStart)
- `sandbox_isolation=microvm_linux_track|microvm_prep`
- `skill_suite_real_tools=false` / `security_live_attacks=false` on microvm

## Out of scope

- Live skill tools / live security attacks
- B4-S staging authorize / chart `a3_process_split_authorized=true` without checklist
- G2b accuracy unlock
