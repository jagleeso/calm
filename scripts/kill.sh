#!/usr/bin/env bash
cmdprocs() {
    ps -ef | grep cmdproc | grep -v grep | awk '{print $2}'
}
cmdprocs
cmdprocs | xargs kill
