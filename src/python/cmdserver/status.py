#!/usr/bin/env python

import sys
import gtk
import gobject
# import wx
import appindicator
import argparse

import imaplib
import re

import config
import cmdserver

import connect
import message

import logging
import logconfig
logger = logging.getLogger(__name__)

class CalmStatus:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.ind = appindicator.Indicator("calm-indicator",
                                           "indicator-messages",
                                           appindicator.CATEGORY_APPLICATION_STATUS)
        self.ind.set_status(appindicator.STATUS_ACTIVE)
        self.ind.set_attention_icon("new-messages-red")

        self.menu_setup()
        self.ind.set_menu(self.menu)

        icon1 = '/usr/share/icons/hicolor/scalable/apps/application-x-clementine.svg'
        icon2 = '/usr/share/icons/hicolor/scalable/apps/pidgin.svg'
        self.icons = [icon1, icon2]
        self.current_icon = 0

    def menu_setup(self):
        self.menu = gtk.Menu()

        # self.quit_item = gtk.MenuItem("Quit")
        # self.quit_item.connect("activate", self.quit)
        # self.quit_item.show()
        # self.menu.append(self.quit_item)

    def main(self):
        self.cmdserver_socket = connect.listen_for_client(self.host, self.port, server_name='status server', client_name='command server')
        # gobject.IO_IN	    There is data to read.
        # gobject.IO_OUT	Data can be written (without blocking).
        # gobject.IO_PRI	There is urgent data to read.
        # gobject.IO_ERR	Error condition.
        # gobject.IO_HUP	Hung up (the connection has been broken, usually for pipes and sockets).
        gobject.io_add_watch(self.cmdserver_socket.makefile('r'), gobject.IO_IN | gobject.IO_ERR | gobject.IO_HUP, self.new_status)
        initial_status = ['status', cmdserver.CmdServer.config['icon']]
        self.update_status(initial_status)
        gtk.main()

    def new_status(self, source, cb_condition):
        if (cb_condition & gobject.IO_ERR) or (cb_condition & gobject.IO_HUP):
            logger.info("Error on socket")
            sys.exit(1)
        else:
            assert cb_condition & gobject.IO_IN
            status = message.recv_status(self.cmdserver_socket)
            self.update_status(status)
        return True

    def update_status(self, status):
        icon = status[1]
        self.ind.set_icon(icon)

    def quit(self, widget):
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="A status changer.")
    args = parser.parse_args()
    indicator = CalmStatus(config.DEFAULT_HOST, config.DEFAULT_STATUS_PORT)
    indicator.main()
        
if __name__ == '__main__':
    main()
