set -e
ROOT=`cd ../; echo $PWD; cd -`

cd_root() {
    cd $ROOT
}

start_cmdserver() {
    local cmdserver="$1"
    shift 1
    cd_root
    src/cmdserver/$cmdserver src/cmdproc/* "$@"
    cd -
}

DICT=resource/lmtool/calm.dic
LM=resource/lmtool/calm.lm
HMM=/usr/share/pocketsphinx/model/hmm/wsj1/
