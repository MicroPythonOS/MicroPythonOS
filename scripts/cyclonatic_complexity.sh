#!/usr/bin/env bash
# Cyclomatic complexity report for internal_filesystem/ (excludes lvgl, lv_*)
# Usage: ./scripts/cyclonatic_complexity.sh [--min N] [--json]

set -euo pipefail
cd "$(dirname "$0")/.."

MIN=${2:-4}
JSON_MODE=0
if [[ "${1:-}" == "--json" ]]; then
    JSON_MODE=1
    MIN=${2:-1}
fi

if [ "$JSON_MODE" -eq 1 ]; then
    python3 -c "
import ast, json, mccabe, sys
from pathlib import Path

results = []
for f in Path('internal_filesystem').rglob('*.py'):
    parts = f.parts
    if any(p.startswith('lv') for p in parts): continue
    try:
        tree = ast.parse(f.read_text())
        visitor = mccabe.PathGraphingAstVisitor()
        visitor.preorder(tree, visitor)
        for name, graph in visitor.graphs.items():
            if name.startswith('TryExcept'): continue
            c = graph.complexity()
            if c >= $MIN:
                results.append({'complexity': c, 'function': name, 'file': str(f)})
    except Exception:
        pass
json.dump(sorted(results, key=lambda x: -x['complexity']), sys.stdout, indent=2)
" 2>/dev/null
else
    python3 -c "
import ast, mccabe, sys
from pathlib import Path

for f in Path('internal_filesystem').rglob('*.py'):
    parts = f.parts
    if any(p.startswith('lv') for p in parts): continue
    try:
        tree = ast.parse(f.read_text())
        visitor = mccabe.PathGraphingAstVisitor()
        visitor.preorder(tree, visitor)
        for name, graph in visitor.graphs.items():
            if name.startswith('TryExcept'): continue
            c = graph.complexity()
            if c >= $MIN:
                print(f'{c:3d}  {name:45s}  {f}')
    except Exception:
        pass
" 2>/dev/null | sort -rn
fi
