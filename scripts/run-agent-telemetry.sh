#!/bin/bash
set -e

# Opprett .agents-mappen hvis den ikke finnes fra før
mkdir -p .agents

echo "🚀 Starting an extended telemetry-collection for the antigravity-agent..."

# 1. Kjøre Radon for å finne komplekse funksjoner (Score C eller dårligere)
echo "📊 Analysing cognitive complexity with Radon..."
uvx radon cc . -n C -j > .agents/radon_complexity.json || true

# 2. Kjøre Semgrep for å finne ueffektive mønstre og arkitekturfeil
echo "🔍 Checking code patterns with Semgrep OSS..."
uvx semgrep --config=auto --json -o .agents/semgrep_findings.json . || true

# 3. Kjøre Sourcery CLI og lagre som CSV
echo "🔮 Generating concrete refactoring suggestions with Sourcery..."
uvx sourcery review --csv . > .agents/sourcery_suggestions.csv || true

# 4. Kjøre tester med dekning og lagre som JSON
echo "🧪 Measuring test coverage with pytest-cov..."
uv run pytest --cov=. --cov-report=json:.agents/coverage.json --cov-report=term-missing || true


# ======================================================================
# 5. Generer den endelige samle-prompten / oppgavebeskrivelsen til agenten
# ======================================================================
echo "📝 Putting together ai_refactor_prompt.txt..."

cat << 'EOF' > .agents/ai_refactor_prompt.txt
======================================================================
CONTEXT FOR REFACTORING AGENT
======================================================================
You are a specialized AI-agent integrated via antigravity for code refactoring.
Your task is to analyze the following telemetry data from Radon, Semgrep and Sourcery,
make a secure refactoring plan, and improvde the code accordingly.

Prioritize your tasks as stated below:
1. SOURCERY SUGGESTIONS (CSV): Implement the concret suggestions for simplification of loops,
unnesting if-statements and removal of dead code.
2. RADON COMPLEXITY (JSON): Split functions and methods that have reached a high complexity score
of C or worse.
3. SEMGREP FINDINGS (JSON): Correct reported code smells or bad patterns.
4. TEST COVERAGE (JSON): Increase test coverage of modules that lack coverage if your are in
test_architect mode.

----------------------------------------------------------------------
TELEMETRY DATA 1: RADON COMPLEXITY (JSON)
----------------------------------------------------------------------
EOF

cat .agents/radon_complexity.json >> .agents/ai_refactor_prompt.txt

cat << 'EOF' >> .agents/ai_refactor_prompt.txt

----------------------------------------------------------------------
TELEMETRI DATA 2: SEMGREP FINDINGS (JSON)
----------------------------------------------------------------------
EOF

cat .agents/semgrep_findings.json >> .agents/ai_refactor_prompt.txt

cat << 'EOF' >> .agents/ai_refactor_prompt.txt

----------------------------------------------------------------------
TELEMETRY DATA 3: SOURCERY REFACTORING SUGGESTIONS (CSV)
----------------------------------------------------------------------
EOF

cat .agents/sourcery_suggestions.csv >> .agents/ai_refactor_prompt.txt

cat << 'EOF' >> .agents/ai_refactor_prompt.txt

----------------------------------------------------------------------
TELEMETRY DATA 4: TEST COVERAGE REPORT (JSON SUMMARY)
----------------------------------------------------------------------
EOF

# Exact summary to compress prompt
if [ -f .agents/coverage.json ]; then
    python3 -c "import json; d=json.load(open('.agents/coverage.json')); print(json.dumps(d.get('totals', {}), indent=2))" >> .agents/ai_refactor_prompt.txt
else
    echo "{\"error\": \"Coverage report missing\"}" >> .agents/ai_refactor_prompt.txt
fi

cat << 'EOF' >> .agents/ai_refactor_prompt.txt


======================================================================
END OF TELEMETRY. PLEASE GENERATE REFACTORING PLAN AND MAKE CHANGES
======================================================================
EOF

echo "✅ All telemetry gathered in .agents/!"
echo "👉 Main promt prepared in: .agents/ai_refactor_prompt.txt"
