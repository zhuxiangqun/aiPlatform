#!/usr/bin/env python3
"""Profile Packager — exports current aiPlat config as distribution.yaml.

H-axis L3→L4 enabler: configuration-as-code distribution.
"""
import json, os, sys, yaml, glob
from datetime import datetime, timezone


def get_config_dir() -> str:
    """Get aiPlat config directory."""
    return os.path.expanduser(os.environ.get("AIPLAT_HOME", "~/.aiplat"))


def pack_profile(output_path: str = "distribution.yaml", profile_name: str = "default") -> dict:
    """Export current aiPlat configuration as a distribution manifest."""
    config_dir = get_config_dir()
    dist = {
        "name": profile_name,
        "version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "platform": {
            "python": sys.version.split()[0],
            "os": sys.platform,
        },
        "agents": [],
        "skills": [],
        "mcp": {},
        "cron": [],
        "config": {},
    }

    # Collect agents
    agents_dir = os.path.join(config_dir, "agents")
    if os.path.isdir(agents_dir):
        for d in os.listdir(agents_dir):
            md_path = os.path.join(agents_dir, d, "AGENT.md")
            if os.path.isfile(md_path):
                with open(md_path) as f:
                    dist["agents"].append({
                        "name": d,
                        "config": f.read()[:2000],
                    })

    # Collect skills
    skills_dir = os.path.join(config_dir, "skills")
    if os.path.isdir(skills_dir):
        for d in os.listdir(skills_dir):
            md_path = os.path.join(skills_dir, d, "SKILL.md")
            if os.path.isfile(md_path):
                with open(md_path) as f:
                    dist["skills"].append({
                        "name": d,
                        "config": f.read()[:2000],
                    })

    # Collect MCP config
    mcp_path = os.path.join(config_dir, "mcp.json")
    if os.path.isfile(mcp_path):
        with open(mcp_path) as f:
            dist["mcp"] = json.load(f)

    # Collect cron job entries (H4 — configuration-as-code distribution)
    cron_dir = os.path.join(config_dir, "cron")
    if os.path.isdir(cron_dir):
        for entry in os.listdir(cron_dir):
            ep = os.path.join(cron_dir, entry)
            if ep.endswith(".yaml") or ep.endswith(".json"):
                try:
                    with open(ep) as f:
                        cron_data = yaml.safe_load(f) if ep.endswith(".yaml") else json.load(f)
                    if cron_data and isinstance(cron_data, dict):
                        dist["cron"].append(cron_data)
                except Exception:
                    pass

    # Collect profile list (H4 — .registry.yaml and individual profiles)
    profiles_dir = os.path.join(config_dir, "profiles")
    if os.path.isdir(profiles_dir):
        for entry in sorted(os.listdir(profiles_dir)):
            ep = os.path.join(profiles_dir, entry)
            if ep.endswith(".yaml") and entry != ".registry.yaml":
                try:
                    with open(ep) as f:
                        pdata = yaml.safe_load(f)
                    dist.setdefault("profiles", []).append({"name": entry[:-5], **(pdata if isinstance(pdata, dict) else {})})
                except Exception:
                    pass

    # Try YAML-safe dump
    try:
        import yaml
        with open(output_path, "w") as f:
            yaml.dump(dist, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        with open(output_path, "w") as f:
            f.write("# distribution.yaml — aiPlat Profile Manifest\n")
            f.write(f"# Generated: {dist['generated_at']}\n")
            f.write(json.dumps(dist, indent=2, ensure_ascii=False))

    return dist


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "distribution.yaml"
    profile = sys.argv[2] if len(sys.argv) > 2 else "default"
    pack_profile(out, profile)
    print(f"✅ Profile exported to {out}")
    print(f"   Agents:  {open(out).read().count('name:')} entries")
    print(f"   Install: bash scripts/hermes-profile-install.sh {out}")

