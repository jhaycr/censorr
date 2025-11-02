#!/usr/bin/env bash
# Simple local diff size check against main (or provided base)
# Usage: scripts/check-pr-size.sh [base_branch]
set -euo pipefail
BASE=${1:-main}

if ! git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  echo "Base branch '$BASE' not found locally. Fetching..." >&2
  git fetch origin "$BASE":"$BASE" || true
fi

# Count additions/deletions excluding vendor/third_party and lockfiles
TMP=$(mktemp)
git diff --numstat "$BASE"...HEAD | grep -Ev '^(|\t)(vendor/|third_party/|.*lock.*)$' > "$TMP" || true

adds=$(awk '{s+=$1} END {print s+0}' "$TMP")
dels=$(awk '{s+=$2} END {print s+0}' "$TMP")
files=$(wc -l < "$TMP" | awk '{print $1+0}')
rm -f "$TMP"

cap_files=10
cap_adds=400
cap_dels=400

echo "Files: $files (cap $cap_files)"
echo "Additions: +$adds (cap +$cap_adds)"
echo "Deletions: -$dels (cap -$cap_dels)"

status=0
if (( files > cap_files )); then
  echo "ERROR: Too many files changed" >&2
  status=1
fi
if (( adds > cap_adds )); then
  echo "ERROR: Too many additions" >&2
  status=1
fi
if (( dels > cap_dels )); then
  echo "ERROR: Too many deletions" >&2
  status=1
fi

exit $status
