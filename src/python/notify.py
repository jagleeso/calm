#!/usr/bin/env python
import pynotify
import argparse
import gtk
import time

import procutil

import logging
import logconfig
logger = logging.getLogger(__name__)

class GUINotifier(object):
    """
    Send notifications via system notification bubbles.
    """
    def __init__(self):
        pynotify.init("Why do I need this...")
        self.notice = pynotify.Notification('', '')
        self._icon_cache = {}

        self._timestamp = None
        self._title = None
        self._message = None
        self._icon = None

    def _record_notification(self, timestamp, title, message=None, icon=None):
        if self._timestamp is None or timestamp - self._timestamp > config.NOTIFY_APPEND_TIME:
            self._title = title
            self._message = message
            self._icon = icon
        else:
            # use the same icon and title as before. update the message.
            if self._message is None:
                self._message = self.get_appended_msg(title, message)
            else:
                self._message = self._message + '\n...\n' + self.get_appended_msg(title, message)

    def notify(self, title, message=None, icon=None):
        ts = time.time()
        self._record_notification(ts, title, message, icon)
        # notice = pynotify.Notification(title, message)
        # notice.show()
        msg = get_msg(self._title, self._message)
        logger.info("NOTIFY: %s", msg)
        # import rpdb; rpdb.set_trace()
        # self.notice.update(msg)
        self.notice.update(self._title, self._message)
        if self._icon is not None:
            pixbuf = None
            if self._icon in self._icon_cache:
                pixbuf = self._icon_cache[self._icon]
            else:
                pixbuf = gtk.gdk.pixbuf_new_from_file(self._icon)
            self.notice.set_icon_from_pixbuf(pixbuf)
            if self._icon not in self._icon_cache:
                self._icon_cache[self._icon] = pixbuf
        self.notice.show()
        # don't incur the delay of notification time.  We want the time period to be roughly 
        # the time at which the notification shows up until the next notification arrives 
        # (notify-osd seems sluggish).
        self._timestamp = time.time()

    def get_appended_msg(self, title, message):
        if message is None:
            return title
        elif title == self._title:
            # same title as before, only use the message.
            return message
        else:
            return title + ': ' + message

class TerminalNotifier(object):
    """
    Send notifications via system notification bubbles.
    """
    def __init__(self):
        pass

    def notify(self, title, message=None):
        if message is None:
            logger.info("NOTIFY <%s>", title)
        else:
            logger.info("NOTIFY <%s>: %s", title, message)

def str_or_empty(x):
    if x is None:
        return ''
    return str(x)

def get_msg(title, message):
    return str_or_empty(title) + ': ' + str_or_empty(message)

def notify_send(title, message=None):
    try:
        msg = get_msg(title, message)
        logger.info("NOTIFY-SEND: %s", msg)
        procutil.call(['notify-send', msg])
    except proctuil.WrappedCalledProcessError:
        logger.exception("notify-osd failed")

import message
import config

import select
import socket
import signal
import sys
import errno 

class NotifyServer(object):
    def __init__(self, port, notifier_class):
        self.notifier = notifier_class()
        self.port = port
        # See http://pymotw.com/2/select/
        self.poller = select.poll()
        self.sockets = []
        self.listen_socket = None
        self.fd_to_socket = {}

    def start(self):
        self._init_listen_socket()
        # self._connect_cmdprocs_and_cmdserver()
        self._setup_signal_handler()
        self._main_loop()

    def _init_listen_socket(self):
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.listen_socket.bind((config.DEFAULT_HOST, self.port))
        self.listen_socket.listen(1)
        self._register_socket(self.listen_socket)

    def _main_loop(self):
        try:
            while True:
                logger.info("START POLLING")
                for fd, flag in self.poller.poll():
                    s = self.fd_to_socket[fd]
                    logger.info("POLL EVENT")

                    if flag & (select.POLLIN | select.POLLPRI):
                        if s is self.listen_socket:
                            # New incoming connection
                            logger.info("New connection")
                            self._accept_new_connection()
                            continue
                        notification = message.recv_notification(s)
                        self.notifier.notify(*notification[1:])
                    elif flag & select.POLLHUP:
                        logger.info("Subscriber hung up")
                        self._remove_socket(s)
                    elif flag & select.POLLERR:
                        logger.info("Error on subscriber socket")
                        self._remove_socket(s)
                    continue
        except select.error as e:
            err = e.args[0]
            if err != errno.EINTR:
                raise e

    def _exit(self, signum, frame):
        logger.info("Got a shutdown signal; close subscriber connections")
        for s in self.sockets:
            self._remove_socket(s)
        self.listen_socket.close()
        logger.info("Exiting notification server")

    def _setup_signal_handler(self):
        f = self._exit
        signal.signal(signal.SIGINT, f)
        signal.signal(signal.SIGTERM, f)
        signal.signal(signal.SIGHUP, f)

    # def _connect_cmdprocs_and_cmdserver()

    #     # listen for connections until everyone connects (all cmdprocs and cmdserver)
    #     self.fd_to_socket = {}
    #     subscribers = [c.config['program'] for c in [config.CMD_SERVER] + config.CMD_PROCS]
    #     for i in range(len(subscribers)):
    #         self.listen_socket.listen(1)
    #         self._accept_new_connection()

    #     # registers all the sockets for poll-ing 
    #     for s in self.sockets:
    #         self.poller.register(s, select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR)

    def _remove_socket(self, s):
        del self.fd_to_socket[s.fileno()]
        self.sockets.remove(s)
        self.poller.unregister(s)
        s.close()

    def _register_socket(self, s):
        self.poller.register(s, select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR)
        self.fd_to_socket[s.fileno()] = s

    def _accept_new_connection(self):
        (s, address) = self.listen_socket.accept()
        self._register_socket(s)
        self.sockets.append(s)
        self.listen_socket.listen(1)

def notify_server_connection(notify_server, notify_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((notify_server, notify_port))
    except:
        s.close()
        raise
    return s

def notify_server(self, title, msg=None, icon=None):
    message.send_notification(self.notify_socket, ['notification', title, msg, icon])

def notify_server_func(notify_socket, title, msg=None, icon=None):
    message.send_notification(notify_socket, ['notification', title, msg, icon])

def main():
    parser = argparse.ArgumentParser(description="Notification server (listen for notifications then publish them)")
    parser.add_argument('--port', type=int, default=config.DEFAULT_NOTIFY_PORT)
    parser.add_argument('--type', required=True)
    type_to_notifier = {
            'gui': GUINotifier,
            'terminal': TerminalNotifier,
            }
    args = parser.parse_args()

    if args.type not in type_to_notifier:
        sys.stderr.write("No such notifier type {type}\n".format(type=args.type))
        sys.exit(1)

    notify_server = NotifyServer(args.port, type_to_notifier[args.type])
    notify_server.start()

if __name__ == '__main__':
    main()
