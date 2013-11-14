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
        cmdproc_cmds = {}
        for cmdproc_path in self.cmdproc_paths:
            (cmdproc_socket, pid, config) = fork_cmdproc(self.socket, self.port, cmdproc_path)
            self._cmdproc_config[config['program']] = config
            cmdproc_cmds[config['program']] = config['commands']
            self._program_to_socket[config['program']] = cmdproc_socket
            self._program_to_pid[config['program']] = pid
        setup_signal_handler(self._program_to_pid.values())

        self._cmd_dfa = CmdDFA(self, cmdproc_cmds)

    def record_macro(self, name):
        """
        Get the command processors ready to record a macro (on return, we're ready).
        """
        for socket in self._program_to_socket.values():
            send_cmd(socket, [['cmd', 'RECORD'], ['arg', name]])
        for program in self._program_to_socket.keys():
            # Wait for all the command processors to be ready to record a macro.
            socket = self._program_to_socket[program]
            ready_msg = recv(socket)
            if ready_msg != 'Ready to record':
                logger.error("The command processor for %s failed to return 'Ready to record', and instead returned '%s'", program, ready_msg)
                for s in self._program_to_socket.values():
                    # Tell processes to stop recording the macro, since some of them might 
                    # be recording.
                    send_cmd(socket, [['cmd', 'DONE']])
                return False
        return True

    def replay_macro(self, name):
        """
        Tell the command processors to replay macro.
        """
        for s in self._program_to_socket.values():
            # Tell processes to stop recording the macro, since some of them might 
            # be recording.
            send_cmd(s, [['cmd', 'REPLAY'], ['arg', name]])

    def end_macro(self):
        """
        Tell the command processors to stop recording the macro.
        """
        for socket in self._program_to_socket.values():
            send_cmd(socket, [['cmd', 'DONE']])

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
    # def arg():
    # def cmdproc():
    # def cmd():
    state = 'cmdserver_or_current_cmdproc'

def build_cmd_dfa():
    """
    Build a DFA for parse_cmd using the serverproc commands and cmdproc commands.

    """
    pass

def cmdserver_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="A command server.")
    parser.add_argument('cmdproc_paths', nargs='+')
    parser.add_argument('--port', type=int, default=DEFAULT_CMDSERVER_PORT)
    return parser

def cmdserver_main(cmdserver_class, parser=None):
    parser = cmdserver_arg_parser(parser)
    args = parser.parse_args()

    cmdserver = cmdserver_class(args.cmdproc_paths, args.port)

    return (args, cmdserver)

_CMDPROC_PIDS = None
def exit_cmdserver(signum, frame):
    signal.signal(signal.SIGINT, _ORIGINAL_SIGINT)
    signal.signal(signal.SIGTERM, _ORIGINAL_SIGTERM)
    signal.signal(signal.SIGHUP, _ORIGINAL_SIGHUP)
    exit_server()

def exit_server():
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

class CmdDFA(object):
    def __init__(self, cmdserver, cmdproc_cmds):
        self._cmdserver = cmdserver
        self._cmdproc_dfa = {}
        self._init_dfa(cmdproc_cmds)

        self._is_sending = False
        self._receiving_cmdproc = None

    def get_ready_to_send(self, cmdproc):
        self._is_sending = True
        self._receiving_cmdproc = cmdproc

    def done_sending(self):
        self._is_sending = False
        self._receiving_cmdproc = None 

    def cmd(self, words):
        """
        Interpret a command for the server or the current in focus application.
        """
        cmd = []
        def consume(i, cmd_str):
            if i >= len(words):
                raise IncompleteCmdServerCommand(cmd) 
            elif words[i] == cmd_str:
                cmd.append(['cmd', cmd_str])
            else:
                raise BadCmdServerCommand(cmd, words[i]) 
        # TODO: add try / except and then handle current application in focus
        if self._is_sending:
            cmd = self.cmdproc_cmd(self._receiving_cmdproc, words)
            self._cmdserver.send_cmd(self._receiving_cmdproc, cmd)
            self.done_sending()
            return
        i = 0
        try:
            consume(i, 'SEND')
            i += 1
        except BadCmdServerCommand:
            try:
                consume(i, 'RECORD')
                i += 1
                macroname = self.ask_for_string('the name of your recording')
                self._cmdserver.record_macro(macroname)
                return
            except BadCmdServerCommand:
                try:
                    consume(i, 'DONE')
                    i += 1
                    self._cmdserver.end_macro()
                    return
                except BadCmdServerCommand:
                    consume(i, 'REPLAY')
                    i += 1
                    macroname = self.ask_for_string('the recording to replay')
                    self._cmdserver.replay_macro(macroname)
                    return
        # TODO: use voice for this
        cmdproc = self.ask_for_string('program to send to')
        if cmdproc not in self._cmdserver._cmdproc_config:
            # self.error("No such program named {cmdproc}".format(**locals()))
            raise BadCmdServerCommand(cmd, cmdproc)
        self.get_ready_to_send(cmdproc)

    def cmdproc_cmd(self, cmdproc, words):
        dfa = self._cmdproc_dfa[cmdproc]
        cmd = []
        for i in range(len(words)):
            w = words[i]
            try:
                result = dfa[(tuple(words[0:i+1]), i)]
                if result[0] == 'cmd':
                    cmd.append(result)
                elif result[0] == 'arg':
                    inputfunc = result[1]
                    cmd.append(inputfunc())
            except KeyError:
                raise BadCmdProcCommand(cmdproc, cmd, w)
        try:
            # process any remaining arguments, or accept
            i = len(words)
            while True:
                result = dfa[(tuple(words), i)]
                if result == 'accept':
                    return cmd
                elif result[0] == 'arg':
                    inputfunc = result[1]
                    cmd.append(inputfunc())
                i += 1
            raise IncompleteCmdProcCommand(cmdproc, cmd) 
        except KeyError:
            raise IncompleteCmdProcCommand(cmdproc, cmd) 

    def _init_dfa(self, cmdproc_cmds):
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
            'pidgin': [ 
                [['cmd', 'REPLY'], ['arg', 'str', 'Message']],
                [['cmd', 'PAUSE']],
                [['cmd', 'VOLUME'], ['arg', int]],
            ],
            ...
        ]

        cmd_delimeters looks like:
        ['SEND', 'clementine', 'VOLUME', 'PLAY', 'PAUSE', 'VOLUME']

        """
        def argtype(cmdarg):
            return cmdarg[0]
        # argfunc = {
        #         'str': 'STR', #self.ask_for_string,
        #         'int': 'INT', #self.ask_for_int,
        #         }
        argfunc = {
                'str': self.ask_for_string,
                'int': self.ask_for_int,
                }
        for cmdproc in cmdproc_cmds.keys():
            cmdproc_dfa = {}
            cmds = cmdproc_cmds[cmdproc]
            # TODO: this scheme doesn't handle multiple states (e.g. TOP LEFT or TOP RIGHT)
            for cmdproc_cmd in cmds:
                cmd_delimeters = []
                for i in range(len(cmdproc_cmd)):
                    cmdarg = cmdproc_cmd[i]
                    if type(cmdarg) == list:
                        if argtype(cmdarg) == 'cmd':
                            # e.g. key = (('PLAY'), 0), value = ['cmd', 'PLAY']
                            # key = (('TOP', 'LEFT'), 1), value = ['cmd', 'LEFT']
                            # key = (('TOP', 'LEFT'), 2), value = 'accept'
                            cmd_delimeters.append(cmdarg[1])
                            cmdproc_dfa[(tuple(cmd_delimeters), i)] = ['cmd', cmdarg[1]]
                        elif argtype(cmdarg) == 'arg':
                            # e.g. for pidgin REPLY: ['arg', self.ask_for_string]
                            # inputfunc = argfunc[cmdarg[1]]
                            description = cmdarg[2]
                            # curry the description and return an arg
                            # inputfunc_wrapper = lambda: ['arg', inputfunc(description)]
                            # inputfunc_wrapper = inputfunc
                            cmdproc_dfa[(tuple(cmd_delimeters), i)] = ['arg', self.wrapped_func(argfunc[cmdarg[1]], description)]
                        else:
                            raise NotImplementedError("Unknown cmdarg {cmdarg}".format(**locals()))
                cmdproc_dfa[(tuple(cmd_delimeters), len(cmdproc_cmd))] = 'accept'
            self._cmdproc_dfa[cmdproc] = cmdproc_dfa
        # Store the results of each transition
        # cmd = []
        # def arg():
        # def cmdproc():
        # def cmd():
        # state = 'cmdserver_or_current_cmdproc'

    def wrapped_func(self, func, description):
        def wrapped():
            return ['arg', func(description)]
        return wrapped
        # inputfunc_wrapper = lambda: ['arg', inputfunc(description)]

    def ask_for_string(self, description):
        string = raw_input("Give me a {description}: ".format(**locals()))
        return string

    def ask_for_int(self, description):
        string = raw_input("Give me a number for {description}: ".format(**locals()))
        return int(string)

    def error(self, message):
        # TODO: use system notification
        logger.info(message)

class BadCmdProcCommand(Exception):
    def __init__(self, cmdproc, cmd_so_far, unexpected):
        message = "Failed to run command for {cmdproc}.  Saw {cmd_so_far}, but didn't expect {unexpected}".format(**locals())
        Exception.__init__(self, message)
        self.cmdproc = cmdproc
        self.cmd_so_far = cmd_so_far
        self.unexpected = unexpected

class BadCmdServerCommand(Exception):
    def __init__(self, cmd_so_far, unexpected):
        message = "Failed to run command for command server.  Saw {cmd_so_far}, but didn't expect {unexpected}".format(**locals())
        Exception.__init__(self, message)
        self.cmd_so_far = cmd_so_far
        self.unexpected = unexpected

class IncompleteCmdProcCommand(Exception):
    def __init__(self, cmdproc, cmd_so_far):
        message = "Failed to run command for {cmdproc}, only saw {cmd_so_far}, but expected more".format(**locals())
        Exception.__init__(self, message)
        self.cmdproc = cmdproc
        self.cmd_so_far = cmd_so_far

class IncompleteCmdServerCommand(Exception):
    def __init__(self, cmd_so_far):
        message = "Failed to run command for command server, saw {cmd_so_far}, but expected more".format(**locals())
        Exception.__init__(self, message)
        self.cmd_so_far = cmd_so_far

if __name__ == '__main__':
    main()
