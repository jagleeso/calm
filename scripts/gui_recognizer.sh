#!/usr/bin/env bash
cd $(dirname $0)/..
DICT=resource/lmtool/calm.dic
LM=resource/lmtool/calm.lm
HMM=/usr/share/pocketsphinx/model/hmm/wsj1/
resource/example/pocketsphinx.py --dict $DICT --lm $LM
