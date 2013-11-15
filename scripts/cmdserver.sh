#!/usr/bin/env bash
cmd="$1"
shift 1

cd $(dirname $0)
source ./common.sh
cd -

start_cmdserver ${cmd}server "$@"
