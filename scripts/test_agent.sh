#!/usr/bin/env bash
# test_agent.sh <agent_name>
# Runs the six automated test checks for one VIKAS agent and writes a report.
#
# Usage:
#   ./scripts/test_agent.sh brand_voice_keeper
#   ./scripts/test_agent.sh keyword_research
#
# Prerequisites:
#   - Docker stack running (docker compose up -d)
#   - DEV_AUTH_BYPASS=true in .env for Layer B API tests
#   - uv venv active (or use: uv run ./scripts/test_agent.sh ...)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_NAME="${1:-}"

if [[ -z "$AGENT_NAME" ]]; then
    echo "Usage: $0 <agent_name>"
    echo ""
    echo "Available agents:"
    ls "$REPO_ROOT/tests/agent_configs/" 2>/dev/null | sed 's/\.yaml$/  /' | column
    exit 1
fi

CONFIG_FILE="$REPO_ROOT/tests/agent_configs/${AGENT_NAME}.yaml"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: No config found at $CONFIG_FILE"
    echo "Run: ls tests/agent_configs/ to see available agents"
    exit 1
fi

echo ""
echo "============================================================"
echo "  VIKAS Agent Test Harness"
echo "  Agent : $AGENT_NAME"
echo "  Config: tests/agent_configs/${AGENT_NAME}.yaml"
echo "============================================================"
echo ""

exec python3 "$SCRIPT_DIR/_test_agent_runner.py" "$AGENT_NAME"
