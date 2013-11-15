#!/usr/bin/env bash
repl_input="$1"
sleep_period=1
shift 1

cd $(dirname $0)
source ./common.sh
cd -

read_input() {
    while read line; do
        echo $line
        sleep $sleep_period
    done < $1
    cat | while read line; do
        echo $line
    done
}

read_input $repl_input | start_cmdserver replserver "$@" 
