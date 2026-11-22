#!/bin/bash
# Control the auto-update rollout of the current release (feed "latest").
#   tools/rollout.sh status
#   tools/rollout.sh pause            stop handing out the update (installs that have it keep it)
#   tools/rollout.sh resume
#   tools/rollout.sh full             everyone now
#   tools/rollout.sh rollback <ver>   bad release: every install of it goes back to <ver> (files must still be on the server)
set -u
cd "$(dirname "$0")/.." || exit 1
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"; H=root@156.67.29.119
CMD=${1:-status}; ARG=${2:-}
if [ "$CMD" = rollback ]; then
  [ -n "$ARG" ] || { echo "usage: rollback <version>"; exit 1; }
  SUMS=$(curl -sf https://rolandhrvth.hu/subbridge/dl/SHA256SUMS.txt) || exit 1
  SW=$(echo "$SUMS" | awk -v f="SubBridge-$ARG-windows-setup.exe" '$2==f{print $1}')
  SD=$(echo "$SUMS" | awk -v f="subbridge_${ARG}_amd64.deb" '$2==f{print $1}')
  [ -n "$SW" ] && [ -n "$SD" ] || { echo "STOP: $ARG files not on the server"; exit 1; }
fi
python3 - "$CMD" "$ARG" "${SW:-}" "${SD:-}" <<'PY'
import json, sys, time
cmd, arg, sw, sd = sys.argv[1:5]
p = 'site/feed/index.json'; d = json.load(open(p)); lt = d["latest"]
if cmd == "status":
    ro = lt.get("rollout") or {}
    k = 1.0 if not ro or ro.get("hours", 0) <= 0 else min(1, (time.time() - ro["start"]) / (ro["hours"] * 3600))
    pct = 100 if not ro else ro.get("from", 20) + (100 - ro.get("from", 20)) * k
    print(f"latest {lt['version']}  paused={lt.get('paused', False)}  replaces={lt.get('replaces', [])}  reach≈{pct:.0f}%")
    sys.exit(3)
if cmd == "pause":
    lt["paused"] = True
elif cmd == "resume":
    lt.pop("paused", None)
elif cmd == "full":
    lt.pop("paused", None); lt["rollout"] = {"start": int(time.time()), "hours": 0, "from": 100}
elif cmd == "rollback":
    bad = lt["version"]
    base = "https://rolandhrvth.hu/subbridge/dl/"
    d["latest"] = {"version": arg, "url": "https://rolandhrvth.hu/subbridge/#download",
                   "replaces": sorted(set((lt.get("replaces") or []) + [bad])),
                   "notes": {"hu": f"A {bad} verzióban hibát találtunk – visszaáll a {arg} verzióra, amíg javítjuk.",
                             "en": f"A problem was found in {bad} – going back to {arg} while it is fixed."},
                   "files": {"windows": {"url": base + f"SubBridge-{arg}-windows-setup.exe", "sha256": sw},
                             "linux-deb": {"url": base + f"subbridge_{arg}_amd64.deb", "sha256": sd}}}
else:
    print("unknown command"); sys.exit(1)
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
print("feed:", json.dumps(d["latest"], ensure_ascii=False)[:300])
PY
rc=$?
[ $rc = 3 ] && exit 0; [ $rc = 0 ] || exit 1
rsync -az --chmod=F644 -e "$SSH" site/feed/index.json $H:/var/www/rolandhrvth/subbridge/feed/index.json || exit 1
git add site/feed/index.json && git commit -q -m "Rollout: $CMD $ARG

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && git push -q origin main
echo DONE
