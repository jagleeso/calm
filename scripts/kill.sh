#!/usr/bin/env bash
cmdprocs() {
    ps -ef | grep 'cmdproc\|notify\.py\|context\.py\|status\.py' | grep -v grep | awk '{print $2}'
}
cmdprocs
cmdprocs | xargs kill "$@"
