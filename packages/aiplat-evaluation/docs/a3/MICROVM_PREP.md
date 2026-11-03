# microVM prep — blocked until KVM/runtime host

> Parent unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Linux track (policy + host allowlist): [`MICROVM_LINUX_TRACK.md`](./MICROVM_LINUX_TRACK.md)  
> Guest boot authorize: [`MICROVM_GUEST_BOOT.md`](./MICROVM_GUEST_BOOT.md)  
> Honesty: **prep ≠ runtime unlock** · **does not** flip `process_split_authorized` · **does not** admit live skill tools · `sandbox_real_isolation=false`

## Status

| Gate | State |
|---|---|
| Docker fixture sandbox (B3-L / S1) | ✅ local engineering |
| Independent microVM binary (Firecracker / equiv.) | ❌ **not on Darwin laptop** → blocked |
| `AIPLAT_EVAL_MICROVM_ENABLED=1` | optional probe only; still **no** live tools without admit |
| Linux/KVM track admit (`ADMIT_RUNNERS`) | ✅ policy shipped — see [`MICROVM_LINUX_TRACK.md`](./MICROVM_LINUX_TRACK.md) |
| Guest Firecracker boot authorize | ✅ code shipped — needs Linux+KVM+assets; see [`MICROVM_GUEST_BOOT.md`](./MICROVM_GUEST_BOOT.md) |
| Live `skill_suite` tools / redteam attacks | ❌ deferred |
| `sandbox_real_isolation` | **false** until certified runtime unlock |
| `process_split_authorized` | **false** |

## Host prerequisites

1. Linux host with KVM (or approved microVM runtime) — **not** developer macOS alone.
2. Runtime binary on PATH or `AIPLAT_EVAL_MICROVM_BIN=/abs/path`.
3. Explicit `AIPLAT_EVAL_MICROVM_ENABLED=1` for readiness probe.
4. Explicit `AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS=1` to admit non-live runners (Linux track).
5. Separate unlock slice to admit live skill tools (this prep **never** opens them).

## Probe / gate

```bash
# Always safe on laptop — asserts live tools still denied:
bash packages/aiplat-evaluation/scripts/microvm_local_prep_gate.sh

# Linux track honesty gate (Darwin ineligible):
bash packages/aiplat-evaluation/scripts/microvm_linux_track_gate.sh
bash packages/aiplat-evaluation/scripts/microvm_guest_boot_gate.sh

# Optional: point at a binary (still will not admit live tools in this slice)
export AIPLAT_EVAL_MICROVM_BIN=/usr/bin/firecracker
export AIPLAT_EVAL_MICROVM_ENABLED=1
```

Health fields (via `sandbox_health` / `/healthz` consumers):

- `microvm_ready` / `microvm_available` / `microvm_block_reason`
- `microvm_host_ok` / `kvm_available` / `microvm_admit_runners`
- `guest_boot_authorized` / `guest_boot`
- `skill_suite_real_tools=false`
- `sandbox_real_isolation=false`

## Out of scope here

- Live skill tools / live security attacks
- B4-S staging authorize (see [`B4S_PREP.md`](./B4S_PREP.md))
- Chart `a3_process_split_authorized=true`
- G2b accuracy unlock
