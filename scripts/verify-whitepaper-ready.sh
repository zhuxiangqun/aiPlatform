#!/usr/bin/env bash
# verify-whitepaper-ready.sh
# 五维白皮书 ready 验收脚本（扁平 volumes 适配版）
# 默认：不重写 generated_at（避免时间戳漂移）；加 --regen 才再生成。

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

REGEN=0
if [ "${1:-}" = "--regen" ]; then
  REGEN=1
fi

if [ "$REGEN" = 1 ]; then
  echo "== 1. 重新生成 (--regen) =="
  python3 scripts/generate_whitepaper_volumes.py
  python3 scripts/generate_platform_whitepaper.py >/dev/null
else
  echo "== 1. 跳过再生成（默认；需要刷新时加 --regen） =="
fi

echo "== 2. 生成器自检 =="
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check

echo "== 3. 关键文件存在 =="
for f in \
  docs/whitepaper/commercial-value-model.md \
  docs/whitepaper/cases/internal-illustrative-fde.md \
  docs/whitepaper/cases/README.md \
  docs/whitepaper/ecosystem-partner-tiers.md \
  docs/whitepaper/ecosystem-partner-commercial-template.md \
  scripts/verify-whitepaper-ready.sh
do
  test -f "$f" || fail "缺少文件：$f"
done

echo "== 4. suite 五卷 status: ready =="
ready_count="$(rg -c 'status: ready' docs/whitepaper/whitepaper-suite.yaml || true)"
if [ "${ready_count:-0}" -lt 5 ]; then
  fail "whitepaper-suite.yaml 中 status: ready 少于 5 处（实际 ${ready_count:-0}）"
fi

echo "== 5. 生成卷 source_status: ready（扁平文件，>=5 卷） =="
src_count="$(rg -l 'source_status: ready' docs/whitepaper/volumes/0*.md | wc -l | tr -d ' ')"
if [ "${src_count:-0}" -lt 5 ]; then
  fail "生成卷 source_status: ready 少于 5 个（实际 ${src_count:-0}）"
fi

echo "== 6. 阻断词检查（只扫生成卷 volumes/） =="
if rg -n '仍 gap|待填充|客户 ROI 仍为 gap|伙伴条款未形成' docs/whitepaper/volumes/0*.md; then
  fail "生成卷存在阻断性措辞"
fi

echo "== 7. 免责 / 示意声明存在性（逐条精确匹配） =="
rg -q 'authorized: false' docs/whitepaper/cases/internal-illustrative-fde.md \
  || fail "示意案例缺少 authorized: false"
rg -q 'kind: illustrative' docs/whitepaper/cases/internal-illustrative-fde.md \
  || fail "示意案例缺少 kind: illustrative"
rg -q '非客户授权' docs/whitepaper/cases/internal-illustrative-fde.md \
  || fail "示意案例缺少「非客户授权」框注"
rg -q '不构成要约' docs/whitepaper/ecosystem-partner-commercial-template.md \
  || fail "商务模板缺少「不构成要约」"
rg -q '以盖章版为准' docs/whitepaper/ecosystem-partner-commercial-template.md \
  || fail "商务模板缺少「以盖章版为准」"

echo "== 8. 总册交叉检查：无「待补」 =="
if rg -n '待补' docs/whitepaper/aiplat-platform-status-whitepaper.md; then
  fail "总册仍含「待补」措辞"
fi

echo "== 9. 生成物一致性（相对 HEAD） =="
# 忽略未跟踪杂项；白皮书生成物须与 HEAD 一致
if ! git diff HEAD --quiet -- \
  docs/whitepaper/volumes/ \
  docs/whitepaper/aiplat-platform-status-whitepaper.md \
  docs/whitepaper/whitepaper-suite.yaml \
  docs/whitepaper/WHITEPAPER_SYSTEM.md \
  scripts/generate_whitepaper_volumes.py \
  scripts/verify-whitepaper-ready.sh; then
  git diff HEAD --stat -- \
    docs/whitepaper/volumes/ \
    docs/whitepaper/aiplat-platform-status-whitepaper.md \
    scripts/verify-whitepaper-ready.sh || true
  fail "白皮书相关文件相对 HEAD 有未提交差异（若刚 --regen，请 git add + commit）"
fi

echo "OK: whitepaper ready 验收通过"
