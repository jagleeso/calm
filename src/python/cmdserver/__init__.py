from message import *
import argparse
import os
import sys
import socket
# http://victorlin.me/posts/2012/08/good-logging-practice-in-python/
import logging
import signal
import traceback

DEFAULT_CMDSERVER_PORT = 2525

import logconfig
logger = logging.getLogger(__name__)

from threading import Thread

class TerminalInputHandler(object):
    def __init__(self):
        pass

    def ask_for_string(self, description, candidates, callback):
        candidates_str = ", ".join(candidates)
        help_str = "" if candidates == [] else " (one of: {candidates_str})".format(**locals())
        def get_a_string():
            string = raw_input("Give me a {description}{help_str}: ".format(description=description, help_str=help_str))
            callback(string)
        t = Thread(target=get_a_string)
        t.start()

class CmdServer(object):
    config = {
        'program': 'cmdserver',
        'commands': [ 
            [['cmd', 'REPLAY'], ['arg', 'str']],
            [['cmd', 'RECORD'], ['arg', 'str']],
            [['cmd', 'FINISH']],
            [['cmd', 'SEND'], ['arg', 'str'], ['cmdproc', 1]],
        ],
    }
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

        self.macros = []

        self.is_recording = False

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
        logger.info("HELLO")
        host = 'localhost'
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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
                    send_cmd(socket, [['cmd', 'FINISH']])
                self.is_recording = False
                return False
        self.is_recording = True
        self.macros.append(name)
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
        if self.is_recording: 
            for socket in self._program_to_socket.values():
                send_cmd(socket, [['cmd', 'FINISH']])
        self.is_recording = False

    def setup_dispatch_loop(self):
        def cmd_string_cb(cmd_string):
            if cmd_string.lower() in ['quit', 'exit']:
                cmdserver.exit_server()
            if self._cmd_dfa._asking_for_input:
                logger.info("We're asking the user for input, hold off on commands for now...")
                return
            else:
                cmd = cmd_string.split()
                self.dispatch_cmd_to_cmdproc(cmd, handle_next_cmd)
                # handle_next_cmd(cmd_string_cb)
        def handle_next_cmd():
            logger.info("asking_for_input == %s, cmd_dfa == %s", self._cmd_dfa._asking_for_input, self._cmd_dfa)
            self._cmd_dfa.ask_for_string("command", cmd_string_cb, [c[1] for c in self.config['commands'] if c[0] == 'cmd'])
        handle_next_cmd()

    def dispatch_cmd_to_cmdproc(self, cmd_strs, callback):
        def err(e):
            # (cmdserver.IncompleteCmdProcCommand, cmdserver.BadCmdProcCommand, 
            # cmdserver.IncompleteCmdServerCommand, cmdserver.BadCmdServerCommand)
            try:
                # hack to get the stacktrace
                raise e
            except:
                pass
            logger.exception(e.message)
            callback()
        self._cmd_dfa.cmd(cmd_strs, callback, err)

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

        # default input handler
        self._string_input_handler = TerminalInputHandler()
        self._asking_for_input = False

        self._is_sending = False
        self._receiving_cmdproc = None

    def get_ready_to_send(self, cmdproc):
        self._is_sending = True
        self._receiving_cmdproc = cmdproc

    def done_sending(self):
        self._is_sending = False
        self._receiving_cmdproc = None 

    def cmd(self, words, callback, err):
        """
        Interpret a command for the server or the current in focus application.

        Call callback when we're ready to handle the next command.

        When receiving a bad command, an exception will be called as an argument to err.
        """
        if self._asking_for_input:
            logger.info("We're asking the user for input, hold off on commands for now...")
            return
        cmd = []
        def consume(i, cmd_str):
            if i >= len(words):
                err(IncompleteCmdServerCommand(cmd))
                return
            elif words[i] == cmd_str:
                cmd.append(['cmd', cmd_str])
            else:
                # TODO: wrong, shouldn't call err here (unless last command tried)
                err(BadCmdServerCommand(cmd, words[i]))
                return
        # TODO: add try / except and then handle current application in focus
        logger.info("is sending?? %s", self._is_sending)
        if self._is_sending:
            def send_cmd_cb(cmd):
                self._cmdserver.send_cmd(self._receiving_cmdproc, cmd)
                self.done_sending()
                callback()
            cmd = self.cmdproc_cmd(self._receiving_cmdproc, words, send_cmd_cb, err)
            return

        def is_cmd(cmd_str):
            if words[0] == cmd_str:
                cmd.append(['cmd', cmd_str])
                return True
            return False

        if len(words) < 1:
            err(IncompleteCmdServerCommand(cmd))
            return
        elif is_cmd('SEND'):
            # TODO: use voice for this
            def get_ready_to_send_cb(cmdproc):
                logger.info("send to... %s", cmdproc)
                if cmdproc not in self._cmdserver._cmdproc_config:
                    # self.error("No such program named {cmdproc}".format(**locals()))
                    # raise BadCmdServerCommand(cmd, cmdproc)
                    err(BadCmdServerCommand(cmd, cmdproc))
                    return
                self.get_ready_to_send(cmdproc)
                callback()
            self.ask_for_string('program to send to', get_ready_to_send_cb, self._cmdserver._cmdproc_config.keys())
        elif is_cmd('RECORD'):
            def start_recording_cb(macroname):
                self._cmdserver.record_macro(macroname)
                callback()
            self.ask_for_string('the name of your recording', start_recording_cb, self._cmdserver.macros)
            return
        elif is_cmd('FINISH'):
            self._cmdserver.end_macro()
            callback()
            return
        elif is_cmd('REPLAY'):
            def replay_macro_cb(macroname):
                self._cmdserver.replay_macro(macroname)
                callback()
            self.ask_for_string('the recording to replay', replay_macro_cb, self._cmdserver.macros)
            return
        else:
            err(BadCmdServerCommand(cmd, words[0]))
            return

    def cmdproc_cmd(self, cmdproc, words, cmd_callback, err):
        dfa = self._cmdproc_dfa[cmdproc]
        cmd = []
        i = 0
        self._resume_cmdproc_cmd(cmdproc, cmd_callback, err, words, i, cmd, dfa)

        # for i in range(len(words)):
        #     w = words[i]
        #     try:
        #         result = dfa[(tuple(words[0:i+1]), i)]
        #         if result[0] == 'cmd':
        #             cmd.append(result)
        #         elif result[0] == 'arg':
        #             inputfunc = result[1]
        #             cmd.append(inputfunc())
        #     except KeyError:
        #         raise BadCmdProcCommand(cmdproc, cmd, w)
        # try:
        #     # process any remaining arguments, or accept
        #     i = len(words)
        #     while True:
        #         result = dfa[(tuple(words), i)]
        #         if result == 'accept':
        #             return cmd
        #         elif result[0] == 'arg':
        #             inputfunc = result[1]
        #             cmd.append(inputfunc())
        #         i += 1
        #     raise IncompleteCmdProcCommand(cmdproc, cmd) 
        # except KeyError:
        #     raise IncompleteCmdProcCommand(cmdproc, cmd) 

    def _resume_cmdproc_cmd(self, cmdproc, cmd_callback, err, words, i, cmd, dfa):
        """
        Call cmd_callback with the command  when we're done handling the command, or call err 
        with and exception if the command is bad.
        """
        # for i in range(len(words)):
        while i < len(words):
            w = words[i]
            try:
                result = dfa[(tuple(words[0:i+1]), i)]
                if result[0] == 'cmd':
                    cmd.append(result)
                elif result[0] == 'arg':
                    inputfunc = result[1]
                    def arg_cb(arg):
                        cmd.append(arg)
                        self._resume_cmdproc_cmd(cmdproc, cmd_callback, err, words, i + 1, cmd, dfa)
                    inputfunc(arg_cb)
                    return
                i += 1
            except KeyError:
                err(BadCmdProcCommand(cmdproc, cmd, w))
                return
        try:
            # process any remaining arguments, or accept
            # i = len(words)
            while True:
                result = dfa[(tuple(words), i)]
                if result == 'accept':
                    cmd_callback(cmd)
                    return
                    # return cmd
                elif result[0] == 'arg':
                    inputfunc = result[1]
                    def arg_cb(arg):
                        cmd.append(arg)
                        self._resume_cmdproc_cmd(cmdproc, cmd_callback, err, words, i + 1, cmd, dfa)
                    inputfunc(arg_cb)
                    return
                i += 1
        except KeyError:
            err(IncompleteCmdProcCommand(cmdproc, cmd))
            return
        err(IncompleteCmdProcCommand(cmdproc, cmd))
        return

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
        def get_input(arg_cb):
            # TODO: make candidates passable as extra argument to get_input
            def wrapped_arg_cb(user_input):
                return arg_cb(['arg', user_input])
            # TODO: pass candidates here
            return func(description, wrapped_arg_cb)
        # TODO: add candidates
        return get_input
        # inputfunc_wrapper = lambda: ['arg', inputfunc(description)]

    def _stop_asking_wrapper(self, callback):
        def stop_asking_wrapper(x):
            self._asking_for_input = False
            logger.info("STOP ASKING: _asking_for_input == %s, cmd_dfa == %s", self._asking_for_input, self)
            result = callback(x)
            return result
        return stop_asking_wrapper

    def ask_for_string(self, description, callback, candidiates=[]):
        assert not self._asking_for_input
        self._asking_for_input = True
        logger.info("START ASKING: _asking_for_input = %s", self._asking_for_input)
        self._string_input_handler.ask_for_string(description, candidiates, self._stop_asking_wrapper(callback))
        # string = raw_input("Give me a {description}: ".format(**locals()))
        # return string

    def ask_for_int(self, description, callback, candidiates=[]):
        assert not self._asking_for_input
        self._asking_for_input = True
        def int_callback_wrapper(string):
            integer = int(string)
            return callback(integer)
        self._string_input_handler.ask_for_string(description, candidiates, self._stop_asking_wrapper(int_callback_wrapper))
        # string = raw_input("Give me a number for {description}: ".format(**locals()))
        # return int(string)

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
