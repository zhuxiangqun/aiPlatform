#!/usr/bin/env bash
# tag-release.sh — create a semver tag and push
# Usage: bash scripts/tag-release.sh [minor|patch]
set -euo pipefail

TYPE="${1:-patch}"
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
VER="${LATEST_TAG#v}"

IFS='.' read -r MAJOR MINOR PATCH <<< "$VER"
case "$TYPE" in
    major) MAJOR=$((MAJOR+1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR+1)); PATCH=0 ;;
    patch) PATCH=$((PATCH+1)) ;;
esac

NEW_TAG="v${MAJOR}.${MINOR}.${PATCH}"
echo "Tagging: $LATEST_TAG → $NEW_TAG"

git tag -a "$NEW_TAG" -m "Release $NEW_TAG"
git push origin "$NEW_TAG"
echo "✅ Released $NEW_TAG"
