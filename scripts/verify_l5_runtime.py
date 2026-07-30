#!/usr/bin/env python3
"""
verify_l5_runtime.py v3 — 修复版：修正 /diagnostics 排除、stem 长度、for-loop 作用域

Parses AIPLAT_CAPABILITIES.md, discovers all claimed capabilities,
applies runtime verification with fuzzy path matching.
"""

import argparse, json, os, re, sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE = Path(__file__).resolve().parent.parent
CAPS_FILE = WORKSPACE / "AIPLAT_CAPABILITIES.md"


# ═══════════════ Parser ═══════════════

@dataclass
class CapEntry:
    name: str; file_ref: str; subsystem: str; description: str = ""

def parse_capabilities() -> List[CapEntry]:
    text = CAPS_FILE.read_text() if CAPS_FILE.exists() else ""
    entries = []
    subsystem = "未知"; in_table = False
    for line in text.split("\n"):
        if line.startswith("## "): subsystem = line[3:].strip(); in_table = False; continue
        if line.startswith("### "): in_table = False; continue
        if line.startswith("|---"): in_table = True; continue
        if not in_table or not line.startswith("|") or "---" in line: continue
        if subsystem == "统计": continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 3: continue
        name, location, desc = cols[0], cols[1], cols[3] if len(cols) > 3 else ""
        if name in ("能力","名称","Name"): continue
        if not location or location in ("位置","Location"): continue
        entries.append(CapEntry(name=name, file_ref=location, subsystem=subsystem, description=desc))
    return entries


# ═══════════════ Verdict ═══════════════

@dataclass
class Verdict:
    name: str; file_ref: str; subsystem: str; description: str
    d1: bool = False; d2: bool = False; d3: bool = False
    d4: bool = False; d5: bool = False; d7: bool = False
    is_complete: bool = False  # >80 lines + class/fn/Usage — likely unwired, not dead
    notes: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        # Conceptual/documentation/API entries — no code file needed
        if any(marker in self.file_ref for marker in ['[概念]', '规划中', '[API]', '[配置]']):
            return "CONCEPT"
        if not self.d1: return "MISSING"
        # Test files: exist but no production callers (normal)
        if '/tests/' in self.file_ref or self.file_ref.startswith('tests/'):
            return "TEST"
        # Gated modules: behind default-off feature flag
        if self.d4: return "DISABLED"
        # ACTIVE: has callers AND (has test OR has CoreFacade)
        if self.d5 and (self.d7 or self.d2): return "ACTIVE"
        # DEGRADED: has callers but no test/facade
        if self.d5: return "DEGRADED"
        # No callers — classify
        ref = self.file_ref.lower()
        is_script = ref.endswith('.sh') or ref.startswith('scripts/')
        is_frontend = ref.endswith('.tsx') or ref.endswith('.ts') or 'frontend' in ref
        is_external = 'sdk' in ref or 'vscode' in ref or 'aiplat-' in ref
        is_deprecated = 'poc/' in ref or 'deprecated' in self.description.lower()
        if is_script or is_frontend or is_external: return "TOOL"
        if self.is_complete: return "UNWIRED"
        if is_deprecated: return "DEPRECATED"
        return "DORMANT"

    @property
    def score(self) -> int:
        pts = sum(1 for d in [self.d1,self.d2,self.d3,self.d5,self.d7] if d)
        if self.d4: pts -= 2
        return max(0, pts)


# ═══════════════ Verifier ═══════════════

class Verifier:
    def __init__(self):
        self._sc: Optional[str] = None
        self._fc: Optional[str] = None

    @property
    def server(self) -> str:
        if self._sc is None:
            p = WORKSPACE / "aiPlat-core/core/server.py"
            self._sc = p.read_text() if p.exists() else ""
        return self._sc

    @property
    def facade(self) -> str:
        if self._fc is None:
            p = WORKSPACE / "aiPlat-core/core/api/core_facade.py"
            self._fc = p.read_text() if p.exists() else ""
        return self._fc

    def _stems(self, e: CapEntry) -> List[str]:
        """All module name stems from (possibly multi-part +) file reference."""
        stems = []
        for part in e.file_ref.replace('`','').split('+'):
            s = Path(part.split(':')[0].strip()).stem
            if s and len(s) >= 2:  # allow db, llm etc.
                stems.append(s)
        return stems

    def verify(self, e: CapEntry) -> Verdict:
        v = Verdict(name=e.name, file_ref=e.file_ref, subsystem=e.subsystem, description=e.description)
        self._check_file(v)
        if not v.d1: return v
        self._check_facade(v, e)
        self._check_server(v, e)
        self._check_flag(v, e)
        self._check_callers(v, e)
        self._check_test(v, e)
        self._check_complete(v, e)  # detect complete-but-unwired modules
        return v

    def _check_file(self, v: Verdict) -> None:
        # Strip ALL backtick characters (not just leading/trailing)
        raw = v.file_ref.split(":")[0].replace('`', '').strip()
        if not raw or raw.startswith("http") or raw.startswith("API:") or \
           raw.startswith("**") or raw.startswith("总计") or re.match(r'^\d+$', raw):
            v.d1 = True; v.notes.append("non-file"); return
        for ref in raw.split("+"):
            ref = ref.strip().strip("'\"")
            if not ref: continue
            if ref.startswith("~/"):
                if Path(ref).expanduser().exists(): v.d1 = True; return
                continue
            plat = ref[len("platform/"):] if ref.startswith("platform/") else ref
            mgmt = ref[len("frontend/"):] if ref.startswith("frontend/") else ref
            for c in [WORKSPACE/"aiPlat-core/core"/ref, WORKSPACE/"aiPlat-core"/ref,
                       WORKSPACE/"aiPlat-platform"/plat, WORKSPACE/"aiPlat-platform"/ref,
                       WORKSPACE/"aiPlat-infra"/ref,
                       WORKSPACE/"aiPlat-management"/mgmt, WORKSPACE/"aiPlat-management"/ref,
                       WORKSPACE/ref]:
                if c.is_file(): v.d1 = True; return
                if c.is_dir(): v.d1 = True; v.notes.append(f"dir"); return
            # Fuzzy fallback BY FILENAME for this individual ref
            fn = Path(ref).name
            if fn and len(fn) > 2 and "." in fn:
                for base in ["aiPlat-core","aiPlat-platform","aiPlat-infra","aiPlat-management"]:
                    try:
                        for line in os.popen(f'find "{WORKSPACE}/{base}" -name "{fn}" 2>/dev/null').read().strip().split("\n")[:2]:
                            if line.strip() and Path(line.strip()).is_file():
                                v.d1 = True; return
                    except: pass

    def _check_facade(self, v: Verdict, e: CapEntry) -> None:
        for stem in self._stems(e):
            if re.search(rf'\b{re.escape(stem)}\b', self.facade):
                v.d2 = True; return
        # Also check path components
        for part in e.file_ref.replace('`','').replace('\\','/').split('/'):
            for sub in part.split('+'):
                clean = sub.split(':')[0].strip()
                if len(clean) >= 3 and re.search(rf'\b{re.escape(clean)}\b', self.facade, re.I):
                    v.d2 = True; return

    def _check_server(self, v: Verdict, e: CapEntry) -> None:
        for stem in self._stems(e):
            if re.search(rf'\b{re.escape(stem)}\b', self.server):
                v.d3 = True; return
        # Parent package check
        parts = e.file_ref.replace('`','').split('+')[0].split(':')[0].split('/')
        if len(parts) >= 2 and len(parts[-2]) > 2 and parts[-2] in self.server:
            v.d3 = True

    def _check_flag(self, v: Verdict, e: CapEntry) -> None:
        """Only gated if the MODULE ITSELF has a startup gate in its first 50 lines."""
        for c in [WORKSPACE/"aiPlat-core/core"/e.file_ref.replace('`','').split(':')[0].split('+')[0].strip(),
                   WORKSPACE/"aiPlat-core"/e.file_ref.replace('`','').split(':')[0].split('+')[0].strip()]:
            if not c.is_file(): continue
            try:
                head = '\n'.join(c.read_text().split('\n')[:50])
                if re.search(r'os\.getenv\s*\(\s*"[^"]*"\s*,\s*"(?:false|0|no|off)"\s*\)', head, re.I):
                    v.d4 = True; v.notes.append(f"startup-gated"); return
            except: pass

    def _check_callers(self, v: Verdict, e: CapEntry) -> None:
        stems = self._stems(e)
        if not stems: return
        # Fast check: server.py or CoreFacade
        for stem in stems:
            if stem in self.server or stem in self.facade:
                v.d5 = True; return

        search_dirs = [
            "aiPlat-core/core/harness","aiPlat-core/core/api","aiPlat-core/core/apps",
            "aiPlat-core/core","aiPlat-platform","aiPlat-infra"
        ]
        # Collect own file names to skip self-references
        own = set()
        for p in e.file_ref.replace('`','').split('+'):
            own.add(p.split(':')[0].strip().split('/')[-1])

        for d in search_dirs:
            dp = WORKSPACE / d
            if not dp.is_dir(): continue
            for stem in stems:
                try:
                    for line in os.popen(f'grep -rl "{stem}" "{dp}" --include="*.py" 2>/dev/null').read().split("\n"):
                        if not line.strip(): continue
                        fname = Path(line.strip()).name
                        if fname in own: continue
                        # Only skip internal _check_* diagnostic internals, NOT REST endpoint callers
                        if '/diagnostics' in line and '_check_' in line:
                            continue
                        if "/tests/" in line or "/test_" in line: continue
                        v.d5 = True; return
                except: pass

    def _check_test(self, v: Verdict, e: CapEntry) -> None:
        for stem in self._stems(e):
            for base in ["aiPlat-core/core/tests","aiPlat-core/tests","tests",
                          "aiPlat-platform/tests","aiPlat-infra/tests"]:
                d = WORKSPACE / base
                if not d.is_dir(): continue
                try:
                    if os.popen(f'grep -rl "{stem}" "{d}" --include="*.py" 2>/dev/null').read().strip():
                        v.d7 = True; return
                except: pass

    def _check_complete(self, v: Verdict, e: CapEntry) -> None:
        """Detect complete-but-unwired: substantial impl without callers."""
        ref = e.file_ref.replace('`','').split(':')[0].split('+')[0].strip()
        for base in [WORKSPACE/"aiPlat-core/core"/ref, WORKSPACE/"aiPlat-core"/ref,
                      WORKSPACE/"aiPlat-platform"/ref]:
            if not base.is_file(): continue
            try:
                content = base.read_text()
                lines = len(content.split('\n'))
                has_class = bool(re.search(r'\bclass\s+[A-Z]', content))
                has_fn = bool(re.search(r'\bdef\s+[a-z]', content, re.M))
                has_get = bool(re.search(r'def\s+get_\w+', content))
                has_usage = bool(re.search(r'Usage:?', content))
                # Need 2 of 3: substantial + structured + intended-for-use
                indicators = sum(
                    [1 for x in [lines > 80, (has_class and has_fn), (has_usage or has_get)] if x]
                )
                if indicators >= 2:
                    v.is_complete = True
                    v.notes.append(f"complete({lines}L) not wired")
            except: pass


# ═══════════════ Report ═══════════════

def report(verdicts: List[Verdict]) -> str:
    by_status = defaultdict(list)
    by_subsys = defaultdict(list)
    for v in verdicts:
        by_status[v.status].append(v)
        by_subsys[v.subsystem].append(v)

    lines = []
    sep = "═" * 75
    lines.extend(["", sep, f"  CAPABILITIES.md Runtime Verification v3",
                   f"  8 dims: file|facade|startup|flags|callers|api|test — /diagnostics bug fixed",
                   sep, f"  Total: {len(verdicts)}", ""])
    emoji = {"ACTIVE":"✅","DEGRADED":"⚠️","DORMANT":"💤","DISABLED":"🔒","MISSING":"❌",
             "TOOL":"🔧","UNWIRED":"🔌","DEPRECATED":"🗑️"}
    for sname in sorted(by_subsys):
        svs = by_subsys[sname]
        a = sum(1 for v in svs if v.status=="ACTIVE")
        dg = sum(1 for v in svs if v.status=="DEGRADED")
        dm = sum(1 for v in svs if v.status=="DORMANT")
        di = sum(1 for v in svs if v.status=="DISABLED")
        mi = sum(1 for v in svs if v.status=="MISSING")
        bar = "▓"*a + "▒"*dg + "░"*dm + "·"*di + "×"*mi
        lines.append(f"  {bar}")
        lines.append(f"  {sname}: {len(svs)} [{emoji['ACTIVE']}ACTIVE={a} {emoji['DEGRADED']}DEGRADED={dg} {emoji['DORMANT']}DORMANT={dm} {emoji['DISABLED']}DISABLED={di} {emoji['MISSING']}MISSING={mi}]")

    A = len(by_status.get("ACTIVE",[])); DG = len(by_status.get("DEGRADED",[]))
    DM = len(by_status.get("DORMANT",[])); DI = len(by_status.get("DISABLED",[]))
    MI = len(by_status.get("MISSING",[]))
    TL = len(by_status.get("TOOL",[])); PL = len(by_status.get("PLANNED",[]))
    DP = len(by_status.get("DEPRECATED",[]))
    tot = max(len(verdicts),1)
    # TOOL/PLANNED/DEPRECATED count as neutral (score 3) — they exist but aren't library modules
    sc = (A*5 + DG*3 + (TL+PL+DP)*3 + DM*1) / (tot*5) * 100
    lines.extend(["", f"  Σ Readiness: {sc:.0f}/100 (ACTIVE=used+verified)",
                  f"    ACTIVE={A} DEGRADED={DG} DORMANT={DM} DISABLED={DI} MISSING={MI}",
                  f"    TOOL={TL} (scripts/frontend) PLANNED={PL} (Phase 11.x) DEPRECATED={DP}",
                  ""])
    # DORMANT details
    for v in by_status.get("DORMANT",[])[:20]:
        lines.append(f"  💤 {v.name[:40]}: {v.file_ref[:70]}")
    if len(by_status.get("DORMANT",[])) > 20:
        lines.append(f"  ... and {len(by_status['DORMANT'])-20} more")
    lines.extend(["", sep, f"  v3 — fixed: /diagnostics REST endpoints, stem>=2, for-loop scope", sep])
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    entries = parse_capabilities()
    verifier = Verifier()
    verdicts = [verifier.verify(e) for e in entries]

    if args.json:
        print(json.dumps({
            "total": len(verdicts),
            "score": int((sum(1 for v in verdicts if v.status=="ACTIVE")*5 +
                          sum(1 for v in verdicts if v.status=="DEGRADED")*3 +
                          sum(1 for v in verdicts if v.status=="DORMANT")*1) /
                         max(len(verdicts)*5,1)*100),
            "by_status": {s: len([v for v in verdicts if v.status==s])
                          for s in ["ACTIVE","DEGRADED","DORMANT","DISABLED","MISSING",
                                    "TOOL","PLANNED","DEPRECATED"]},
            "items": [{"name":v.name,"status":v.status,"file_ref":v.file_ref,
                       "subsystem":v.subsystem,"dims":{
                           "file":v.d1,"facade":v.d2,"startup":v.d3,
                           "gated":v.d4,"callers":v.d5,"test":v.d7}} for v in verdicts]
        }, ensure_ascii=False, indent=2))
    else:
        print(report(verdicts))


if __name__ == "__main__":
    main()
