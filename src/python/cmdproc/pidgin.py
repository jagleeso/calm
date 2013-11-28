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
import notify

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
            [['cmd', 'CONVERSATION'], ['arg', 'str', 'Conversation']],
        ],
        'icon': '/usr/share/icons/hicolor/scalable/apps/pidgin.svg',
    }
    def __init__(self, cmdserver_server, cmdserver_port):
        cmd_to_handler = {
            ("RESPOND",): self.cmd_reply,
            ("MESSAGE",): self.cmd_message,
            ("CONVERSATION",): self.cmd_conversation,
        }
        super(PidginCmdProc, self).__init__(cmdserver_server, cmdserver_port, cmd_to_handler=cmd_to_handler)

    def _init_active_conv_idx(self):
        self.active_conv_idx = active_conv_idx()

    def _init_online_buddy_idx(self):
        self.online_buddy_idx = online_buddy_idx()

    def get_candidates(self, request):
        request_args = request[1]
        if request_args == [['MESSAGE'], 1]:
            self._init_active_conv_idx()
            if self.active_conv_idx is None:
                return None
            return sorted(self.active_conv_idx.keys())
        elif request_args == [['CONVERSATION'], 1]:
            if self.online_buddy_idx is None:
                return None
            return sorted(self.online_buddy_idx.keys())

    def start(self):
        logger.info("Starting Pidgin command processor...")
        self.connect()
        setup_dbus_handlers()
        # this thing takes forever, so lets build it first.
        self._init_online_buddy_idx()
        self.receive_and_dispatch_loop()

    def cmd_reply(self, args):
        last_sender = None
        last_sender = _last_sender.value
        logger.info("Got RESPOND command: %s.  Last sender was %s", args, last_sender)
        cmd, message = args

        last_sender = _last_sender.value
        last_conversation = _last_conversation.value
        if last_sender == '':
            logger.info("There is no last sender... ignoring RESPOND and notifying")
            # notify.notify_send("Message not received", "no one to reply to")
            self.notify_server("Message not received", "no one to reply to")
        else:
            send_im(last_conversation, message[1])

    def cmd_message(self, args):
        self._init_active_conv_idx()
        cmd, receiver, message = args
        if message[1] is None:
            # notify.notify_send("Message not delivered since message was empty")
            self.notify_server("Message not delivered since message was empty")
            return
        if self.active_conv_idx is None or receiver[1] not in self.active_conv_idx:
            # notify.notify_send("Message not delivered since conversation doesn't exist", receiver[1])
            self.notify_server("Message not delivered since conversation doesn't exist", receiver[1])
            return
        convo_id = self.active_conv_idx[receiver[1]]
        send_im(convo_id, message[1])

    def cmd_conversation(self, args):
        cmd, receiver = args
        if self.online_buddy_idx is None or receiver[1] not in self.online_buddy_idx:
            # notify.notify_send("Message not delivered since conversation doesn't exist", receiver[1])
            self.notify_server("Couldn't make the conversation since the user doesn't exist", receiver[1])
            return
        account_id, buddy_name = self.online_buddy_idx[receiver[1]]
        new_conversation(account_id, buddy_name)

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

def active_conv_idx():
    d = {}
    active_convo_ids = get_active_convo_ids()
    if active_convo_ids is None:
        return None
    for convo_id in active_convo_ids:
        account_username = get_account_username_for_convo(convo_id)
        receiver_username = get_conversation_title(convo_id)
        if account_username is None or receiver_username is None:
            continue
        key = "{receiver_username} - {account_username}".format(**locals())
        # key = (account_username, receiver_username)
        d[key] = convo_id
    return d

def online_buddy_idx():
    d = {}
    account_ids = get_account_ids()
    for account_id in account_ids:
        account_username = get_account_username(account_id)
        buddy_ids = get_buddy_ids(account_id)
        for buddy_id in buddy_ids:
            if is_buddy_online(buddy_id):
                receiver_username = get_buddy_alias(buddy_id)
                buddy_name = get_buddy_name(buddy_id)
                key = "{receiver_username} - {account_username}".format(**locals())
                d[key] = (account_id, buddy_name)
    return d

def extract_id_set(convo_id_str):
    m = re.match(r'\[Argument: ai \{([^}]*)\}\]', convo_id_str)
    if m is not None:
        convo_ids = set(map(int, (id for id in re.compile(r',\s*').split(m.group(1)) if id is not '')))
        return convo_ids
    return None

def get_account_ids():
    return pidgin_dbus(extract_id_set, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleAccountsGetAllActive', 
            [], qdbus_args=['--literal'])

def get_account_name(account_id):
    def post_process(s):
        return s.rstrip('/\n')
    return pidgin_dbus(post_process, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleAccountGetUsername', 
            [account_id])

def get_buddy_alias(buddy_id):
    return pidgin_dbus(lambda s: s.rstrip(), 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleBuddyGetAlias', 
            [buddy_id], qdbus_args=[])

def get_buddy_name(buddy_id):
    return pidgin_dbus(lambda s: s.rstrip(), 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleBuddyGetName', 
            [buddy_id], qdbus_args=[])

PURPLE_CONV_TYPE_IM = 1
PURPLE_CONV_TYPE_CHAT = 2
def new_conversation(account_id, buddy_name):
    return pidgin_dbus(extract_id_set, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleConversationNew', 
            [PURPLE_CONV_TYPE_IM, account_id, buddy_name], qdbus_args=['--literal'])

def get_buddy_ids(account_id):
    return pidgin_dbus(extract_id_set, 
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleFindBuddies', 
            [account_id, ''], qdbus_args=['--literal'])

def is_buddy_online(buddy_id):
    return pidgin_dbus(lambda s: bool(int(s.rstrip())),
            'im.pidgin.purple.PurpleService', '/im/pidgin/purple/PurpleObject', 
            'im.pidgin.purple.PurpleInterface.PurpleBuddyIsOnline', 
            [buddy_id], qdbus_args=[])

def get_active_convo_ids():
    """
    Return the active conversation id's for pidgin.

    e.g.
    qdbus --literal im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleGetConversations
    [Argument: ai {14537}]
    """
    return pidgin_dbus(extract_id_set, 
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

def get_account_username_for_convo(convo_id):
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
    return get_account_username(account_id)

def get_account_username(account_id):
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
