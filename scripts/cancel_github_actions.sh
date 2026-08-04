#!/bin/bash
set -euo pipefail

repo=$(git remote get-url origin | sed 's|.*github.com[:/]||; s|\.git$||')
[ -z "$repo" ] && repo="MicroPythonOS/MicroPythonOS"

runs=$(gh run list -R "$repo" --json databaseId,status,workflowName --limit 100)
in_progress=$(echo "$runs" | python3 -c "
import json,sys
all_runs = json.load(sys.stdin)
in_prog = [r for r in all_runs if r['status'] == 'in_progress']
print(json.dumps(in_prog))
")

count=$(echo "$in_progress" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")

if [ "$count" -eq 0 ]; then
    echo "No in-progress runs."
    exit 0
fi

echo "Cancelling $count in-progress run(s):"
echo "$in_progress" | python3 -c "
import json,sys
for r in json.load(sys.stdin):
    print(f'  {r[\"databaseId\"]}  {r[\"status\"]}  {r[\"workflowName\"]}')
"

ids=$(echo "$in_progress" | python3 -c "import json,sys; print('\n'.join(str(r['databaseId']) for r in json.load(sys.stdin)))")
for id in $ids; do
    gh run cancel -R "$repo" "$id"
done

echo "Done."
