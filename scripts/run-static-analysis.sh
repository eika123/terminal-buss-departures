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

# Output directory for analysis artifacts
OUT_DIR="static-analysis"
mkdir -p "${OUT_DIR}"

GEN_DOC=false

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --doc)
            GEN_DOC=true
            ;;
        -h|--help)
            echo "Usage: $0 [--doc]"
            echo "  --doc    Generate visual dependency graphs (SVG/JSON via pydeps)"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--doc]"
            exit 1
            ;;
    esac
done

echo "==> Running static analysis..."

# 1. Pyflakes analysis
echo "--> Checking Python code with pyflakes..."
uv run pyflakes *.py adapters tests
echo "    pyflakes: clean (0 issues)"

# 2. Ruff analysis
echo "--> Checking with ruff..."
uv run ruff check .

# 3. Pyright static type checker
echo "--> Checking static types with pyright..."
uv run pyright
echo "    pyright: 0 errors"

# 4. Bandit security analysis
echo "--> Checking code security with bandit..."
uv run bandit -r *.py adapters -s B404 --quiet
echo "    bandit: clean? ...(0 security issues detected in scan)"

# 4. Check for circular dependencies (always fast & non-visual)
echo "--> Checking for circular dependencies..."
uv run pydeps avgangstider.py --show-cycles --no-output 2>&1 || true

# 5. Optional documentation & dependency graphs
if [ "$GEN_DOC" = true ]; then
    echo "--> Generating visual dependency graph (${OUT_DIR}/dependencies.svg)..."
    uv run pydeps avgangstider.py \
        --cluster \
        -o "${OUT_DIR}/dependencies.svg" \
        --noshow

    echo "--> Generating dependency structure data (${OUT_DIR}/dependencies.json)..."
    uv run pydeps avgangstider.py \
        --show-deps \
        --no-output > "${OUT_DIR}/dependencies.json"

    echo "==> Documentation artifacts saved to ${OUT_DIR}/"
fi

echo "==> Static analysis completed successfully!"

