#!/bin/sh
# Run once after cloning: sh scripts/install_hooks.sh
set -e
ROOT="$(git rev-parse --show-toplevel)"
cp "$ROOT/scripts/pre-push.hook" "$ROOT/.git/hooks/pre-push"
chmod +x "$ROOT/.git/hooks/pre-push"
echo "✓ pre-push hook installed"
