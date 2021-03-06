#!/usr/bin/env bash
cd $(dirname $0)
source ./common.sh
cd_root

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

# -cmn current \
pocketsphinx_continuous -lm $LM -dict $DICT \
    -hmm $HMM \
