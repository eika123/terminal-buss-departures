#!/bin/bash
set -e

# Opprett .agents-mappen hvis den ikke finnes fra før
mkdir -p .agents

echo "🚀 Starter utvidet telemetri-innsamling for antigravity-agent..."

# 1. Kjøre Radon for å finne komplekse funksjoner (Score C eller dårligere)
echo "📊 Analyserer kognitiv kompleksitet med Radon..."
uvx radon cc . -n C -j > .agents/radon_complexity.json || true

# 2. Kjøre Semgrep for å finne ueffektive mønstre og arkitekturfeil
echo "🔍 Sjekker kodemønstre med Semgrep OSS..."
uvx semgrep --config=auto --json -o .agents/semgrep_findings.json . || true

# 3. Kjøre Sourcery CLI og lagre som CSV
echo "🔮 Genererer konkrete refaktoreringsforslag med Sourcery..."
uvx sourcery review --csv . > .agents/sourcery_suggestions.csv || true

# 4. Kjøre tester med dekning og lagre som JSON
echo "🧪 Måler testdekning med pytest-cov..."
uv run pytest --cov=. --cov-report=json:.agents/coverage.json --cov-report=term-missing || true


# ======================================================================
# 5. Generer den endelige samle-prompten / oppgavebeskrivelsen til agenten
# ======================================================================
echo "📝 Setter sammen ai_refactor_prompt.txt..."

cat << 'EOF' > .agents/ai_refactor_prompt.txt
======================================================================
CONTEXT FOR REFACTORING AGENT
======================================================================
Du er en spesialisert AI-agent integrert via antigravity for kode-refaktorering. 
Din oppgave er å analysere de medfølgende telemetridataene fra Radon, Semgrep 
og Sourcery, lage en sikker refaktoreringsplan, og utbedre koden.

Prioriter oppgavene slik:
1. SOURCERY SUGGESTIONS (CSV): Implementer de konkrete forslagene til forenkling 
   av løkker, sammenslåing av if-setninger og fjerning av død kode.
2. RADON COMPLEXITY (JSON): Splitt opp funksjoner/metoder som har fått en høy 
   kompleksitetscore (Score C eller dårligere).
3. SEMGREP FINDINGS (JSON): Rett opp eventuelle code smells eller dårlige mønstre.
4. TEST COVERAGE (JSON): Øk testdekningen på moduler som mangler dekning dersom du er i test_architect modus.

----------------------------------------------------------------------
TELEMETRI DATA 1: RADON COMPLEXITY (JSON)
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
TELEMETRI DATA 3: SOURCERY REFACTORING SUGGESTIONS (CSV)
----------------------------------------------------------------------
EOF

cat .agents/sourcery_suggestions.csv >> .agents/ai_refactor_prompt.txt

cat << 'EOF' >> .agents/ai_refactor_prompt.txt

----------------------------------------------------------------------
TELEMETRI DATA 4: TEST COVERAGE REPORT (JSON SUMMARY)
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
SLUTT PÅ TELEMETRI. VENNLIGST GENERER REFAKTORERINGSPLAN OG UTFØR ENDRINGER.
======================================================================
EOF

echo "✅ All telemetri samlet i .agents/!"
echo "👉 Hovedprompt klargjort i: .agents/ai_refactor_prompt.txt"
