#!/usr/bin/env python
import cmdserver
import logging
import argparse

from cmdserver import voiceserver
import notify

import logconfig
logger = logging.getLogger(__name__)

class GUIServer(cmdserver.CmdServer):
    def __init__(self, notifier_path, cmdproc_paths, port):
        super(GUIServer, self).__init__(notifier_path, cmdproc_paths, port)
        self.listening = True
        self.notifier = 'gui'

    def start(self):
        logger.info("Starting GUI server...")
        self.startup_procs()
        self._cmd_dfa._string_input_handler = voiceserver.AutocompleteGUIInputHandler()
        self.setup_dispatch_loop()
        self._cmd_dfa._string_input_handler.main_loop()

def package_cmd(cmd_name, cmd_args):
    return [['cmd', cmd_name], ['arg', cmd_args]]

def main():
    parser = argparse.ArgumentParser(description="A GUI command server.")
    args, server = cmdserver.cmdserver_main(GUIServer, parser)

    server.start()

if __name__ == '__main__':
    main()
