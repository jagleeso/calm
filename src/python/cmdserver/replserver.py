#!/usr/bin/env python
import cmdserver
import logging
import argparse

import logconfig
logger = logging.getLogger(__name__)

class ReplServer(cmdserver.CmdServer):
    def __init__(self, cmdproc_paths, port):
        super(ReplServer, self).__init__(cmdproc_paths, port)

    def start(self):
        logger.info("Starting REPL server...")
        self.startup_cmdprocs()
        self.setup_dispatch_loop()
        # while True:
        #     try:
        #         cmd_string = raw_input(">> ")
        #     except EOFError:
        #         cmdserver.exit_server()
        #     cmd = cmd_string.split()
        #     self.dispatch_cmd_to_cmdproc(cmd)

    # def dispatch_cmd_to_cmdproc(self, cmd_strs):
    #     try:
    #         self._cmd_dfa.cmd(cmd_strs)
    #     except (cmdserver.IncompleteCmdProcCommand, cmdserver.BadCmdProcCommand, 
    #             cmdserver.IncompleteCmdServerCommand, cmdserver.BadCmdServerCommand) as e:
    #         logger.exception(e.message)
    #     def err(e):
    #         # (cmdserver.IncompleteCmdProcCommand, cmdserver.BadCmdProcCommand, 
    #         # cmdserver.IncompleteCmdServerCommand, cmdserver.BadCmdServerCommand)
    #         logger.exception(e.message)
    #         callback()
    #     self._cmd_dfa.cmd(cmd_strs, callback, err)

    # def dispatch_cmd_to_cmdproc(self, cmd_strs):
    #     if len(cmd_strs) < 1:
    #         logger.error("Command string too short")
    #     if cmd_strs[0] == 'RECORD':
    #         name = cmd_strs[1]
    #         self.record_macro(name)
    #     elif cmd_strs[0] == 'DONE':
    #         self.end_macro()
    #     elif cmd_strs[0] == 'REPLAY':
    #         name = cmd_strs[1]
    #         self.replay_macro(name)
    #     elif cmd_strs[0] == 'SEND':
    #         program = cmd_strs[1]
    #         cmd_name = cmd_strs[2]
    #         # cmd_args = " ".join(cmd_strs[3:])
    #         if program == 'pidgin' and cmd_name == 'REPLY':
    #             cmd_args = cmd_strs[3:]
    #         elif program == 'clementine' and cmd_name == 'VOLUME':
    #             cmd_args = cmd_strs[3]
    #         else:
    #             cmd_args = cmd_strs[3:]
    #         cmd = package_cmd(cmd_name, cmd_args)
    #         self.send_cmd(program, cmd)
    #     else:
    #         logger.error("Unrecognized command \"%s\" in \"%s\"", cmd_strs[0], " ".join(cmd_strs))

def package_cmd(cmd_name, cmd_args):
    return [['cmd', cmd_name], ['arg', cmd_args]]

def main():
    # logger.setLevel(logging.INFO)
    logger.info("TEST")

    parser = argparse.ArgumentParser(description="A REPL command server.")
    args, server = cmdserver.cmdserver_main(ReplServer, parser)

    server.start()

if __name__ == '__main__':
    main()
