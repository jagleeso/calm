#!/usr/bin/env python
import cmdserver
from cmdproc import window
import notify

import logging
import argparse
import os

import logconfig
logger = logging.getLogger(__name__)

# import gtk
import gobject
import pygst
pygst.require('0.10')
gobject.threads_init()
import gst

import actextcontrol
import wx

def expanded(widget, padding=0):
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(widget, 1, wx.EXPAND|wx.ALL, padding)
    return sizer

def wx_string_fetcher(app, frm, match_at_start = False, add_option=False, 
        case_sensitive=False, description="text", on_close=None):

    panel = wx.Panel(frm)     
    ok = wx.Button(panel, label="Ok")
    cancel = wx.Button(panel, label="Cancel")
    description_txt = wx.StaticText(panel)
    def set_description(descrip):
        if descrip is None:
            descrip = "text"
        descrip = descrip.lower()
        description_txt.SetLabel("Enter {descrip}:".format(**locals()))
    user_input = actextcontrol.ACTextControl(panel, candidates=[], add_option=False, size=(280, -1))
    user_input.set_description = set_description
    user_input.set_description(description)

    # Set sizer for the frame, so we can change frame size to match widgets
    expand_sizer = wx.BoxSizer()
    expand_sizer.Add(panel, 1, wx.ALL | wx.EXPAND)        

    # Layout our GUI
    sizer = wx.GridBagSizer(2, 5)
    sizer.Add(description_txt, (0, 0))
    sizer.Add(user_input, (1, 0))
    sizer.Add(ok, (1, 1))
    sizer.Add(cancel, (1, 2))

    # Add a border in the window
    border = wx.BoxSizer()
    border.Add(sizer, 1, wx.ALL | wx.EXPAND, 5)

    panel.SetSizerAndFit(border)  
    frm.SetSizerAndFit(expand_sizer)  

    # Hook up callbacks to the ACTextControl callbacks
    def ok_callback_wrapper(event):
        if user_input.callback is not None:
            value = user_input.GetValue()
            if value == '':
                value = None
            user_input.callback(value)
    ok.Bind(wx.EVT_BUTTON, ok_callback_wrapper)
    if on_close is not None:
        cancel.Bind(wx.EVT_BUTTON, on_close)

    user_input.SetValue('')
    
    return user_input

class AutocompleteGUIInputHandler(object):
    def __init__(self):
        self.app = wx.PySimpleApp()
        # import rpdb; rpdb.set_trace()
        self._init_frm()
        # self.timer = 
        self.TIMER_ID = 100  # pick a number
        self.timer = wx.Timer(self.frm, self.TIMER_ID)  # message will be sent to the panel
        # timer.Start(100)  # x100 milliseconds
        wx.EVT_TIMER(self.frm, self.TIMER_ID, self._raise)  # call the on_timer function

    def _init_frm(self):
        # self.frm = wx.Frame(None, -1, "Test", style=wx.DEFAULT_FRAME_STYLE)
        self.frm = wx.Frame(None, -1, "", style=wx.STAY_ON_TOP | wx.DEFAULT_FRAME_STYLE)
        self.app.SetTopWindow(self.frm)
        # self.frm.SetSize((400, 100))
        # self.frm.SetSize((400, 100))
        self.frm.Bind(wx.EVT_CLOSE, self._on_close)
        self.string_fetcher = wx_string_fetcher(self.app, self.frm, on_close=self._on_close)
        self.has_been_shown = False
        self.hex_code = None 
        self.frm.Bind(wx.EVT_SHOW, self._raise)

    def _on_close(self, event):
        assert self.string_fetcher.callback is not None
        self.frm.Hide()
        self.timer.Stop()
        self.string_fetcher.callback(None)
        # self.frm.Destroy()

    def _hide_frm(self):
        self.frm.Hide()
        # self.frm.Destroy()
        # self.frm = None
        # self.string_fetcher = None

    def ask_for_string(self, description, candidates, callback):
        # self._init_frm()
        self.frm.SetTitle("Calm")
        # logger.info("candidates == %s", candidates)
        if candidates is not None and candidates != []:
            self.string_fetcher.all_candidates = candidates
        else:
            self.string_fetcher.all_candidates = [] 
            # self.string_fetcher.hide_popup()
            # logger.info("hide the popup")

        self.string_fetcher.SetValue('')
        def finish_input_wrapper(string):
            if not self.has_been_shown:
                # Get our window identifier
                self.pid = os.getpid()
                self.windows = window.windows()
                for w in self.windows:
                    if w['pid'] == self.pid:
                        assert self.hex_code is None
                        self.hex_code = w['hex_code']
                assert self.hex_code is not None
                self.has_been_shown = True
            self._hide_frm()
            return callback(string)
        self.string_fetcher.callback = finish_input_wrapper
        self.string_fetcher.set_description(description)
        self.frm.Center()
        self.frm.Iconize(False)
        self.frm.Raise()
        self.frm.Show()
        self.frm.SetFocus()
        self.app.SetTopWindow(self.frm)
        self.string_fetcher.SetFocus()

        # TIMER_ID = 100  # pick a number
        # timer = wx.Timer(panel, TIMER_ID)  # message will be sent to the panel
        self.timer.Start(100)  # x100 milliseconds
        # wx.EVT_TIMER(panel, TIMER_ID, on_timer)  # call the on_timer function

        # self.app.SetFocus()
        # self.app.Raise()
        # self.frm.ToggleWindowStyle(wx.STAY_ON_TOP)

    # def _reshow_popup(self):
    #     self.string_fetcher.hide_popup()
    #     self.string_fetcher._on_focus(None)

    def _raise(self, event):
        # logger.info("raise?")
        if self.app.IsActive():
            # logger.info("Looks like we already have focus")
            self.timer.Stop()
            return
        if self.hex_code is not None:
            ws = window.windows()
            c = None
            for w in ws:
                if w['pid'] == self.pid:
                    c = w['hex_code']
            if c == self.hex_code:
                # logger.info("RAISE WINDOW: %s", self.hex_code)
                window.raise_window(self.hex_code)
                # self._reshow_popup()
                self.timer.Stop()
        else:
            # self._reshow_popup()
            self.timer.Stop()

    def main_loop(self):
        self.app.MainLoop()

class VoiceServer(cmdserver.CmdServer):
    def __init__(self, notifier_path, cmdproc_paths, port, ps_lm, ps_dict):
        self.ps_lm = ps_lm
        self.ps_dict = ps_dict
        super(VoiceServer, self).__init__(notifier_path, cmdproc_paths, port)
        self.notifier = 'gui'

    def init_gst(self):
        """Initialize the speech components"""
        self.pipeline = gst.parse_launch('gconfaudiosrc ! audioconvert ! audioresample '
                                         + '! vader name=vad auto-threshold=true '
                                         + '! pocketsphinx name=asr ! fakesink')
        asr = self.pipeline.get_by_name('asr')
        asr.connect('partial_result', self.asr_partial_result)
        asr.connect('result', self.asr_result)

        if self.ps_lm is not None:
            asr.set_property('lm', self.ps_lm)
        if self.ps_dict is not None:
            asr.set_property('dict', self.ps_dict)

        asr.set_property('configured', True)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::application', self.application_message)

        self.start_recording()

    def start(self):
        logger.info("Starting Voice server...")
        self.startup_procs()
        self._cmd_dfa._string_input_handler = AutocompleteGUIInputHandler()
        logger.info("Initializing the pocketsphinx voice server...")
        self.init_gst()
        logger.info("Starting the main loop...")
        self._cmd_dfa._string_input_handler.main_loop()

    # Recording functions

    def start_recording(self):
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop_recording(self):
        vader = self.pipeline.get_by_name('vad')
        vader.set_property('silent', True)

    def pause_recording(self):
        self.pipeline.set_state(gst.STATE_PAUSED)

    def partial_result(self, hyp, uttid):
        """Delete any previous selection, insert text and select it."""
        # All this stuff appears as one single action
        logger.info("PARTIAL: hyp == {hyp}, uttid == {uttid}".format(**locals()))

    def final_result(self, hyp, uttid):
        """Insert the final result."""
        logger.info("FINAL: hyp == {hyp}, uttid == {uttid}".format(**locals()))
        cmd_words = hyp.split()
        def empty_cb():
            pass
        self.dispatch_cmd_to_cmdproc(cmd_words, empty_cb)

    # Glue code for passing messages to the handler thread...

    def asr_partial_result(self, asr, text, uttid):
        """Forward partial result signals on the bus to the main thread."""
        struct = gst.Structure('partial_result')
        struct.set_value('hyp', text)
        struct.set_value('uttid', uttid)
        asr.post_message(gst.message_new_application(asr, struct))

    def asr_result(self, asr, text, uttid):
        """Forward result signals on the bus to the main thread."""
        struct = gst.Structure('result')
        struct.set_value('hyp', text)
        struct.set_value('uttid', uttid)
        asr.post_message(gst.message_new_application(asr, struct))

    def application_message(self, bus, msg):
        """Receive application messages from the bus."""
        msgtype = msg.structure.get_name()
        if msgtype == 'partial_result':
            self.partial_result(msg.structure['hyp'], msg.structure['uttid'])
        elif msgtype == 'result':
            self.final_result(msg.structure['hyp'], msg.structure['uttid'])

def main():
    parser = argparse.ArgumentParser(description="A voice command server.")
    # arg cmd server args
    parser = cmdserver.cmdserver_arg_parser(parser)
    parser.add_argument('--lm', help="Language model (.lm) file")
    parser.add_argument('--dict', help="Dictionary (.dic) file")
    args = parser.parse_args()
    server = VoiceServer(args.notifier, args.cmdproc_paths, args.port, args.lm, args.dict)

    server.start()

if __name__ == '__main__':
    main()
