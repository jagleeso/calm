from message import *
import cmdserver

from multiprocessing import Process
import socket 
import logging
import argparse

import logconfig
logger = logging.getLogger(__name__)

class CmdProc(object):
    """
    Send the command server our configuration info, and await commands.

    Command processors are used like:
    proc = CmdProc('localhost', 2525)
    proc.start() 
    # which does:
    # self.connect()
    # ...
    # self.receive_and_dispatch_loop()
    """
    def __init__(self, cmdserver_server, cmdserver_port, config=None, cmd_to_handler=None):
        if config is not None:
            # might define as class variable
            self.config = config
        if cmd_to_handler is not None:
            # might define as class variable
            self.cmd_to_handler = cmd_to_handler
        self.port = cmdserver_port
        self.server = cmdserver_server

    def connect(self):
        """
        Connect to the command server.

        A client only needs the sequence socket(), connect(). Also note that the server does 
        not sendall()/recv() on the socket it is listening on but on the new socket returned 
        by accept().
        """
        host = 'localhost'
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.server, self.port))
        # send the cmdserver our configuration information
        send_msg(self.socket, self.config)

    def start(self):
        raise NotImplementedError

    def get_cmd_handler(self, cmd):
        """
        Overridden cmdproc's.
        """
        if self.cmd_to_handler is None:
            return None
        return self.handle_cmd_with(cmd, self.cmd_to_handler)

    def default_handler(self, cmd):
        logger.error("Couldn't find a handler for command: %s", cmd)

    def receive_and_dispatch(self):
        """
        Dispatch a new thread to handle the next command (don't want to block on newly 
        arriving commands).
        """
        cmd = recv_cmd(self.socket)
        handler = self.get_cmd_handler(cmd)
        if handler is None:
            handler = self.default_handler
        p = Process(target=handler, args=(cmd,))
        p.start()

    def receive_and_dispatch_loop(self):
        while True:
            self.receive_and_dispatch()

    def handle_cmd_with(self, cmd, cmd_to_handler):
        """
        Look at the first 'cmd', and dispatch on cmd_to_handler (dict from cmd name to handler).
        """
        logger.info("cmd %s, cmd_to_handler %s", cmd, cmd_to_handler)
        assert cmd[0][0] == 'cmd'
        command_name = cmd[0][1]
        return cmd_to_handler[command_name]

def cmdproc_main(cmdproc_class, parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="A command processor.")
    parser.add_argument('--server', default="localhost")
    parser.add_argument('--port', type=int, default=cmdserver.DEFAULT_CMDSERVER_PORT)
    args = parser.parse_args()

    processor = cmdproc_class(args.server, args.port)

    return (args, processor)
