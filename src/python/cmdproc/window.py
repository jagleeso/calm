#!/usr/bin/env python
import cmdproc
import mydbus
import procutil

# https://developer.pidgin.im/wiki/DbusHowto
# provide asynchronous 
import argparse
import subprocess
import wx
import sys

import logging

import logconfig
logger = logging.getLogger(__name__)

class WindowCmdProc(cmdproc.CmdProc):
    config = {
        'program': 'window',
        'commands': [ 
            [['cmd', 'LEFT']],
            [['cmd', 'RIGHT']],
            [['cmd', 'MAXIMIZE']],
            [['cmd', 'UPPER'], ['cmd', 'LEFT']],
            [['cmd', 'UPPER'], ['cmd', 'RIGHT']],
            [['cmd', 'BOTTOM'], ['cmd', 'LEFT']],
            [['cmd', 'BOTTOM'], ['cmd', 'RIGHT']],
        ],
    }
    def __init__(self, cmdserver_server, cmdserver_port):
        cmd_to_handler = {
            ('LEFT',): self.cmd_left,
            ('RIGHT',): self.cmd_right,
            ('MAXIMIZE',): self.cmd_maximize,
            ('UPPER', 'LEFT'): self.cmd_upper_left,
            ('UPPER', 'RIGHT'): self.cmd_upper_right,
            ('BOTTOM', 'LEFT'): self.cmd_bottom_left,
            ('BOTTOM', 'RIGHT'): self.cmd_bottom_right,
        }
        super(WindowCmdProc, self).__init__(cmdserver_server, cmdserver_port, cmd_to_handler=cmd_to_handler)
        self.screen_width, self.screen_height = get_resolution()

    def start(self):
        logger.info("Starting Window Manager command processor...")
        self.connect()
        self.receive_and_dispatch_loop()

    def macro_check(self, window, args, kwargs):
        ws = windows()
        if not any(w['hex_code'] == window for w in ws):
            # The window may no longer exist if this command is being replayed with a macro
            return False
        # logger.info("is_recording? %s", self.is_recording())
        if self.is_recording():
            # self.put_cmd(lambda: cmd_func(args, window=window))
            self.put_cmd(args, **kwargs)
        return True

    def cmd_left(self, args, **kwargs):
        # import rpdb; rpdb.set_trace()
        # logger.info("in window... recording == %s", self._recording.value);
        # self.log_recording()
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = 0
        y = 0
        width = self.screen_width // 2
        height = self.screen_height
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

    def cmd_right(self, args, **kwargs):
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = self.screen_width // 2
        y = 0
        width = self.screen_width // 2
        height = self.screen_height
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

    def cmd_upper_left(self, args, **kwargs):
        # import rpdb; rpdb.set_trace()
        # logger.info("in window... recording == %s", self._recording.value);
        # self.log_recording()
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = 0
        y = 0
        width = self.screen_width // 2
        height = self.screen_height // 2
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

    def cmd_upper_right(self, args, **kwargs):
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = self.screen_width // 2
        y = 0
        width = self.screen_width // 2
        height = self.screen_height // 2
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

    def cmd_bottom_left(self, args, **kwargs):
        # import rpdb; rpdb.set_trace()
        # logger.info("in window... recording == %s", self._recording.value);
        # self.log_recording()
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = 0
        y = self.screen_height // 2
        width = self.screen_width // 2
        height = self.screen_height // 2
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

    def cmd_bottom_right(self, args, **kwargs):
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = self.screen_width // 2
        y = self.screen_height // 2
        width = self.screen_width // 2
        height = self.screen_height // 2
        width = self.screen_width // 2
        height = self.screen_height // 2
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

    def cmd_maximize(self, args, **kwargs):
        if 'window' not in kwargs:
            kwargs['window'] = get_current_window()
        if not self.macro_check(kwargs['window'], args, kwargs):
            return
        x = 0
        y = 0
        width = self.screen_width
        height = self.screen_height
        move_window(kwargs['window'], x, y, width, height)
        focus_window(kwargs['window'])

def get_resolution():
    # for some reason we need to assign it to a variable for this to work...
    app = wx.App(False)
    return wx.GetDisplaySize()

def get_current_window():
    """
    Get the unique hex code identifier of the currently active window (i.e. the one in focus). 
    """
    
    int_code = int(subprocess.check_output(['xdotool', 'getactivewindow']).rstrip())
    # hex_code = hex()
    hex_code = "{0:#0{1}x}".format(int_code,8+2)
    return hex_code

def focus_window(hex_code):
    return subprocess.check_call(['wmctrl', '-i', '-a', hex_code], stderr=sys.stderr)

def move_window(hex_code, x, y, width, height):
    gravity = 0
    return subprocess.check_call(['wmctrl', '-i', '-r', hex_code, '-e', ','.join(map(str, [gravity, x, y, width, height]))], stderr=sys.stderr)

def windows():
    """
    As per the wmctrl man page entry for the -l option:

    List the windows being managed by the window manager. One line is output for  each  
    window,  with  the line  broken up into space separated columns.  The first column always 
    contains the window identity as a hexadecimal integer, and the second column always 
    contains the desktop  number  (a  -1  is  used  to identify  a sticky window). If the -p 
    option is specified the next column will contain the PID for the window as a decimal 
    integer. If the -G option is specified then four integer columns will  follow:  x- offset,  
    y-offset,  width  and  height.  The  next column always contains the client machine name. 
    The remainder of the line contains the window title (possibly with multiple spaces in the 
    title). 

    Return this information as list of dicts.
    """
    dicts = []
    for window_str in subprocess.check_output(['wmctrl', '-lG', '-p']).split('\n'):
        f = window_str.split()
        if f == []:
            continue 
        d = {
                'hex_code':f[0], 
                'desktop_number':'sticky' if f[1] == '-1' else 'normal',
                'pid':int(f[2]),
                'x':int(f[3]),
                'y':int(f[4]),
                'width':int(f[5]),
                'height':int(f[6]),
                'machine':f[7],
                'title':" ".join(f[8:]),
        }
        dicts.append(d)
    return dicts

def receive_msg(account, sender, message, conversation, flags):
    global _last_sender
    logger.info("DBUS: %s said: \"%s\", old _last_sender == %s", sender, message, _last_sender.value)
    # _state_lock.acquire()
    _last_sender.value = sender
    # _state_lock.release()

def get_current_program():
    """
    Get the current program name of the active window.
    """
    current_window = get_current_window()
    ws = windows()
    pid = None
    for w in ws:
        if w['hex_code'] == current_window:
            pid = w['pid']
    if pid is None:
        return None
    program_name = name_from_pid(pid)
    if program_name is None:
        return None
    return program_name.rstrip()

def name_from_pid(pid): 
    """
    E.g.
    ps -p 23827 -o comm= 
    """
    name = procutil.call(['ps', '-p', str(pid), '-o', 'comm='])
    return name

def main():
    parser = argparse.ArgumentParser(description="A window manager command processor.")
    args, processor = cmdproc.cmdproc_main(WindowCmdProc, parser)
    processor.start()
        
if __name__ == '__main__':
    main()
