#!/usr/bin/env python
import cmdserver
import notify

import logging
import argparse

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

def wx_string_fetcher(app, frm, match_at_start = False, add_option=False, case_sensitive=False, description="Enter text"):
    panel = wx.Panel(frm)
    
    label1 = wx.StaticText(panel, -1, description)
    ctrl1 = actextcontrol.ACTextControl(panel, candidates=[], add_option=False)

    box = wx.BoxSizer(wx.HORIZONTAL)
    box.Add(label1, 1, wx.EXPAND)
    box.Add(ctrl1, 3, wx.EXPAND)

    panel.SetSizer(box)
    panel.Layout()
    panel.SetAutoLayout(True)

    ctrl1.SetValue('')
    
    return ctrl1

class AutocompleteGUIInputHandler(object):
    def __init__(self):
        self.app = wx.PySimpleApp()
        self.frm = wx.Frame(None, -1, "Test", style=wx.DEFAULT_FRAME_STYLE)
        self.app.SetTopWindow(self.frm)
        # self.frm.SetSize((400, 100))
        # self.frm.SetSize((400, 100))
        self.frm.Bind(wx.EVT_CLOSE, self._on_close)
        self.string_fetcher = wx_string_fetcher(self.app, self.frm)

    def _on_close(self, event):
        assert self.string_fetcher.callback is not None
        self.frm.Hide()
        self.string_fetcher.callback(None)

    def ask_for_string(self, description, candidates, callback):
        self.frm.SetTitle(description)
        logger.info("candidates == %s", candidates)
        if candidates is not None and candidates != []:
            self.string_fetcher.all_candidates = candidates
        else:
            self.string_fetcher.all_candidates = [] 
            self.string_fetcher.hide_popup()
            logger.info("hide the popup")

        self.string_fetcher.SetValue('')
        def finish_input_wrapper(string):
            self.frm.Hide()
            return callback(string)
        self.string_fetcher.callback = finish_input_wrapper
        self.string_fetcher.SetFocus()
        self.frm.Center()
        self.frm.Show()
        self.frm.ToggleWindowStyle(wx.STAY_ON_TOP)

    def main_loop(self):
        self.app.MainLoop()

class VoiceServer(cmdserver.CmdServer):
    def __init__(self, cmdproc_paths, port, ps_lm, ps_dict):
        self.ps_lm = ps_lm
        self.ps_dict = ps_dict
        super(VoiceServer, self).__init__(cmdproc_paths, port)
        self.notifier = notify.GUINotifier()

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
        self.startup_cmdprocs()
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
    server = VoiceServer(args.cmdproc_paths, args.port, args.lm, args.dict)

    server.start()

if __name__ == '__main__':
    main()
