#!/usr/bin/env python
import argparse
from cmdproc import clementine, pidgin, window
from cmdserver import CmdServer

def main():
    parser = argparse.ArgumentParser(description="Generate a corpa file for input into the lmtool web service")
    args = parser.parse_args()

    cmdprocs = [clementine.ClementineCmdProc, pidgin.PidginCmdProc, window.WindowCmdProc]
    program_to_delims = {}
    for cmdproc in cmdprocs:
        program_to_delims[cmdproc.config['program']] = extract_cmds(cmdproc.config['commands'], cmdprocs)

    cmdserver_delims = extract_cmds(CmdServer.config['commands'], cmdprocs)

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

def extract_cmds(cmd_config, cmdprocs):
    cmd_delims = []
    for cmd in cmd_config:
        cmd_delimiters = []
        was_cmdproc = False
        for i in range(len(cmd)):
            cmdarg = cmd[i]
            if cmdarg[0] == 'cmd':
                cmd_delimiters.append(cmdarg[1])
            elif cmdarg[0] == 'cmdproc' and cmd[i-1][0] != 'arg':
                for cmdproc in cmdprocs:
                    new_cmd = cmd_delimiters + [cmdproc.config['program'].upper()]
                    cmd_delims.append(new_cmd)
                was_cmdproc = True
                assert i == len(cmd) - 1
        if not was_cmdproc:
            cmd_delims.append(cmd_delimiters)
    return cmd_delims

if __name__ == '__main__':
    main()
