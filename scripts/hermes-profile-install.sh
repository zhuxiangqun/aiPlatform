#!/usr/bin/env bash
# aiPlat profile install script — one-click install from distribution.yaml or Git repo.
# Usage: bash hermes-profile-install.sh <distribution.yaml | git-url>
# H-axis L3→L4 enabler.

set -euo pipefail

SOURCE="${1:-}"
AIPLAT_HOME="${AIPLAT_HOME:-$HOME/.aiplat}"

if [ -z "$SOURCE" ]; then
    echo "Usage: bash hermes-profile-install.sh <distribution.yaml | git-url>"
    echo ""
    echo "Examples:"
    echo "  bash hermes-profile-install.sh ./distribution.yaml"
    echo "  bash hermes-profile-install.sh https://github.com/org/aiplat-profile.git"
    exit 1
fi

echo "=== aiPlat Profile Installer ==="
echo "  Source: $SOURCE"
echo "  Target: $AIPLAT_HOME"
echo ""

# Determine source type
if [[ "$SOURCE" == http*://*git* || "$SOURCE" == git@* ]]; then
    IS_GIT_REPO=1
else
    IS_GIT_REPO=0
fi

if [ "$IS_GIT_REPO" -eq 1 ]; then
    echo "[*] Cloning from Git repository..."
    CLONE_DIR="$(mktemp -d)/aiplat-profile"
    git clone "$SOURCE" "$CLONE_DIR"
    MANIFEST="$CLONE_DIR/distribution.yaml"
    if [ ! -f "$MANIFEST" ]; then
        echo "[!] Error: distribution.yaml not found in repository root."
        rm -rf "$(dirname "$CLONE_DIR")"
        exit 1
    fi
    PROFILE_NAME=$(grep '^name:' "$MANIFEST" | head -1 | awk '{print $2}')
    echo "  Profile: ${PROFILE_NAME:-unknown}"
else
    MANIFEST="$SOURCE"
    if [ ! -f "$MANIFEST" ]; then
        echo "[!] Error: $MANIFEST not found."
        exit 1
    fi
    PROFILE_NAME=$(grep '^name:' "$MANIFEST" | head -1 | awk '{print $2}')
fi

echo ""
echo "[*] Installing profile '$PROFILE_NAME'..."

# Install using Python to parse YAML
python3 - "$MANIFEST" "$AIPLAT_HOME" "$CLONE_DIR" << 'PYEOF'
import sys, os, json, shutil
manifest_path = sys.argv[1]
target_dir = os.path.expanduser(sys.argv[2])
clone_dir = sys.argv[3] if len(sys.argv) > 3 else ""

try:
    import yaml
    with open(manifest_path) as f:
        dist = yaml.safe_load(f)
except ImportError:
    import json
    with open(manifest_path) as f:
        content = f.read()
        if content.startswith("#"):
            content = content.split("\n", 1)[1] if "\n" in content else content
        dist = json.loads(content)

profile = dist.get("name", "default")
os.makedirs(target_dir, exist_ok=True)

# Install agents
if dist.get("agents"):
    agents_dir = os.path.join(target_dir, "agents")
    for agent in dist["agents"]:
        adir = os.path.join(agents_dir, agent["name"])
        os.makedirs(adir, exist_ok=True)
        with open(os.path.join(adir, "AGENT.md"), "w") as f:
            f.write(agent.get("config", ""))
    print(f"  Agents: {len(dist['agents'])} installed")

# Install skills
if dist.get("skills"):
    skills_dir = os.path.join(target_dir, "skills")
    for skill in dist["skills"]:
        sdir = os.path.join(skills_dir, skill["name"])
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "SKILL.md"), "w") as f:
            f.write(skill.get("config", ""))
    print(f"  Skills: {len(dist['skills'])} installed")

# Install MCP config
if dist.get("mcp"):
    with open(os.path.join(target_dir, "mcp.json"), "w") as f:
        json.dump(dist["mcp"], f, indent=2)
    print("  MCP config: installed")

# Copy extra files from clone
if clone_dir and os.path.isdir(clone_dir):
    for item in os.listdir(clone_dir):
        src = os.path.join(clone_dir, item)
        dst = os.path.join(target_dir, item)
        if os.path.isfile(src) and not item.endswith(".yaml"):
            shutil.copy2(src, dst)

print(f"\n✅ Profile '{profile}' installed to {target_dir}")
print("   Restart aiPlat to load new configuration.")
PYEOF

EXIT_CODE=$?
if [ "$IS_GIT_REPO" -eq 1 ] && [ -d "$CLONE_DIR" ]; then
    rm -rf "$(dirname "$CLONE_DIR")"
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "[*] Installation complete. Profile '$PROFILE_NAME' is ready."
    echo "    Restart your aiPlat services to apply changes."
else
    echo "[!] Installation failed."
    exit $EXIT_CODE
fi
