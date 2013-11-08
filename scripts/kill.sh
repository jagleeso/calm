#!/usr/bin/env bash
ps -ef | grep cmdproc | grep -v grep | awk '{print $2}' | xargs kill 
