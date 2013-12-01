#!/usr/bin/env python
import cmdproc
import mydbus
from message import *

# https://developer.pidgin.im/wiki/DbusHowto
# provide asynchronous 
import dbus
import re
import gobject
import argparse
from dbus.mainloop.glib import DBusGMainLoop
import logging
import subprocess
import notify
import config

from multiprocessing import Process, Lock, Array, Value
from threading import Thread

import logconfig
logger = logging.getLogger(__name__)

def default_handler(cmdproc, notify_socket, cmdserver_socket, *args):
    logger.info("ACTIVITY on %s: %s", cmdproc, args)
    old_cmdproc = _focussed_cmdproc.value

    # if old_cmdproc != cmdproc:
    _focussed_cmdproc.value = cmdproc
    logger.info("ACTIVITY switch to %s", cmdproc)
    send_focus(cmdserver_socket, ['focus', cmdproc])

    return cmdproc

dbus_signal_handlers = {
        'pidgin': {
            'dbus_interface': 'im.pidgin.purple.PurpleInterface',
            'signals': [
                'ReceivedImMsg',
                'ConversationCreated',
                ],
            'handler': default_handler,
            },
        'clementine': {
            'dbus_interface': 'org.freedesktop.MediaPlayer',
            'signals': [
                # TODO add play, pause, and stop handlers
                'TrackChange',
                ],
            'handler': default_handler,
            },
        }

def wrapped_handler(handler, cmdproc, notify_socket, cmdserver_socket):
    def _wrapped(*args):
        return handler(cmdproc, notify_socket, cmdserver_socket, *args)
    return _wrapped

def setup_dbus_handlers(cmdproc_handlers, notify_socket, cmdserver_socket):
    """
    Spawn a separate thread that listens for dbus events. 
    """
    logger.info("Setting up dbus handlers...")
    def setup():
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()

        for cmdproc in cmdproc_handlers.keys():
            dbus_info = cmdproc_handlers[cmdproc]
            interface = dbus_info['dbus_interface']
            handler = dbus_info['handler']
            for signal in dbus_info['signals']:
                bus.add_signal_receiver(wrapped_handler(handler, cmdproc, notify_socket, cmdserver_socket),
                                        dbus_interface=interface,
                                        signal_name=signal)

        loop = gobject.MainLoop()
        logger.info("Run the loop....")
        loop.run()
        logger.info("Running")
    dbus.mainloop.glib.threads_init()
    setup()
    # dbus_thread = Process(target=setup)
    # logger.info("Start DBUS thread....")
    # dbus_thread.start()
    logger.info("Started.")

_focussed_cmdproc = Array('c', 1024, lock=True)

def get_focussed_cmdproc():
    cmdproc = _focussed_cmdproc.value
    if cmdproc is '':
        return None
    return cmdproc

def start_listening(host, port):
    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    listen_socket.bind((host, port))
    listen_socket.listen(1)
    (s, address) = listen_socket.accept()
    listen_socket.close()
    logger.info("Context server connected to command server")
    setup_dbus_handlers(dbus_signal_handlers, None, s)

def context_server_connection(context_server, context_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((context_server, context_port))
    except:
        s.close()
        raise
    return s

def main():
    parser = argparse.ArgumentParser(description="A context sensor.")
    args = cmdproc.cmdserver_args(parser)
    start_listening(config.DEFAULT_HOST, config.DEFAULT_CONTEXT_PORT)
        
if __name__ == '__main__':
    main()
