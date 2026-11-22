#!/bin/bash
# Pull bug reports from the project server and list the new ones.
#   tools/reports.sh          new reports since the last run
#   tools/reports.sh all      every report
# Reports land in build/reports/<time>-<id>/ (report.json, strip.jpg, frame.jpg) – private, never commit them.
cd "$(dirname "$0")/.." || exit 1
D=build/reports; mkdir -p "$D"
rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=10" root@156.67.29.119:/var/lib/subbridge-reports/ "$D/" || exit 1
seen=$D/.seen; touch "$seen"
total=$(wc -l < "$D/index.jsonl" 2>/dev/null || echo 0)
from=$([ "$1" = all ] && echo 0 || cat "$seen" 2>/dev/null || echo 0)
[ -z "$from" ] && from=0
echo "reports: $total total, $((total - from)) new"
tail -n +$((from + 1)) "$D/index.jsonl" 2>/dev/null | python3 -c '
import json, sys
for l in sys.stdin:
    d = json.loads(l)
    print(f"{d[\"t\"]}  {d[\"id\"]}  v{d[\"app\"]}  {d.get(\"health\")}  {d[\"os\"][:28]:28}  {d[\"note\"][:90]}")'
echo "$total" > "$seen"
