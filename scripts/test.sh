#!/usr/bin/env bash
repl_input="$1"
sleep_period=1
shift 1

read_input() {
    while read line; do
        echo $line
        sleep $sleep_period
    done < $1
    cat | while read line; do
        echo $line
    done
}

cd $(dirname $0)/..
read_input $repl_input | src/cmdserver/replserver src/cmdproc/* "$@" 
