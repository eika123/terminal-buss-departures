#!/usr/bin/env bash
set -euo pipefail

# Ensure ~/.local/bin and ~/.cargo/bin are in PATH if uv is located there
if ! command -v uv &> /dev/null; then
    for cand in "${HOME}/.local/bin" "${HOME}/.cargo/bin"; do
        if [ -x "${cand}/uv" ]; then
            if [[ ":$PATH:" != *":$cand:"* ]]; then
                export PATH="${cand}:${PATH}"
            fi
            break
        fi
    done
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

RECORD_FLAG=""
DOC_FLAG=""

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --record|--record-all)
            RECORD_FLAG="--record-mode=all"
            ;;
        --record-new)
            RECORD_FLAG="--record-mode=new_episodes"
            ;;
        --doc)
            DOC_FLAG="--doc"
            ;;
        -h|--help)
            echo "Usage: $0 [--record|--record-all] [--record-new] [--doc]"
            echo "  --record      Refresh and re-record all API cassettes against live endpoints"
            echo "  --record-new  Record cassettes for new contract tests only"
            echo "  --doc         Generate static analysis dependency graph"
            exit 0
            ;;
    esac
done

echo "=================================================="
echo "Step 1/2: Running Static Analysis"
echo "=================================================="
if [ -n "${DOC_FLAG}" ]; then
    "${SCRIPT_DIR}/run-static-analysis.sh" "${DOC_FLAG}"
else
    "${SCRIPT_DIR}/run-static-analysis.sh"
fi

echo ""
echo "=================================================="
echo "Step 2/2: Running Tests (Unit & API Contract)"
echo "=================================================="
if [ -n "${RECORD_FLAG}" ]; then
    echo "--> Running with VCR recording mode: ${RECORD_FLAG}"
    uv run pytest -v ${RECORD_FLAG}
else
    # In standard runs, replay cassettes without hitting the live network
    uv run pytest -v
fi

echo ""
echo "All static analysis checks, unit tests, and API contract tests passed successfully!"
