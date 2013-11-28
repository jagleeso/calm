#!/usr/bin/env python
import cmdproc
import mydbus
import procutil
import notify

# https://developer.pidgin.im/wiki/DbusHowto
# provide asynchronous 
import gobject
import argparse

import logging

from multiprocessing import Process, Value, Array, Lock, Manager

import logconfig
logger = logging.getLogger(__name__)

class ClementineCmdProc(cmdproc.CmdProc):
    config = {
        'program': 'clementine',
        'commands': [ 
            [['cmd', 'PLAY']],
            [['cmd', 'PAUSE']],
            [['cmd', 'STOP']],
            [['cmd', 'VOLUME'], ['arg', 'int', "Volume Level", "A number between 0 and 100"]],
            [['cmd', 'NEXT']],
            [['cmd', 'PREVIOUS']],
            [['cmd', 'TRACK'], ['arg', 'str', "Track to Play", "The name of a track in your playlist"]],
            [['cmd', 'PLAYING']],
        ],
        'icon': '/usr/share/icons/hicolor/scalable/apps/application-x-clementine.svg',
    }
    def __init__(self, cmdserver_server, cmdserver_port):
        cmd_to_handler = {
            ("PLAY",): self.cmd_play,
            ("PAUSE",): self.cmd_pause,
            ("STOP",): self.cmd_stop,
            ("VOLUME",): self.cmd_volume,
            ("NEXT",): self.cmd_next,
            ("PREVIOUS",): self.cmd_previous,
            ("TRACK",): self.cmd_track,
            ("PLAYING",): self.cmd_playing,
        }
        super(ClementineCmdProc, self).__init__(cmdserver_server, cmdserver_port, cmd_to_handler=cmd_to_handler)

        self._tracklock = Lock()
        self.track_infos = self._manager.list()
        self.track_index = self._manager.dict()

        self._init_tracklist()

    def get_candidates(self, request):
        request_args = request[1]
        if request_args == [['TRACK'], 1]:
            self._init_tracklist()
            if len(self.track_index) == 0:
                return []
            else:
                return self.track_index.keys()

    def _init_tracklist(self):
        self._tracklock.acquire()
        if len(self.track_infos) > 0:
            self._tracklock.release()
            return
        try:
            tracklist_info(self.track_infos)
            track_search_index(self.track_infos, self.track_index)
        except procutil.WrappedCalledProcessError:
            logger.info("Looks like clementine isn't started yet; delay tracklist initialization until it's started.")
        finally:
            self._tracklock.release()

    def start(self):
        logger.info("Starting Clementine command processor...")
        self.connect()
        self.receive_and_dispatch_loop()

    def cmd_play(self, args):
        logger.info("cmd_play %s", args)
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Play')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_pause(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Pause')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_stop(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Stop')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_next(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Next')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_previous(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.Prev')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_volume(self, args):
        cmd, level = args
        try:
            result = mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.VolumeSet', [level[1]])
            if self.is_recording():
                self.put_cmd(args, **{})
            return result
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_track(self, args):
        """
        e.g.
        qdbus org.mpris.clementine /TrackList org.freedesktop.MediaPlayer.PlayTrack 0 
        """
        cmd, track = args
        self._init_tracklist()
        if len(self.track_infos) == 0:
            logger.exception("Looks like clementine isn't running...")
            return
        track_number = None
        try:
            track_number = self.track_index[track[1]]
        except KeyError:
            logger.exception("No such track \"%s\"...", track[1])
            self.notify_server("No such track", track[1])
            return
        try:
            result = mydbus.send_dbus('org.mpris.clementine', '/TrackList', 'org.freedesktop.MediaPlayer.PlayTrack', [track_number])
            if self.is_recording():
                self.put_cmd(args, **{})
            return result
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

    def cmd_playing(self, args):
        try:
            return mydbus.send_dbus('org.mpris.clementine', '/Player', 'org.freedesktop.MediaPlayer.ShowOSD')
        except mydbus.WrappedCalledProcessError as e:
            logger.exception("Looks like clementine isn't running...")

def track_info(track_number):
    """
    e.g.
    qdbus org.mpris.clementine /TrackList org.freedesktop.MediaPlayer.GetMetadata 122 
    """
    info_string = mydbus.send_dbus('org.mpris.clementine', '/TrackList', 'org.freedesktop.MediaPlayer.GetMetadata', [track_number])
    info_string.rstrip()
    field_delim = ': '
    d = {}
    for line in info_string.splitlines():
        fields = line.split(field_delim)
        field_name = fields[0]
        value = None
        if len(fields) == 2:
            value = fields[1]
        else:
            value = fields[0] + ''.join(field_delim + e for e in fields[1:len(fields)])
        d[field_name] = value
        d['track_number'] = str(track_number)
    if d == {}:
        return None
    return d

def tracklist_info(tracks=None):
    if tracks is None:
        tracks = []
    i = 0
    while True:
        info = track_info(i)
        if info is None:
            break
        tracks.append(info)
        i += 1
    return tracks

def track_search_index(track_infos, index=None):
    """
    Mapping from (track search string to match against) -> (track number)
    """
    if index is None:
        index = {}
    for info in track_infos:
        s = ''  
        if 'artist' in info:
            s = info['artist'] + ' - ' 
        s = s + info['title']
        index[s] = info['track_number']
    return index

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
