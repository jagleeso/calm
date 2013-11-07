from message import *
import cmdserver

from multiprocessing import Process, Value, Array, Lock, Manager
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

        # Recording macros...
        self._manager = Manager()
        self._macrolock = Lock()
        self._recording = Value('i', False, lock=False)
        self._macroname = Array('c', 1024, lock=False)
        self._macro_cmds = self._manager.list()
        self._macros = self._manager.dict()

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
        if cmd[0][1] == 'RECORD':
            macroname = cmd[1][1]
            # Time to record a macro; tell the command server we're ready.
            self.begin_recording(macroname)
            send(self.socket, 'Ready to record')
            return
        elif cmd[0][1] == 'DONE':
            self.stop_recording()
            return
        elif cmd[0][1] == 'REPLAY':
            macroname = cmd[1][1]
            self.replay_macro(macroname)
            return
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

    # Atomic operations on macros

    def replay_macro(self, name):
        macro_cmds = None
        self._macrolock.acquire()
        macro_cmds = self._macros.get(name, None)
        self._macrolock.release()
        if macro_cmds is None:
            # TODO: notify unknown macro
            logger.error("No such macro %s", name)
            return
        for cmd in macro_cmds:
            cmd()

    def begin_recording(self, name):
        self._macrolock.acquire()
        assert self._macroname.value == ''
        assert self._recording.value == False
        self._macroname.value = name
        self._recording.value = True
        logger.info("begin_recording: name = %s, is_recording = %s", self._macroname.value, self._recording.value)
        self._macrolock.release()

    def _assert_recording(self):
        assert self._macroname.value != ''
        assert self._recording.value == True

    def is_recording(self):
        check = None
        self._macrolock.acquire()
        check = bool(self._recording.value)
        self._macrolock.release()
        return check

    def stop_recording(self):
        cmds = None
        name = None

        self._macrolock.acquire()
        self._assert_recording()
        name = self._macroname.value
        cmds = list(self._macro_cmds)
        self._macros[name] = cmds

        self._macroname.value = ''
        self._recording.value = False 
        logger.info("stop_recording: name = %s, cmds = %s, is_recording = %s", name, cmds, self._recording.value)
        self._macrolock.release()

        return name, cmds

    def put_cmd(self, cmd):
        self._macrolock.acquire()
        self._assert_recording()
        self._macro_cmds.append(cmd)
        logger.info("begin_recording: cmd = %s, _macro_cmds = %s", cmd, list(self._macro_cmds))
        self._macrolock.release()

def cmdproc_main(cmdproc_class, parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="A command processor.")
    parser.add_argument('--server', default="localhost")
    parser.add_argument('--port', type=int, default=cmdserver.DEFAULT_CMDSERVER_PORT)
    args = parser.parse_args()

    processor = cmdproc_class(args.server, args.port)

    return (args, processor)
