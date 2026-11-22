#!/bin/bash
# Publish a release after its CI run passed: upload installers (old versions stay), checksums, site download
# links, and ONLY THEN the feed "latest" entry (this is what makes every installed app update).
# Usage: tools/publish_release.sh <ci-run-id> <version>
set -u
cd "$(dirname "$0")/.."
RUN=$1; V=$2
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"; H=root@156.67.29.119; DL=/var/www/rolandhrvth/subbridge/dl
gh run watch "$RUN" --interval 60 > /dev/null 2>&1
for j in test linux windows; do
  c=$(gh run view "$RUN" --json jobs --jq ".jobs[] | select(.name==\"$j\") | .conclusion")
  [ "$c" = "success" ] || { echo "STOP: $j=$c"; exit 1; }
done
A=build/tmp/rel-$V; rm -rf $A; mkdir -p $A
gh run download "$RUN" -n windows -D $A/win || exit 1
gh run download "$RUN" -n linux -D $A/lin || exit 1
WIN=$(find $A/win -iname "*setup*.exe" | head -1); DEB=$(find $A/lin -name "*.deb" | head -1); TGZ=$(find $A/lin -name "*.tar.gz" | head -1)
[ -n "$WIN" ] && [ -n "$DEB" ] || { echo "STOP: artifacts missing"; exit 1; }
cp "$WIN" dist/SubBridge-$V-windows-setup.exe; cp "$DEB" dist/subbridge_${V}_amd64.deb
[ -n "$TGZ" ] && cp "$TGZ" dist/SubBridge-$V-linux-x86_64.tar.gz
dpkg-deb -f dist/subbridge_${V}_amd64.deb Version | grep -qx "$V" || { echo "STOP: deb version mismatch"; exit 1; }
FILES="dist/SubBridge-$V-windows-setup.exe dist/subbridge_${V}_amd64.deb"
[ -n "$TGZ" ] && FILES="$FILES dist/SubBridge-$V-linux-x86_64.tar.gz"
rsync -a --chmod=F644 -e "$SSH" $FILES $H:$DL/ || exit 1
$SSH $H "cd $DL && sha256sum *.deb *.exe *.apk *.tar.gz > SHA256SUMS.txt && chmod 644 SHA256SUMS.txt" || exit 1
SW=$(sha256sum dist/SubBridge-$V-windows-setup.exe | cut -d' ' -f1); SD=$(sha256sum dist/subbridge_${V}_amd64.deb | cut -d' ' -f1)
# verify what the server serves matches
for f in SubBridge-$V-windows-setup.exe subbridge_${V}_amd64.deb; do
  curl -sf "https://rolandhrvth.hu/subbridge/dl/$f" | sha256sum | cut -d' ' -f1 > /tmp/srv.sha
  grep -q "$(cat /tmp/srv.sha)" <(echo "$SW $SD") || { echo "STOP: server copy of $f differs"; exit 1; }
done
python3 - "$V" "$SW" "$SD" <<'PY'
import json, re, sys
v, sw, sd = sys.argv[1:4]
p = 'site/index.html'; s = open(p).read()
s = re.sub(r'dl/SubBridge-[0-9.]+-windows-setup\.exe", note: "\.exe · (\d+) MB · v[0-9.]+',
           lambda m: f'dl/SubBridge-{v}-windows-setup.exe", note: ".exe · {m.group(1)} MB · v{v}', s)
s = re.sub(r'dl/subbridge_[0-9.]+_amd64\.deb", note: "\.deb · (\d+) MB · v[0-9.]+',
           lambda m: f'dl/subbridge_{v}_amd64.deb", note: ".deb · {m.group(1)} MB · v{v}', s)
s = re.sub(r'dl/SubBridge-[0-9.]+-linux-x86_64\.tar\.gz', f'dl/SubBridge-{v}-linux-x86_64.tar.gz', s)
open(p, 'w').write(s)
p = 'site/feed/index.json'; d = json.load(open(p))
base = "https://rolandhrvth.hu/subbridge/dl/"
d["latest"] = {"version": v, "url": "https://rolandhrvth.hu/subbridge/#download",
               "notes": {"hu": "Windows: a magyar felirat kattintás nélkül megjelenik (F11 teljes képernyőn is), több monitornál is a helyén van, és a felirat-réteg egy váratlan hibától sem áll le.",
                         "en": "Windows: translations show without clicking into the game (also in F11 fullscreen), land on the right spot with several monitors, and the overlay no longer stops on an unexpected error."},
               "files": {"windows": {"url": base + f"SubBridge-{v}-windows-setup.exe", "sha256": sw},
                         "linux-deb": {"url": base + f"subbridge_{v}_amd64.deb", "sha256": sd}}}
d["news"].insert(0, {"id": f"{v}-release", "date": "2026-11-22",
    "title": {"hu": f"Megjelent a SubBridge {v}", "en": f"SubBridge {v} is out"},
    "body": d["latest"]["notes"]})
json.dump(d, open(p, 'w'), ensure_ascii=False, indent=2)
PY
rsync -az --chmod=D755,F644 -e "$SSH" --exclude dl site/ $H:/var/www/rolandhrvth/subbridge/ || exit 1
git add site && git commit -q -m "Release $V: downloads and feed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && git push -q origin main
curl -s https://rolandhrvth.hu/subbridge/feed/index.json | python3 -c "import json,sys;print('feed latest:', json.load(sys.stdin)['latest']['version'])"
echo DONE
