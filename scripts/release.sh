#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/release.sh <version> [--no-tag] [--no-push] [--no-deploy]

Creates a patch/minor release by keeping backend, frontend, git tag,
Docker build metadata, and /api/health aligned.

Examples:
  scripts/release.sh 0.2.2
  scripts/release.sh 0.3.0 --no-push
EOF
}

VERSION=""
NO_TAG=0
NO_PUSH=0
NO_DEPLOY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --no-tag)
      NO_TAG=1
      ;;
    --no-push)
      NO_PUSH=1
      ;;
    --no-deploy)
      NO_DEPLOY=1
      ;;
    *)
      if [[ -z "$VERSION" ]]; then
        VERSION="$1"
      else
        echo "Unexpected argument: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
  shift
done

if [[ -z "$VERSION" ]]; then
  usage >&2
  exit 2
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must look like 0.2.2, got: $VERSION" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit or stash changes first." >&2
  git status --short >&2
  exit 1
fi

TAG="v$VERSION"
if [[ "$NO_TAG" -eq 0 ]] && git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "Tag already exists: $TAG" >&2
  exit 1
fi

python3 - "$VERSION" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

version = sys.argv[1]
root = Path.cwd()

(root / "app" / "version.py").write_text(f'VERSION = "{version}"\n', encoding="utf-8")

app_vue = root / "frontend" / "src" / "App.vue"
text = app_vue.read_text(encoding="utf-8")
import re
text = re.sub(r"const appVersion = ref\('[^']+'\)", f"const appVersion = ref('{version}')", text)
app_vue.write_text(text, encoding="utf-8")

subprocess.run(
    ["npm", "version", version, "--no-git-tag-version", "--allow-same-version", "--prefix", "frontend"],
    check=True,
)
PY

python3 -m compileall app
npm run build --prefix frontend

git add app/version.py frontend/package.json frontend/package-lock.json frontend/src/App.vue
if ! git diff --cached --quiet; then
  git commit -m "chore: release $TAG"
else
  echo "No version file changes to commit."
fi

if [[ "$NO_TAG" -eq 0 ]]; then
  git tag "$TAG"
fi

if [[ "$NO_DEPLOY" -eq 0 ]]; then
  COMMIT="$(git rev-parse --short=12 HEAD)"
  GIT_COMMIT="$COMMIT" docker compose up -d --build
  echo "Waiting for health endpoint..."
  for _ in {1..20}; do
    if HEALTH="$(curl -fsS http://localhost:8500/api/health 2>/dev/null)"; then
      echo "$HEALTH"
      python3 - "$HEALTH" "$VERSION" "$COMMIT" <<'PY'
import json
import sys
health = json.loads(sys.argv[1])
version = sys.argv[2]
commit = sys.argv[3]
if health.get("version") != version:
    raise SystemExit(f"Health version mismatch: {health.get('version')} != {version}")
if health.get("commit") != commit:
    raise SystemExit(f"Health commit mismatch: {health.get('commit')} != {commit}")
PY
      break
    fi
    sleep 1
  done
fi

if [[ "$NO_PUSH" -eq 0 ]]; then
  git push origin main
  if [[ "$NO_TAG" -eq 0 ]]; then
    git push origin "$TAG"
  fi
fi

echo "Release complete: $TAG"
