from message import *
import argparse
import os
import sys
import socket
# http://victorlin.me/posts/2012/08/good-logging-practice-in-python/
import logging
import signal

DEFAULT_CMDSERVER_PORT = 2525

import logconfig
logger = logging.getLogger(__name__)

class CmdServer(object):
    """
    Spawn cmdprocs and send them sockets to listen to messages on, and register their 
    names with the sockets

    cmdprocs:
    a list of paths to execute
    """
    def __init__(self, cmdproc_paths, port):
        self.port = port
        self.cmdproc_paths = cmdproc_paths

        self._cmdproc_config = {}
        self._program_to_socket = {}
        self._program_to_pid = {}

    def start(self):
        raise NotImplementedError

    def send_cmd(self, program, cmd):
        cmdproc_socket = self._program_to_socket[program]
        send_cmd(cmdproc_socket, cmd)

    def make_cmdserver_socket(self):
        """
        Note that a server must perform the sequence socket(), bind(), listen(), accept() 
        (possibly repeating the accept() to service more than one client).

        A client only needs the sequence socket(), connect(). Also note that the server does 
        not sendall()/recv() on the socket it is listening on but on the new socket returned 
        by accept().
        """
        host = 'localhost'
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((host, self.port))

    def startup_cmdprocs(self):
        """
        Fork the cmdproc processes, and get all their configuration information.
        """
        self.make_cmdserver_socket()
        for cmdproc_path in self.cmdproc_paths:
            (cmdproc_socket, pid, config) = fork_cmdproc(self.socket, self.port, cmdproc_path)
            self._cmdproc_config[config['program']] = config
            self._program_to_socket[config['program']] = cmdproc_socket
            self._program_to_pid[config['program']] = pid
        setup_signal_handler(self._program_to_pid.values())

def parse_cmd(words, serverproc_cmds, cmdproc_cmds, cmd_delimeters):
    """
    Takes a DFA that transitions on words based on whether they are command delimiters.
    Based on the transitions, returns a command array of the form:

    [['cmd', 'SEND'], ['cmd', 'clementine'], ['cmd', 'VOLUME'], ['arg', 55]]

    serverproc_cmds looks like:
    [ 
        [['cmd', 'SEND'], ['arg', str], ['cmdproc', 1]], # 1 => use arg at index 1 as cmdproc identifier 
    ],

    cmdproc_cmds looks like:
    [
        'clementine': [ 
            [['cmd', 'PLAY']],
            [['cmd', 'PAUSE']],
            [['cmd', 'VOLUME'], ['arg', int]],
        ],
        ...
    ]

    cmd_delimeters looks like:
    ['SEND', 'clementine', 'VOLUME', 'PLAY', 'PAUSE', 'VOLUME']

    """
    # Store the results of each transition
    cmd = []
    def arg():
    def cmdproc():
    def cmd():
    state = 'cmdserver_or_current_cmdproc'

def build_cmd_dfa():
    """
    Build a DFA for parse_cmd using the serverproc commands and cmdproc commands.

    """
    pass

def cmdserver_main(cmdserver_class, parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="A command server.")
    parser.add_argument('cmdproc_paths', nargs='+')
    parser.add_argument('--port', type=int, default=DEFAULT_CMDSERVER_PORT)
    args = parser.parse_args()

    cmdserver = cmdserver_class(args.cmdproc_paths, args.port)

    return (args, cmdserver)

_CMDPROC_PIDS = None
def exit_cmdserver(signum, frame):
    signal.signal(signal.SIGINT, _ORIGINAL_SIGINT)
    signal.signal(signal.SIGTERM, _ORIGINAL_SIGTERM)
    signal.signal(signal.SIGHUP, _ORIGINAL_SIGHUP)
    logger.info("Terminating command server and command server processes (%s)...", _CMDPROC_PIDS)
    if _CMDPROC_PIDS is not None:
        for pid in _CMDPROC_PIDS:
            os.kill(pid, signal.SIGTERM)
    sys.exit()

_ORIGINAL_SIGINT = signal.getsignal(signal.SIGINT)
_ORIGINAL_SIGTERM = signal.getsignal(signal.SIGTERM)
_ORIGINAL_SIGHUP = signal.getsignal(signal.SIGHUP)
def setup_signal_handler(cmdproc_pids):
    global _CMDPROC_PIDS
    _CMDPROC_PIDS = cmdproc_pids
    signal.signal(signal.SIGINT, exit_cmdserver)
    signal.signal(signal.SIGTERM, exit_cmdserver)
    signal.signal(signal.SIGHUP, exit_cmdserver)

def fork_cmdproc(cmdserver_socket, cmdserver_port, cmdproc_path):
    """
    Spawn a child cmdproc process, passing it a --listen argument identifying the socket 
    for communication with the cmdserver.

    Wait for it to start up and connect to our socket, then ask for its configuration 
    data:
    { 
        # the program it interacts with (e.g. clementine)
        'program': 'clementine',
        # the commands it handles
        'commands': {
            [['cmd', 'PLAY'], ['arg', "name-or-search"]],
            [['cmd', 'START']],
            [['cmd', 'NEXT']],
            [['cmd', 'PREVIOUS']],
            [['cmd', 'PAUSE']],
        },
    }
    """
    try:
        pid = os.fork()
    except OSError, e:
        ## some debug output
        sys.exit(1)
    if pid == 0:
        ## eventually use os.putenv(..) to set environment variables
        ## os.execv strips of args[0] for the arguments
        os.execv(cmdproc_path, [cmdproc_path, '--server', 'localhost', '--port', str(cmdserver_port)])
    cmdserver_socket.listen(1)
    (cmdproc_socket, address) = cmdserver_socket.accept()
    config = recv_msg(cmdproc_socket)
    assert 'program' in config
    assert 'commands' in config
    logger.info("New command processor \"%s\" (PID: %s) connected with configuration:", config['program'], pid)
    logger.info(config)
    return (cmdproc_socket, pid, config)

if __name__ == '__main__':
    main()
