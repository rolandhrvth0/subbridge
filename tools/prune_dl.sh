#!/bin/bash
# Remove old installers from the download folder on the server, keeping the newest KEEP versions (default 2)
# and every .apk. Dry run unless called with --yes. Usage: tools/prune_dl.sh [--yes] [KEEP]
set -u
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"; H=root@156.67.29.119; DL=/var/www/rolandhrvth/subbridge/dl
YES=0; [ "${1:-}" = "--yes" ] && { YES=1; shift; }
KEEP=${1:-2}
$SSH $H "cd $DL && ls" > /tmp/dl.list || exit 1
vers=$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' /tmp/dl.list | sort -uV)
keep=$(echo "$vers" | tail -n "$KEEP")
old=$(grep -vE '\.apk$|SHA256SUMS' /tmp/dl.list | while read f; do v=$(echo "$f" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+'); echo "$keep" | grep -qx "$v" || echo "$f"; done)
[ -z "$old" ] && { echo "nothing to remove"; exit 0; }
echo "keep versions: $(echo $keep)"; echo "remove:"; echo "$old" | sed 's/^/  /'
[ $YES = 1 ] || { echo "(dry run – add --yes)"; exit 0; }
$SSH $H "cd $DL && rm -f $(echo $old) && sha256sum *.deb *.exe *.apk *.tar.gz > SHA256SUMS.txt; df -h / | tail -1"
