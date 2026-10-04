#!/usr/bin/env bash
# install_hooks.sh -- wire the safety gate into this repository's git hooks.
#
#   bash scripts/install_hooks.sh
#
# Hooks live in .git/hooks and are NOT versioned, so a fresh clone has no gate until
# this is run. That is why scripts/make_review_bundle.py and the push path both call
# scripts/precommit_safety_check.py --mode history independently of the hook.
#
# Refuses to write if .git is missing, and never touches anything outside .git/hooks.
set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
[ -d "$ROOT/.git" ] || { echo "FATAL: $ROOT is not a git repository (run git init first)"; exit 8; }

HOOK="$ROOT/.git/hooks/pre-commit"
cat > "$HOOK" <<'EOF'
#!/bin/sh
# Installed by scripts/install_hooks.sh -- do not edit here, edit the script.
# Blocks any commit whose staged blobs hit a PDK / credential / vendor-model rule.
root=$(git rev-parse --show-toplevel) || exit 1
py=python
command -v "$py" >/dev/null 2>&1 || py=python3
exec "$py" "$root/scripts/precommit_safety_check.py" --mode staged
EOF
chmod +x "$HOOK" 2>/dev/null || true

cat > "$ROOT/.git/hooks/pre-push" <<'EOF'
#!/bin/sh
# Installed by scripts/install_hooks.sh
# Re-checks the FULL history before anything leaves the machine: a secret deleted in a
# later commit is still in history, and history is what gets pushed.
root=$(git rev-parse --show-toplevel) || exit 1
py=python
command -v "$py" >/dev/null 2>&1 || py=python3
exec "$py" "$root/scripts/precommit_safety_check.py" --mode history
EOF
chmod +x "$ROOT/.git/hooks/pre-push" 2>/dev/null || true

echo "HOOKS installed: pre-commit(staged gate) pre-push(history gate)"
printf '%s\n' "  $HOOK" "  $ROOT/.git/hooks/pre-push"
grep -c . "$HOOK" | sed 's/^/  pre-commit lines=/'
