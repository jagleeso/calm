#!/usr/bin/env bash
cd $(dirname $0)
source ./common.sh
cd_root

start_cmdserver voiceserver --lm $LM --dict $DICT
