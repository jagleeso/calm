#!/usr/bin/env python
import cmdserver
import logging
import argparse

from cmdserver import voiceserver

import logconfig
logger = logging.getLogger(__name__)

class GUIServer(cmdserver.CmdServer):
    def __init__(self, cmdproc_paths, port):
        super(GUIServer, self).__init__(cmdproc_paths, port)

    def start(self):
        logger.info("Starting GUI server...")
        self.startup_cmdprocs()
        self._cmd_dfa._string_input_handler = voiceserver.AutocompleteGUIInputHandler()
        self.setup_dispatch_loop()
        self._cmd_dfa._string_input_handler.main_loop()

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
    parser = argparse.ArgumentParser(description="A GUI command server.")
    args, server = cmdserver.cmdserver_main(GUIServer, parser)

    server.start()

if __name__ == '__main__':
    main()
