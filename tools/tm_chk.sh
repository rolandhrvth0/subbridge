#!/bin/bash
# tm_chk.sh <chunk>: line count + every 20th pair, to catch an off-by-one (LOCAL tool)
c=$1; cd "$(dirname "$0")/../build/tm"
echo "$(wc -l < work/$c.tsv) en / $(wc -l < work/$c.hu) hu"
paste <(cut -f2 work/$c.tsv) work/$c.hu | awk -F'\t' 'NR%20==0 || NR==1 {print NR": "substr($1,1,50)" || "substr($2,1,50)}'
