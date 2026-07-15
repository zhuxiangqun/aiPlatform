"""Vulnerability SLA Tracker — enforces CVSS-based fix deadlines.
Gap 5.8: transforms SECURITY.md static SLA table into automated enforcement.

Records vulnerability discovery time, calculates fix deadline based on
CVSS severity, and provides CI-integrated breach detection.
"""
import os, sqlite3, threading, time
from datetime import datetime, timezone, timedelta
from typing import Optional

def _load_sla_tiers() -> dict:
    """Load SLA tiers from config/sla_tiers.yaml, fallback to inline defaults."""
    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "sla_tiers.yaml"
    )
    try:
        import yaml as _yaml  # type: ignore
        with open(yaml_path) as f:
            data = _yaml.safe_load(f)
        if isinstance(data, dict):
            return dict(data)
    except Exception:
        pass
    
    # Fallback inline defaults
    return {
        "critical": {"cvss_min": 9.0, "ack_hours": 4, "fix_hours": 24},
        "high":     {"cvss_min": 7.0, "ack_hours": 24, "fix_hours": 168},
        "medium":   {"cvss_min": 4.0, "ack_hours": 48, "fix_hours": 720},
        "low":      {"cvss_min": 0.0, "ack_hours": 168, "fix_hours": 2160},
    }

# SLA tiers from SECURITY.md (config/sla_tiers.yaml)
SLA_TIERS = _load_sla_tiers()


class VulnerabilitySLATracker:
    """Tracks vulnerability discovery → fix timeline with automated breach detection."""

    def __init__(self, db_path: str = "~/.aiplat/security/vuln_sla.db"):
        self.db_path = os.path.expanduser(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS vulnerabilities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cve_id TEXT NOT NULL,
                    cvss REAL NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    discovered_at TEXT NOT NULL,
                    ack_deadline TEXT NOT NULL,
                    fix_deadline TEXT NOT NULL,
                    fixed_at TEXT,
                    status TEXT DEFAULT 'open',
                    source TEXT DEFAULT 'dependabot'
                );
                CREATE TABLE IF NOT EXISTS sla_breaches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vuln_id INTEGER NOT NULL,
                    breach_type TEXT NOT NULL,
                    breached_at TEXT NOT NULL,
                    hours_overdue REAL,
                    FOREIGN KEY(vuln_id) REFERENCES vulnerabilities(id)
                );
                CREATE INDEX IF NOT EXISTS idx_vuln_status ON vulnerabilities(status);
            """)
            conn.commit()
            conn.close()

    def _severity_from_cvss(self, cvss: float) -> str:
        for level, tier in SLA_TIERS.items():
            if cvss >= tier["cvss_min"]:
                return level
        return "low"

    def record(self, cve_id: str, cvss: float, description: str = "",
               source: str = "dependabot") -> int:
        severity = self._severity_from_cvss(cvss)
        tier = SLA_TIERS[severity]
        now = datetime.now(timezone.utc)
        ack_deadline = now + timedelta(hours=tier["ack_hours"])
        fix_deadline = now + timedelta(hours=tier["fix_hours"])

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO vulnerabilities(cve_id, cvss, severity, description, discovered_at, ack_deadline, fix_deadline, source) VALUES(?,?,?,?,?,?,?,?)",
                (cve_id, cvss, severity, description, now.isoformat(), ack_deadline.isoformat(), fix_deadline.isoformat(), source))
            vid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()
            conn.close()
        return vid

    def mark_fixed(self, cve_id: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE vulnerabilities SET fixed_at=?, status='fixed' WHERE cve_id=? AND status='open'",
                        (now, cve_id))
            conn.commit()
            conn.close()

    def check_breaches(self) -> list[dict]:
        """Return all open vulnerabilities past their fix deadline. CI calls this."""
        now = datetime.now(timezone.utc).isoformat()
        breaches = []
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM vulnerabilities WHERE status='open' AND fix_deadline <= ?",
                (now,)).fetchall()

            for row in rows:
                deadline = datetime.fromisoformat(row["fix_deadline"])
                hours_over = (datetime.now(timezone.utc) - deadline).total_seconds() / 3600
                breaches.append({
                    "cve_id": row["cve_id"],
                    "cvss": row["cvss"],
                    "severity": row["severity"],
                    "hours_overdue": round(hours_over, 1),
                    "fix_deadline": row["fix_deadline"],
                    "discovered_at": row["discovered_at"],
                })

                conn.execute(
                    "INSERT INTO sla_breaches(vuln_id, breach_type, breached_at, hours_overdue) VALUES(?,?,?,?)",
                    (row["id"], "fix_deadline", now, round(hours_over, 1)))
            conn.commit()
            conn.close()
        return breaches

    def get_dashboard(self) -> dict:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            total_open = conn.execute("SELECT COUNT(*) as c FROM vulnerabilities WHERE status='open'").fetchone()["c"]
            critical_open = conn.execute("SELECT COUNT(*) as c FROM vulnerabilities WHERE status='open' AND severity='critical'").fetchone()["c"]
            total_fixed = conn.execute("SELECT COUNT(*) as c FROM vulnerabilities WHERE status='fixed'").fetchone()["c"]
            conn.close()

        breaches = len(self.check_breaches())
        return {
            "total_open": total_open,
            "critical_open": critical_open,
            "total_fixed": total_fixed,
            "sla_breaches": breaches,
            "sla_ok": breaches == 0,
        }


def check_and_exit():
    """CI entry point: check SLA breaches and exit 1 if critical breached."""
    tracker = VulnerabilitySLATracker()
    breaches = tracker.check_breaches()
    critical = [b for b in breaches if b["severity"] == "critical"]
    dashboard = tracker.get_dashboard()

    print(f"[SLA Check] Open: {dashboard['total_open']}, "
          f"Fixed: {dashboard['total_fixed']}, "
          f"Breaches: {dashboard['sla_breaches']}, "
          f"Critical breached: {len(critical)}")

    if critical:
        for b in critical:
            print(f"  ❌ {b['cve_id']} (CVSS {b['cvss']}) — {b['hours_overdue']:.0f}h overdue")
        exit(1)

    if breaches:
        print(f"  ⚠️ {len(breaches)} non-critical SLA breaches found (informational)")
    else:
        print("  ✅ All vulnerabilities within SLA")


_sla_tracker: Optional[VulnerabilitySLATracker] = None


def get_sla_tracker() -> VulnerabilitySLATracker:
    global _sla_tracker
    if _sla_tracker is None:
        _sla_tracker = VulnerabilitySLATracker()
    return _sla_tracker
