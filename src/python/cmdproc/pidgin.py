#!/usr/bin/env python
import cmdproc
import mydbus

# https://developer.pidgin.im/wiki/DbusHowto
# provide asynchronous 
import dbus
import re
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
# Who last sent us a message (used as a received for a RESPOND command)?
# _last_sender = None
_last_sender = Array('c', 1024, lock=True)
_last_conversation = Value('i', lock=True)

class PidginCmdProc(cmdproc.CmdProc):
    config = {
        'program': 'pidgin',
        'commands': [ 
            [['cmd', 'MESSAGE'], ['arg', 'str', 'Conversation'], ['arg', 'str', 'Message']],
            [['cmd', 'RESPOND'], ['arg', 'str', 'Message']],
        ],
    }
    def __init__(self, cmdserver_server, cmdserver_port):
        cmd_to_handler = {
            ("RESPOND",): self.cmd_reply,
            ("MESSAGE",): self.cmd_message,
        }
        super(PidginCmdProc, self).__init__(cmdserver_server, cmdserver_port, cmd_to_handler=cmd_to_handler)

    def _init_conversation_index(self):
        self.conversation_index = conversation_index()

    def get_candidates(self, request):
        request_args = request[1]
        if request_args == [['MESSAGE'], 1]:
            self._init_conversation_index()
            return sorted(self.conversation_index.keys())

    def start(self):
        logger.info("Starting Pidgin command processor...")
        self.connect()
        setup_dbus_handlers()
        self.receive_and_dispatch_loop()

    def cmd_reply(self, args):
        last_sender = None
        last_sender = _last_sender.value
        logger.info("Got RESPOND command: %s.  Last sender was %s", args, last_sender)
        cmd, message = args

        last_sender = _last_sender.value
        last_conversation = _last_conversation.value
        if last_sender == '':
            logger.info("There is no last sender... ignoring RESPOND")
        else:
            send_im(last_conversation, message[1])

    def cmd_message(self, args):
        self._init_conversation_index()
        cmd, receiver, message = args
        if receiver[1] not in self.conversation_index:
            self.notifier.notify("Message not delivered since conversation doesn't exist:", receiver[1])
            return
        convo_id = self.conversation_index[receiver[1]]
        send_im(convo_id, message[1])

def receive_msg(account, sender, message, conversation, flags):
    global _last_sender
    logger.info("receive_msg DBUS: %s said \"%s\", old _last_sender == %s", sender, message, _last_sender.value)
    logger.info("receive_msg DBUS: conversation == %s", conversation)

    _last_sender.value = sender
    _last_conversation.value = conversation

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

def pidgin_dbus(post_process, service, path, method, args=[], qdbus_args=[]):
     try: 
         result = mydbus.send_dbus(service, path, method, args, qdbus_args).rstrip()
         return post_process(result)
     except mydbus.WrappedCalledProcessError:
         logger.exception("Looks like pidgin isn't running")
         return None

def send_im(conversation, message):
     # First we have to get a "ConvIm" id from the conversation id we got in receive_msg.
     try: 
         conv_im = int(mydbus.send_dbus("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject", "im.pidgin.purple.PurpleInterface.PurpleConvIm", [conversation]).rstrip())
         # Then we use the ConvIm to identify the conversation and send it a message.
         return mydbus.send_dbus("im.pidgin.purple.PurpleService", "/im/pidgin/purple/PurpleObject", "im.pidgin.purple.PurpleInterface.PurpleConvImSend", [conv_im, message]).rstrip()
     except mydbus.WrappedCalledProcessError:
         logger.exception("Looks like pidgin isn't running")

def conversation_index():
    d = {}
    for convo_id in get_active_convo_ids():
        account_username = get_account_username(convo_id)
        receiver_username = get_conversation_title(convo_id)
        if account_username is None or receiver_username is None:
            continue
        key = "{receiver_username} - {account_username}".format(**locals())
        # key = (account_username, receiver_username)
        d[key] = convo_id
    return d

def get_active_convo_ids():
    """
    Return the active conversation id's for pidgin.

    e.g.
    qdbus --literal im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleGetConversations
    [Argument: ai {14537}]
    """
    def convo_id_set(convo_id_str):
        m = re.match(r'\[Argument: ai \{([^}]*)\}\]', convo_id_str)
        if m is not None:
            convo_ids = set(map(int, (id for id in re.compile(r',\s*').split(m.group(1)) if id is not '')))
            return convo_ids
        return None
    return pidgin_dbus(convo_id_set, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleGetConversations', 
            [], qdbus_args=['--literal'])

def get_account_id(convo_id):
    """
    e.g.
    $ qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConversationGetAccount 56788

    887
    """
    if convo_id is None:
        return None
    return pidgin_dbus(int, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleConversationGetAccount',
            [convo_id])

def get_account_username(convo_id):
    """
    e.g.
    $ qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleAccountGetUsername 946

    Username 946
    jagleeso@gmail.com/

    Returns:
    jagleeso@gmail.com/
    """
    if convo_id is None:
        return None
    account_id = get_account_id(convo_id)
    if account_id is None:
        return None
    def extract_account_username(account):
        """
        Given:
        jagleeso@gmail.com/

        Return:
        jagleeso@gmail.com
        """
        return account.rstrip('/')
    return pidgin_dbus(extract_account_username, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleAccountGetUsername',
            [account_id])

def get_conversation_title(convo_id):
    """
    $ qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConversationGetTitle 42906

    jiawen zhang
    """
    if convo_id is None:
        return None
    return pidgin_dbus(lambda x: x, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleConversationGetTitle', 
            [convo_id])

def main():
    parser = argparse.ArgumentParser(description="A pidgin command processor.")
    args, processor = cmdproc.cmdproc_main(PidginCmdProc, parser)
    processor.start()
        
if __name__ == '__main__':
    main()
