#!/usr/bin/env bash
cd $(dirname $0)/..
DICT=resource/lmtool/calm.dic
LM=resource/lmtool/calm.lm
HMM=/usr/share/pocketsphinx/model/hmm/wsj1/
# extra params from outdated website...they don't even work.
# http://www.speech.cs.cmu.edu/sphinx/models/#am
#
# -subvq      wsj_all_cd30.mllt_cd_cont_4000/subvq \
# -beam       1e-80 \
# -wbeam      1e-60 \
# -subvqbeam  1e-2 \
# -maxhmmpf   2500 \
# -maxcdsenpf 1500 \
# -maxwpf     20 \
pocketsphinx_continuous -lm $LM -dict $DICT \
    -hmm $HMM \
