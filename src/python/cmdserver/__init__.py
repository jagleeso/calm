from message import *
import argparse
import os
import sys
import socket
# http://victorlin.me/posts/2012/08/good-logging-practice-in-python/
import logging
import signal
import traceback
import errno 
import time
import os

from cmdproc import window, extract_cmds

import config
import notify

import logconfig
logger = logging.getLogger(__name__)

from threading import Thread

class TerminalInputHandler(object):
    def __init__(self):
        pass

    def ask_for_string(self, description, candidates, callback):
        if candidates is None:
            candidates = []
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
            [['cmd', 'REPLAY'], ['arg', 'str', "Recorded macro name"]],
            [['cmd', 'RECORD'], ['arg', 'str', "New macro name"]],
            [['cmd', 'FINISH'], ['cmd', 'MACRO']],
            [['cmd', 'SEND'], ['arg', 'str'], ['cmdproc', 1]],
            [['cmd', 'FINISH'], ['cmd', 'SENDING']],
            [['cmd', 'UNDO']],
            [['cmd', 'WAKEUP'], ['cmd', 'CALM']],
            [['cmd', 'SLEEP']],
            [['cmd', 'TALK'], ['arg', 'str'], ['cmdproc', 1]],
            [['cmd', 'FINISH'], ['cmd', 'TALKING']],
            [['cmd', 'HELP']],
        ],
        'icon': os.path.join(config.IMG, 'calm.svg'),
    }
    """
    Spawn cmdprocs and send them sockets to listen to messages on, and register their 
    names with the sockets

    cmdprocs:
    a list of paths to execute
    """
    def __init__(self, notifier_path, cmdproc_paths, port):
        self.port = port
        self.cmdproc_paths = cmdproc_paths

        self._cmdproc_config = {}
        self._program_to_socket = {}
        self._program_to_pid = {}

        self.macros = set([])
        self._macro_cmd_receiver = []

        self._is_talking = False
        self._is_sending = False
        self.is_recording = False
        self.current_macro = None

        self.notifier = 'gui'
        self.notifier_path = notifier_path

        self.listening = False

        self._receiving_cmdproc = None
        self._prev_receiving_cmdproc = None

    def sleep(self):
        self.listening = False
        self.notify_server("Going to sleep...", 'WAKEUP CALM to resume')

    def wakeup(self):
        self.listening = True 
        self.notify_server("Ready for commands")

    def start(self):
        raise NotImplementedError

    def send_cmd(self, program, cmd):
        cmdproc_socket = self._program_to_socket[program]
        send_cmd(cmdproc_socket, cmd)
        if self.is_recording:
            response = recv_response(cmdproc_socket)
            if response == ['response', 'recorded']:
                # The command processor recorded the command; keep track of this for UNDO's
                self._macro_cmd_receiver.insert(0, program)
            else:
                assert response == ['response', 'not recorded']

    def get_candidates(self, program, request):
        cmdproc_socket = self._program_to_socket[program]
        send_request(cmdproc_socket, request)
        candidates = recv_candidates(cmdproc_socket)
        return candidates

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
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.bind((host, self.port))

    def startup_procs(self):
        self.startup_notify_server()
        self.startup_cmdprocs()
        self.notify_server('Calm is ready', 'Say WAKEUP CALM to get started')

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
        setup_signal_handler(self._program_to_pid.values() + [self.notify_server_pid])

        self._cmd_dfa = CmdDFA(self, cmdproc_cmds)

    def startup_notify_server(self):
        (s, pid) = fork_notify_server(self.notifier_path, self.notifier, config.DEFAULT_NOTIFY_PORT)
        self.notify_socket = s 
        self.notify_server_pid = pid

    def notify_server(self, *args, **kwargs):
        kwargs['icon'] = self.config['icon']
        return notify.notify_server(self, *args, **kwargs)

    def notify_server_for_cmdproc(self, cmdproc, *args, **kwargs):
        kwargs['icon'] = self._cmdproc_config[cmdproc]['icon']
        return notify.notify_server(self, *args, **kwargs)

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
        self.current_macro = name
        self.macros.add(name)
        self.notify_server("Recording macro", name)
        return True

    def replay_macro(self, name):
        """
        Tell the command processors to replay macro.
        """
        if name not in self.macros:
            return
        self.notify_server("Replaying macro", name)
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
            if self._macro_cmd_receiver == []:
                # The user recorded an empty macro, ignore it.
                self.macros.remove(self.current_macro)
                self.notify_server("Nothing recorded for macro", self.current_macro)
            else:
                self.notify_server("Finished recording macro", self.current_macro)
        self.is_recording = False
        self.current_macro = None
        self._macro_cmd_receiver = []

    def undo_last_cmd(self):
        assert self.is_recording
        if self._macro_cmd_receiver == []:
            return
        last_receiver = self._macro_cmd_receiver.pop()
        socket = self._program_to_socket[last_receiver]
        send_cmd(socket, [['cmd', 'UNDO']])

    def setup_dispatch_loop(self):
        def cmd_string_cb(cmd_string):
            if cmd_string is None:
                handle_next_cmd()
                return
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
            # logger.info("asking_for_input == %s, cmd_dfa == %s", self._cmd_dfa._asking_for_input, self._cmd_dfa)
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
            if type(e) == BadCmdProcCommandInput:
                # import rpdb; rpdb.set_trace()
                cmd_str = ' '.join(cmdarg[1] for cmdarg in e.cmd_so_far)
                self.notify_server_for_cmdproc(e.cmdproc,
                        "Bad input for {cmd_str}:".format(**locals()), 
                        "expected {descr}".format(descr=e.arg_description.lower()))
            callback()
        self._cmd_dfa.cmd(cmd_strs, callback, err)

    def cmd_help(self):
        def config_to_cmd_str(cmds):
            return ', '.join(sorted(
                ' '.join(cmd_delims) for cmd_delims in cmds))

        cmdserver_cmds = None
        if self._is_sending:
            cmdserver_cmds = [
                    ['WAKEUP', 'CALM'],
                    ['FINISH', 'SENDING'],
                    ['SLEEP'],
                    ['HELP'],
                    ]
        else:
            cmdserver_cmds = extract_cmds(self.config['commands'])
            cmdserver_cmds.remove(['FINISH', 'SENDING'])
            if not self._is_talking:
                cmdserver_cmds.remove(['FINISH', 'TALKING'])

            if self.is_recording:
                cmdserver_cmds.remove(['RECORD'])
            else:
                cmdserver_cmds.remove(['FINISH', 'MACRO'])
                cmdserver_cmds.remove(['UNDO'])
        server_str = config_to_cmd_str(cmdserver_cmds)

        current_cmdproc = None
        if self._is_sending or self._is_talking:
            current_cmdproc = self._receiving_cmdproc
        else:
            current_program = window.get_current_program()
            if current_program in self._cmdproc_config:
                current_cmdproc = current_program

        if current_cmdproc is None:
            self.notify_server('Commands', server_str)
        else:
            cmdproc_cmds = extract_cmds(self._cmdproc_config[current_cmdproc]['commands'])
            cmdproc_str = config_to_cmd_str(cmdproc_cmds)
            self.notify_server_for_cmdproc(
                    current_cmdproc,
                    'Commands for {program}:'.format(program=current_cmdproc), 
                    cmdproc_str + '\n...\n' + server_str)

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
    parser.add_argument('--port', type=int, default=config.DEFAULT_CMDSERVER_PORT)
    parser.add_argument('--notifier', required=True)
    return parser

def cmdserver_main(cmdserver_class, parser=None):
    parser = cmdserver_arg_parser(parser)
    args = parser.parse_args()

    cmdserver = cmdserver_class(args.notifier, args.cmdproc_paths, args.port)

    return (args, cmdserver)

_PIDS = None
def exit_cmdserver(signum, frame):
    signal.signal(signal.SIGINT, _ORIGINAL_SIGINT)
    signal.signal(signal.SIGTERM, _ORIGINAL_SIGTERM)
    signal.signal(signal.SIGHUP, _ORIGINAL_SIGHUP)
    exit_server()

def exit_server():
    logger.info("Terminating command server, command server processes, and notification server (%s)...", _PIDS)
    if _PIDS is not None:
        for pid in _PIDS:
            os.kill(pid, signal.SIGTERM)
    sys.exit()

_ORIGINAL_SIGINT = signal.getsignal(signal.SIGINT)
_ORIGINAL_SIGTERM = signal.getsignal(signal.SIGTERM)
_ORIGINAL_SIGHUP = signal.getsignal(signal.SIGHUP)
def setup_signal_handler(cmdproc_pids):
    global _PIDS
    _PIDS = cmdproc_pids
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

def fork_notify_server(notifier_path, notifier_type, notifier_port):
    try:
        pid = os.fork()
    except OSError, e:
        sys.exit(1)
    if pid == 0:
        os.execv(notifier_path, [notifier_path, '--type', notifier_type, '--port', str(notifier_port)])
    while True:
        try: 
            notifier_socket = notify.notify_server_connection(config.DEFAULT_HOST, notifier_port)
            break
        except (OSError, socket.error) as e:
            if e.errno != errno.ECONNREFUSED:
                raise
        time.sleep(config.NOTIFY_CONNECT_RETRY_TIMEOUT)

            
    logger.info("%s notify server \"%s\" (PID: %s) connected", notifier_type, notifier_path, pid)
    return (notifier_socket, pid)

class CmdDFA(object):
    def __init__(self, cmdserver, cmdproc_cmds):
        self._cmdserver = cmdserver
        self._cmdproc_dfa = {}
        self._cmdproc_argspecs = {}
        self._init_dfa(cmdproc_cmds)

        # default input handler
        self._string_input_handler = TerminalInputHandler()
        self._asking_for_input = False

        self._is_sending = False
        self._talking_to_cmdproc = False

    def get_ready_to_send(self, cmdproc):
        self._is_sending = True
        self._cmdserver._is_sending = True
        # The previous receiving command proc should only be None if we are not talking to a command 
        # proc.
        assert not self._talking_to_cmdproc or self._cmdserver._prev_receiving_cmdproc is None
        self._cmdserver._prev_receiving_cmdproc = self._cmdserver._receiving_cmdproc
        self._cmdserver._receiving_cmdproc = cmdproc

    def done_sending(self):
        self._is_sending = False
        self._cmdserver._is_sending = False
        self._cmdserver._receiving_cmdproc = self._cmdserver._prev_receiving_cmdproc 
        self._cmdserver._prev_receiving_cmdproc = None

        # If we were talking before we sent this command, remind the user of the mode switch
        if self._cmdserver._is_talking:
            self._cmdserver.notify_server_for_cmdproc(
                    self._cmdserver._receiving_cmdproc,
                    "Talking to {cmdproc} again".format(cmdproc=self._cmdserver._receiving_cmdproc))

    def get_ready_to_talk(self, cmdproc):
        self._talking_to_cmdproc = True 
        self._cmdserver._is_talking = True
        assert self._cmdserver._prev_receiving_cmdproc is None
        self._cmdserver._receiving_cmdproc = cmdproc
        self._cmdserver.notify_server_for_cmdproc(
                self._cmdserver._receiving_cmdproc,
                "Talking to {cmdproc}".format(cmdproc=self._cmdserver._receiving_cmdproc))

    def done_talking(self, cmdproc):
        self._talking_to_cmdproc = False
        self._cmdserver._is_talking = False
        self._cmdserver.notify_server("Finished talking to {cmdproc}".format(cmdproc=self._cmdserver._receiving_cmdproc))
        self._cmdserver._receiving_cmdproc = None 

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

        def is_cmd(*cmd_strs):
            if words[0:len(cmd_strs)] == list(cmd_strs):
                for cmd_str in cmd_strs:
                    cmd.append(['cmd', cmd_str])
                return True
            return False

        if not self._cmdserver.listening:
            if is_cmd('WAKEUP', 'CALM'):
                self._cmdserver.wakeup()
                callback()
                return
            else:
                # We're ignoring input since we're sleeping
                callback()
                return
        elif is_cmd('SLEEP'):
            self._cmdserver.sleep()
            callback()
            return
        elif is_cmd('HELP'):
            self._cmdserver.cmd_help()
            callback()
            return

        # TODO: add try / except and then handle current application in focus
        # logger.info("is sending?? %s", self._is_sending)
        if self._is_sending:
            if is_cmd('FINISH', 'SENDING'):
                self.done_sending()
                callback()
                return
            def send_cmd_cb(cmd):
                self._cmdserver.send_cmd(self._cmdserver._receiving_cmdproc, cmd)
                self.done_sending()
                callback()
            self.cmdproc_cmd(self._cmdserver._receiving_cmdproc, words, send_cmd_cb, err)
            return

        if len(words) < 1:
            err(IncompleteCmdServerCommand(cmd))
            return

        def ask_for_program(cb):
            # TODO: use voice for this
            def get_ready_to_send_cb(cmdproc):
                # logger.info("send to... %s", cmdproc)
                if cmdproc not in self._cmdserver._cmdproc_config:
                    # self.error("No such program named {cmdproc}".format(**locals()))
                    # raise BadCmdServerCommand(cmd, cmdproc)
                    err(BadCmdServerCommand(cmd, cmdproc))
                    return
                cb(cmdproc)
            self.ask_for_string('program to send to', get_ready_to_send_cb, self._cmdserver._cmdproc_config.keys())

        if is_cmd('TALK'):
            def talk_to_cb(cmdproc):
                if self._talking_to_cmdproc:
                    # We're already talking to a cmdproc; switch to talking to this cmdproc
                    self.done_talking(self._cmdserver._receiving_cmdproc)
                self.get_ready_to_talk(cmdproc)
                callback()
            ask_for_program(talk_to_cb)
            return
        elif is_cmd('FINISH', 'TALKING'):
            if self._talking_to_cmdproc:
                self.done_talking(self._cmdserver._receiving_cmdproc)
            callback()
            return
        elif is_cmd('SEND'):
            def send_cb(cmdproc):
                self.get_ready_to_send(cmdproc)
                callback()
            ask_for_program(send_cb)
            return
        elif is_cmd('RECORD'):
            def start_recording_cb(macroname):
                if macroname is not None:
                    self._cmdserver.record_macro(macroname)
                callback()
            self.ask_for_string('the name of your recording', start_recording_cb, self._cmdserver.macros)
            return
        elif is_cmd('FINISH', 'MACRO'):
            self._cmdserver.end_macro()
            callback()
            return
        elif is_cmd('REPLAY'):
            def replay_macro_cb(macroname):
                self._cmdserver.replay_macro(macroname)
                callback()
            self.ask_for_string('the recording to replay', replay_macro_cb, self._cmdserver.macros)
            return
        elif is_cmd('UNDO'):
            if self._cmdserver.is_recording:
                self._cmdserver.undo_last_cmd()
            callback()
            return

        def send_cmd_to_cmdproc(cmdproc):
            """
            Sending a command to a command processor (either the current application, or an application 
            we're talking to).
            """
            def send_cmd_cb(cmd):
                self._cmdserver.send_cmd(cmdproc, cmd)
                callback()
            def cmdproc_and_cmdserver_err(e):
                if type(e) == BadCmdProcCommandInput:
                    err(e)
                else:
                    err(NeitherCmdProcOrServerCommand(e, BadCmdServerCommand(cmd, words[0])))
            self.cmdproc_cmd(cmdproc, words, send_cmd_cb, cmdproc_and_cmdserver_err)

        # See if we're talking to a specific command processor
        if self._talking_to_cmdproc:
            send_cmd_to_cmdproc(self._cmdserver._receiving_cmdproc)
            return

        # Try sending the command to the currently active process to see if it can handle it.
        current_cmdproc = window.get_current_program()
        if current_cmdproc is None:
            # Current active process has no command processor; interpret as a bad server command.
            err(BadCmdServerCommand(cmd, words[0]))
            return
        send_cmd_to_cmdproc(current_cmdproc)
        return

    def cmdproc_cmd(self, cmdproc, words, cmd_callback, err):
        try:
            dfa = self._cmdproc_dfa[cmdproc]
            argspecs = self._cmdproc_argspecs[cmdproc]
        except KeyError:
            err(NoSuchCmdProc(cmdproc, words))
            return
        cmd = []
        i = 0
        self._resume_cmdproc_cmd(cmdproc, cmd_callback, err, words, i, cmd, dfa, argspecs)

    def _resume_cmdproc_cmd(self, cmdproc, cmd_callback, err, words, i, cmd, dfa, argspecs):
        """
        Call cmd_callback with the command  when we're done handling the command, or call err 
        with and exception if the command is bad.
        """
        def arg_description(argcmd):
            if len(argcmd) == 4:
                return argcmd[3]
            else:
                return argcmd[2]
        def handle_arg(argspec, result, i):
            def arg_cb(arg):
                if isinstance(arg, ValueError):
                    err(BadCmdProcCommandInput(cmdproc, cmd, w, arg_description(argspec)))
                else:
                    cmd.append(arg)
                    self._resume_cmdproc_cmd(cmdproc, cmd_callback, err, words, i + 1, cmd, dfa, argspecs)
            inputfunc = result[1]
            request = ['request', [words[0:i+1], i]]
            candidates = self._cmdserver.get_candidates(cmdproc, request)
            if candidates is None:
                inputfunc(arg_cb)
            else:
                inputfunc(arg_cb, candidates[1])
        while i < len(words):
            w = words[i]
            try:
                result = dfa[(tuple(words[0:i+1]), i)]
                if result[0] == 'cmd':
                    cmd.append(result)
                elif result[0] == 'arg':
                    argspec = argspecs[(tuple(words[0:i+1]), i)]
                    handle_arg(argspec, result, i)
                    return
                i += 1
            except KeyError:
                err(BadCmdProcCommand(cmdproc, cmd, w))
                return
        try:
            # process any remaining arguments, or accept
            while True:
                result = dfa[(tuple(words), i)]
                if result == 'accept':
                    cmd_callback(cmd)
                    return
                    # return cmd
                elif result[0] == 'arg':
                    argspec = argspecs[(tuple(words[0:i+1]), i)]
                    handle_arg(argspec, result, i)
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
                [['cmd', 'RESPOND'], ['arg', 'str', 'Message']],
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
        argfunc = {
                'str': self.ask_for_string,
                'int': self.ask_for_int,
                }
        for cmdproc in cmdproc_cmds.keys():
            cmdproc_dfa = {}
            cmdproc_argspecs = {}
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
                            # e.g. for pidgin RESPOND: ['arg', self.ask_for_string]
                            # inputfunc = argfunc[cmdarg[1]]
                            description = cmdarg[2]
                            # curry the description and return an arg
                            # inputfunc_wrapper = lambda: ['arg', inputfunc(description)]
                            # inputfunc_wrapper = inputfunc
                            cmdproc_dfa[(tuple(cmd_delimeters), i)] = ['arg', self.wrapped_func(argfunc[cmdarg[1]], description)]
                            cmdproc_argspecs[(tuple(cmd_delimeters), i)] = cmdarg
                        else:
                            raise NotImplementedError("Unknown cmdarg {cmdarg}".format(**locals()))
                cmdproc_dfa[(tuple(cmd_delimeters), len(cmdproc_cmd))] = 'accept'
            self._cmdproc_dfa[cmdproc] = cmdproc_dfa
            self._cmdproc_argspecs[cmdproc] = cmdproc_argspecs

    def wrapped_func(self, func, description):
        def get_input(arg_cb, candidates=[]):
            def wrapped_arg_cb(user_input):
                if isinstance(user_input, Exception):
                    return arg_cb(user_input)
                else:
                    return arg_cb(['arg', user_input])
            return func(description, wrapped_arg_cb, candidates)
        return get_input

    def _stop_asking_wrapper(self, callback):
        def stop_asking_wrapper(x):
            self._asking_for_input = False
            result = callback(x)
            return result
        return stop_asking_wrapper

    def ask_for_string(self, description, callback, candidates=[]):
        assert not self._asking_for_input
        self._asking_for_input = True
        self._string_input_handler.ask_for_string(description, list(candidates) if candidates is not None else None, self._stop_asking_wrapper(callback))

    def ask_for_int(self, description, callback, candidates=[]):
        assert not self._asking_for_input
        self._asking_for_input = True
        def int_callback_wrapper(string):
            try:
                integer = int(string)
                return callback(integer)
            except ValueError as e:
                return callback(e)
        self._string_input_handler.ask_for_string(description, list(candidates) if candidates is not None else None, self._stop_asking_wrapper(int_callback_wrapper))

class NeitherCmdProcOrServerCommand(Exception):
    def __init__(self, cmdproc_exception, cmdserver_exception):
        indent = "    "
        message = (
            "First failed to parse command in command sever, then failed to parse in current command processor:\n" +
            indent + "Command server attempt:\n" +
            2*indent + str(cmdserver_exception) + "\n" +
            indent + "Command processor attempt:\n" +
            2*indent + str(cmdproc_exception)
        )
        Exception.__init__(self, message)

class BadCmdProcCommand(Exception):
    def __init__(self, cmdproc, cmd_so_far, unexpected):
        message = "Failed to run command for {cmdproc}.  Saw {cmd_so_far}, but didn't expect {unexpected}".format(**locals())
        Exception.__init__(self, message)
        self.cmdproc = cmdproc
        self.cmd_so_far = cmd_so_far
        self.unexpected = unexpected

class BadCmdProcCommandInput(Exception):
    def __init__(self, cmdproc, cmd_so_far, unexpected, arg_description):
        message = "Failed to run command for {cmdproc}.  Saw {cmd_so_far}, but didn't expect {unexpected} (type should be {arg_description})".format(**locals())
        Exception.__init__(self, message)
        self.cmdproc = cmdproc
        self.cmd_so_far = cmd_so_far
        self.unexpected = unexpected
        self.arg_description = arg_description

class NoSuchCmdProc(Exception):
    def __init__(self, cmdproc, words):
        message = "No command processor exists for the program {cmdproc} (for handling {words})".format(**locals())
        Exception.__init__(self, message)
        self.cmdproc = cmdproc
        self.words = words

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
