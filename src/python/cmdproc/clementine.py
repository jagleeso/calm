#!/usr/bin/env python
import cmdproc
import mydbus

# https://developer.pidgin.im/wiki/DbusHowto
# provide asynchronous 
import gobject
import argparse

import logging

import logconfig
logger = logging.getLogger(__name__)

class ClementineCmdProc(cmdproc.CmdProc):
    config = {
        'program': 'clementine',
        'commands': [ 
            [['cmd', 'PLAY']],
            [['cmd', 'PAUSE']],
            [['cmd', 'VOLUME'], ['arg', 'int', "Volume Level"]],
            [['cmd', 'NEXT']],
            [['cmd', 'PREVIOUS']],
        ],
    }
    def __init__(self, cmdserver_server, cmdserver_port):
        cmd_to_handler = {
            ("PLAY",): self.cmd_play,
            ("PAUSE",): self.cmd_pause,
            ("VOLUME",): self.cmd_volume,
            ("NEXT",): self.cmd_next,
            ("PREVIOUS",): self.cmd_previous,
        }
        super(ClementineCmdProc, self).__init__(cmdserver_server, cmdserver_port, cmd_to_handler=cmd_to_handler)

    def start(self):
        logger.info("Starting Clementine command processor...")
        self.connect()
        self.receive_and_dispatch_loop()

    def cmd_play(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Play')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_pause(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Pause')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_next(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Next')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_previous(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Previous')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_volume(self, args):
        cmd, level = args
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.VolumeSet', [level[1]])
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

def receive_msg(account, sender, message, conversation, flags):
    global _last_sender
    logger.info("DBUS: %s said: \"%s\", old _last_sender == %s", sender, message, _last_sender.value)
    # _state_lock.acquire()
    _last_sender.value = sender
    # _state_lock.release()

def main():
    parser = argparse.ArgumentParser(description="A clementine command processor.")
    args, processor = cmdproc.cmdproc_main(ClementineCmdProc, parser)
    processor.start()
        
if __name__ == '__main__':
    main()
