#!/usr/bin/env bash
# usage: ... > record.wav
arecord -f S16_LE -r 8000 -D default
