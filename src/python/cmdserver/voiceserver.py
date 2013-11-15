#!/usr/bin/env python
import cmdserver
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

def wx_string_fetcher(app, frm, match_at_start = False, add_option=False, case_sensitive=False):
    panel = wx.Panel(frm)
    
    label1 = wx.StaticText(panel, -1, 'Matches anywhere in string')
    ctrl1 = actextcontrol.ACTextControl(panel, candidates=[], add_option=False)

    fgsizer = wx.FlexGridSizer(rows=4, cols=2, vgap=20, hgap=10)
    fgsizer.AddMany([label1, ctrl1])
    
    panel.SetAutoLayout(True)
    panel.SetSizer(fgsizer)
    fgsizer.Fit(panel)

    ctrl1.SetValue('')
    
    panel.Layout()

    return ctrl1

class AutocompleteGUIInputHandler(object):
    def __init__(self):
        self.app = wx.PySimpleApp()
        self.frm = wx.Frame(None, -1, "Test", style=wx.DEFAULT_FRAME_STYLE)
        self.app.SetTopWindow(self.frm)
        self.frm.SetSize((400, 250))
        self.frm.Bind(wx.EVT_CLOSE, self._on_close)
        self.string_fetcher = wx_string_fetcher(self.app, self.frm)

    def _on_close(self, event):
        assert self.string_fetcher.callback is not None
        self.frm.Hide()
        self.string_fetcher.callback(None)

    def ask_for_string(self, description, candidates, callback):
        self.frm.SetTitle(description)
        self.string_fetcher.candidates = candidates
        def finish_input_wrapper(string):
            self.frm.Hide()
            return callback(string)
        self.string_fetcher.callback = finish_input_wrapper
        self.string_fetcher.SetFocus()
        self.frm.Show()
        # string = raw_input("Give me a {description}: ".format(**locals()))
        # return string

    def main_loop(self):
        self.app.MainLoop()

class VoiceServer(cmdserver.CmdServer):
    def __init__(self, cmdproc_paths, port, ps_lm, ps_dict):
        self.ps_lm = ps_lm
        self.ps_dict = ps_dict
        super(VoiceServer, self).__init__(cmdproc_paths, port)

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
        self.init_gst()
        self._cmd_dfa._string_input_handler.main_loop()
        # actextcontrol.test()
        # gtk.main()
        # while True:
        #     try:
        #         cmd_string = raw_input(">> ")
        #     except EOFError:
        #         cmdserver.exit_server()
        #     cmd = cmd_string.split()
        #     self.dispatch_cmd_to_cmdproc(cmd)

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
        # try:
        #     self._cmd_dfa.cmd(cmd_words)
        # except (cmdserver.IncompleteCmdProcCommand, cmdserver.BadCmdProcCommand, 
        #         cmdserver.IncompleteCmdServerCommand, cmdserver.BadCmdServerCommand) as e:
        #     logger.exception(e.message)

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

    # def dispatch_cmd_to_cmdproc(self, cmd_strs):
    #     pass

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