#!/usr/bin/env python
import argparse
from cmdproc import clementine, pidgin, window, extract_cmds
from cmdserver import CmdServer

def main():
    parser = argparse.ArgumentParser(description="Generate a corpa file for input into the lmtool web service")
    args = parser.parse_args()

    cmdprocs = [clementine.ClementineCmdProc, pidgin.PidginCmdProc, window.WindowCmdProc]
    program_to_delims = {}
    for cmdproc in cmdprocs:
        program_to_delims[cmdproc.config['program']] = extract_cmds(cmdproc.config['commands'])
    cmdserver_delims = extract_cmds(CmdServer.config['commands'])

    for server_cmd in cmdserver_delims:
        pr(*server_cmd)
    for cmdproc in program_to_delims:
        for cmdproc_cmd in program_to_delims[cmdproc]:
            pr(*cmdproc_cmd)
    # if server_cmd == 'SEND':
    #     for cmdproc in program_to_delims:
    #         cmdproc_cmds = program_to_delims[cmdproc]
    #     cmd_delims = [server_cmd] + 

def pr(*cmds):
    print " ".join(cmds)

def prefixes(l):
    for i in range(l):
        yield l[0:i+1]

if __name__ == '__main__':
    main()
