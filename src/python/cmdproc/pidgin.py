#!/usr/bin/env python
import cmdproc

# https://developer.pidgin.im/wiki/DbusHowto
# provide asynchronous 
import dbus
import gobject
import argparse
from dbus.mainloop.glib import DBusGMainLoop
import logging
import subprocess

from multiprocessing import Process, Lock, Array, Value
from threading import Thread

import logconfig
logger = logging.getLogger(__name__)

# Keeping track of pidgen messenger's state based on received messages.

# Mutex over all messenger state.
# _state_lock = Lock()
# Who last sent us a message (used as a received for a REPLY command)?
# _last_sender = None
_last_sender = Array('c', 1024, lock=True)
_last_conversation = Value('i', lock=True)

class PidginCmdProc(cmdproc.CmdProc):
    config = {
        'program': 'pidgin',
        'commands': [ 
            # [['cmd', 'REPLY'], ['arg', ['many', 'str']]],
            [['cmd', 'REPLY'], ['arg', 'str', "Reply"]],
        ],
    }
    def __init__(self, cmdserver_server, cmdserver_port):
        cmd_to_handler = {
            ("REPLY",): self.cmd_reply,
        }
        super(PidginCmdProc, self).__init__(cmdserver_server, cmdserver_port, cmd_to_handler=cmd_to_handler)

    def start(self):
        logger.info("Starting Pidgin command processor...")
        self.connect()
        setup_dbus_handlers()
        self.receive_and_dispatch_loop()

    def cmd_reply(self, args):
        last_sender = None
        last_sender = _last_sender.value
        logger.info("Got REPLY command: %s.  Last sender was %s", args, last_sender)
        cmd, message = args

        # logger.info("HERE GOES....")
        # bus = dbus.SessionBus()
        # logger.info("GOT DBUS....")
        # logger.info("GOT VALUES....")
        # obj = bus.get_object("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject")
        # logger.info("GOT OBJECT....")
        # purple = dbus.Interface(obj, "im.pidgin.purple.PurpleInterface")
        # logger.info("GOT PURPLE....")
        # # logger.info("purple.PurpleGetIms(): %s.", purple.PurpleGetIms())
        # purple.PurpleConvImSend(purple.PurpleConvIm(last_conversation), " ".join(["bananas", "grapes"]))
        # logger.info("DONE....")

        last_sender = _last_sender.value
        last_conversation = _last_conversation.value
        if last_sender == '':
            logger.info("There is no last sender... ignoring REPLY")
        else:
            send_im(last_conversation, message[1])

        # obj = self.bus.get_object("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject")
        # purple = dbus.Interface(obj, "im.pidgin.purple.PurpleInterface")
        # logger.info("purple.PurpleGetIms(): %s.", purple.PurpleGetIms())
        # purple.PurpleConvImSend(purple.PurpleConvIm(last_sender), " ".join(args))

def receive_msg(account, sender, message, conversation, flags):
    global _last_sender
    logger.info("receive_msg DBUS: %s said \"%s\", old _last_sender == %s", sender, message, _last_sender.value)
    logger.info("receive_msg DBUS: conversation == %s", conversation)

    _last_sender.value = sender
    _last_conversation.value = conversation

    # This works...but its not where we want it
    # logger.info("HERE GOES....")
    # bus = dbus.SessionBus()
    # last_sender = _last_sender.value
    # last_conversation = _last_conversation.value
    # obj = bus.get_object("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject")
    # purple = dbus.Interface(obj, "im.pidgin.purple.PurpleInterface")
    # logger.info("purple.PurpleGetIms(): %s.", purple.PurpleGetIms())
    # purple.PurpleConvImSend(purple.PurpleConvIm(conversation), " ".join(["bananas", "grapes"]))
    # logger.info("DONE....")

def setup_dbus_handlers():
    """
    Spawn a separate thread that listens for dbus events. 
    """
    logger.info("Setting up dbus handlers...")
    def setup():
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        bus.add_signal_receiver(receive_msg,
                                dbus_interface="im.pidgin.purple.PurpleInterface",
                                signal_name="ReceivedImMsg")

        loop = gobject.MainLoop()
        logger.info("Run the loop....")
        loop.run()
        logger.info("Running")
    dbus.mainloop.glib.threads_init()
    dbus_thread = Process(target=setup)
    logger.info("Start DBUS thread....")
    dbus_thread.start()
    logger.info("Started.")

def send_dbus(service, path, method, args=[]):
    """
    So basically, I can't figure out threading with dbus in python, so just invoke qdbus command line program instead to send a reply...

    qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvIm $conversation
    qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvImSend $convIMResult 'hello world'
    """
    return subprocess.check_output(["qdbus", service, path, method] + [str(a) for a in args])

def send_im(conversation, message):
     # First we have to get a "ConvIm" id from the conversation id we got in receive_msg.
     try: 
         conv_im = int(send_dbus("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject", "im.pidgin.purple.PurpleInterface.PurpleConvIm", [conversation]).rstrip())
         # Then we use the ConvIm to identify the conversation and send it a message.
         return send_dbus("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject", "im.pidgin.purple.PurpleInterface.PurpleConvImSend", [conv_im, message]).rstrip()
     except subprocess.CalledProcessError:
         logger.exception("Looks like pidgin isn't running")

def main():
    parser = argparse.ArgumentParser(description="A pidgin command processor.")
    args, processor = cmdproc.cmdproc_main(PidginCmdProc, parser)
    processor.start()
        
if __name__ == '__main__':
    main()
