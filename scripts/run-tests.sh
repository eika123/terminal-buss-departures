#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "=================================================="
echo "Step 1/2: Running Static Analysis"
echo "=================================================="
"${SCRIPT_DIR}/run_static_analysis.sh" "$@"

echo ""
echo "=================================================="
echo "Step 2/2: Running Unit Tests"
echo "=================================================="
uv run pytest -v

echo ""
echo "All static analysis checks and unit tests passed successfully!"

