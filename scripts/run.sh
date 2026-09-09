#!/usr/bin/env bash
# learn-project 一键执行：分析 + 启动 WebUI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
WORKSPACE="${LEARN_PROJECT_WORKSPACE:-$REPO_ROOT/learnProject}"
PORT="${LEARN_PROJECT_PORT:-9876}"

echo "==> Workspace: $WORKSPACE"
echo "==> Analyzing project..."
python "$SCRIPT_DIR/analyze.py" --workspace "$WORKSPACE"

echo ""
echo "==> Starting WebUI on http://127.0.0.1:${PORT}"
echo "    Press Ctrl+C to stop"
cd "$WORKSPACE"
exec python server.py "$PORT"
