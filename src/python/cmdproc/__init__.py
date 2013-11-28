from message import *
import config
import notify

from multiprocessing import Process, Value, Array, Lock, Manager
import socket 
import logging
import argparse

import logconfig
logger = logging.getLogger(__name__)


def madeup(arg1, arg2):
    logger.info("arg1 is %s, arg2 is %s", arg1.value, arg2.value)

# Recording macros...
# _manager = Manager()
# _macrolock = Lock()
# For some reason if lock=True isn't set, things don't synchronize properly...!
# _recording = Value('i', False, lock=True)
# _macroname = Array('c', 1024, lock=True)
# _macro_cmds = _manager.list()
# _macros = _manager.dict()

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

        logger.error("calling __init__ in cmdproc")
        # Recording macros...
        self._manager = Manager()
        self._macrolock = Lock()
        self._recording = Value('i', False, lock=True)
        self._macroname = Array('c', 1024, lock=True)
        self._macro_cmds = self._manager.list()
        self._macros = self._manager.dict()

        self.notifier = 'gui'
        self._notifylock = Lock()

    def startup_notify_server(self):
        (s, pid) = fork_notify_server(self.notifier_type, config.DEFAULT_NOTIFY_PORT)
        self.notify_socket = s 
        self.notify_server_pid = pid

    def notify_server(self, *args, **kwargs):
        self._notifylock.acquire()
        if 'icon' in self.config:
            kwargs['icon'] = self.config['icon']
        result = notify.notify_server(self, *args, **kwargs)
        self._notifylock.release()
        return result

    def get_candidates(self, request):
        # no candidates by default
        return None

    def connect(self):
        """
        Connect to the command server.

        A client only needs the sequence socket(), connect(). Also note that the server does 
        not sendall()/recv() on the socket it is listening on but on the new socket returned 
        by accept().
        """
        self.notify_socket = notify.notify_server_connection(config.DEFAULT_HOST, config.DEFAULT_NOTIFY_PORT)

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
        cmd_or_request = recv_cmd_or_request(self.socket)
        if is_request(cmd_or_request):
            request = cmd_or_request
            candidates = self.get_candidates(request)
            logger.info("Send back candidates to cmdserver for request %s: %s", request, candidates)
            send_candidates(self.socket, ['candidates', candidates])
        else:
            assert is_cmd(cmd_or_request)
            cmd = cmd_or_request
            if cmd[0][1] == 'RECORD':
                macroname = cmd[1][1]
                # Time to record a macro; tell the command server we're ready.
                self.begin_recording(macroname)
                send(self.socket, 'Ready to record')
                return
            elif cmd[0][1] == 'FINISH':
                self.stop_recording()
                return
            elif cmd[0][1] == 'REPLAY':
                macroname = cmd[1][1]
                self.replay_macro(macroname)
                return
            elif cmd[0][1] == 'UNDO':
                if self.is_recording():
                    self.undo_last_cmd()
                return
            handler = self.get_cmd_handler(cmd)
            if handler is None:
                handler = self.default_handler
            if self.is_recording():
                # HACK: make it so we can send back a ['response', 'recorded'] or ['response', 'not recorded']
                # (can't access the socket in a new Process).
                length_before = len(self._macro_cmds)
                handler(cmd)
                length_after = len(self._macro_cmds)
                if length_after != length_before:
                    logger.info("%s WAS recorded", cmd)
                    assert length_after == length_before + 1
                    send_response(self.socket, ['response', 'recorded'])
                else:
                    logger.info("%s was NOT recorded", cmd)
                    send_response(self.socket, ['response', 'not recorded'])
            else:
                # logger.info("in cmdproc before starting process _recording == %s", _recording)
                # def notifier_wrapper():
                #     self.notifier = notify.GUINotifier()
                #     handler(cmd)
                # p = Process(target=notifier_wrapper)
                p = Process(target=handler, args=(cmd,))
                p.start()
        # logger.info("in cmdproc after starting process _recording == %s", _recording)
        # p = Process(target=madeup, args=(_recording, some_arg))
        # p.start()

    def undo_last_cmd(self):
        assert self.is_recording()

        self._macrolock.acquire()
        if len(self._macro_cmds) == 0:
            self._macrolock.release()
            return
        logger.info("About to UNDO in %s.  Current commands: %s", self.config['program'], self._macro_cmds)
        old_cmd = self._macro_cmds[-1]
        del self._macro_cmds[-1]
        self._macrolock.release()
        self.notify_server("Undo last command", pretty_cmd(old_cmd[0]))
        logger.info("%s: %s undone.", self.config['program'], old_cmd)
        # TODO: self.notifier.post("%s undone.", old_cmd)

    def receive_and_dispatch_loop(self):
        while True:
            self.receive_and_dispatch()

    def handle_cmd_with(self, cmd, cmd_to_handler):
        """
        Look at the first 'cmd', and dispatch on cmd_to_handler (dict from cmd name to handler).
        """
        # logger.info("cmd %s, cmd_to_handler %s", cmd, cmd_to_handler)
        cmds = tuple([c[1] for c in cmd if c[0] == 'cmd'])
        # assert cmd[0][0] == 'cmd'
        # command_name = cmd[0][1]
        # return cmd_to_handler[command_name]
        return cmd_to_handler[cmds]

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
        for args, kwargs in macro_cmds:
            logger.info("REPLAY %s: args = %s, kwargs = %s", name, args, kwargs)
            handler = self.get_cmd_handler(args)
            handler(args, **kwargs)

    def begin_recording(self, name):
        self._macrolock.acquire()
        assert self._macroname.value == ''
        assert self._recording.value == False
        self._macroname.value = name
        self._recording.value = True
        logger.info("begin_recording: name = %s, is_recording = %s", self._macroname.value, self._recording.value)
        self._assert_recording()
        self._macrolock.release()

    def _assert_recording(self):
        assert self._macroname.value != ''
        assert self._recording.value == True

    def is_recording(self):
        check = None
        self._macrolock.acquire()
        check = bool(self._recording.value)
        # logger.info("is_recording: check = %s", check)
        self._macrolock.release()
        return check

    def stop_recording(self):
        cmds = None
        name = None

        self._macrolock.acquire()
        self._assert_recording()

        name = self._macroname.value
        cmds = list(self._macro_cmds)
        if len(cmds) != 0:
            # Otherwise the user recorded an empty macro; ignore it.
            self._macros[name] = cmds

        self._macro_cmds[:] = []
        self._macroname.value = ''
        self._recording.value = False 

        logger.info("stop_recording: name = %s, cmds = %s, is_recording = %s, _macro_cmds = %s", name, cmds, self._recording.value, self._macro_cmds)
        self._macrolock.release()

        return name, cmds

    def put_cmd(self, args, **kwargs):
        self._macrolock.acquire()
        self._assert_recording()
        self._macro_cmds.append([args, kwargs])
        logger.info("put_cmd: args = %s, kwargs = %s, _macro_cmds = %s", args, kwargs, list(self._macro_cmds))
        self.notify_server("Recorded command", pretty_cmd(args))
        self._macrolock.release()

def pretty_cmd(cmd):
    def cmd_arg_as_str(cmdarg):
        if cmdarg[0] in ['cmd', 'arg']:
            return str(cmdarg[1])
        else:
            return str(cmdarg)
    return " ".join(cmd_arg_as_str(c) for c in cmd)

def cmdproc_main(cmdproc_class, parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="A command processor.")
    parser.add_argument('--server', default="localhost")
    parser.add_argument('--port', type=int, default=config.DEFAULT_CMDSERVER_PORT)
    args = parser.parse_args()

    processor = cmdproc_class(args.server, args.port)

    return (args, processor)

def extract_cmds(cmd_config):
    cmd_delims = []
    for cmd in cmd_config:
        cmd_delimiters = []
        for cmdarg in cmd:
            if cmdarg[0] == 'cmd':
                cmd_delimiters.append(cmdarg[1])
        cmd_delims.append(cmd_delimiters)
    return cmd_delims
