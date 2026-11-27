#!/bin/bash
# tm_put.sh <batch>: huk/<batch>.tsv from every finished work/<batch>_NN.hu (LOCAL tool)
b=$1; cd "$(dirname "$0")/../build/tm"
for h in work/${b}_*.hu; do t=${h%.hu}.tsv; [ "$(wc -l < $t)" = "$(wc -l < $h)" ] && paste <(cut -f1 $t) $h; done | awk -F'\t' '$2!=""' > huk/$b.tsv
wc -l < huk/$b.tsv
