import pynotify

import procutil

import logging
import logconfig
logger = logging.getLogger(__name__)

class GUINotifier(object):
    """
    Send notifications via system notification bubbles.
    """
    def __init__(self):
        pynotify.init("Why do I need this...")
        self.notice = pynotify.Notification('', '')

    def notify(self, title, message=None):
        # notice = pynotify.Notification(title, message)
        # notice.show()
        msg = get_msg(title, message)
        logger.info("NOTIFY: %s", msg)
        self.notice.update(msg)
        self.notice.show()

class TerminalNotifier(object):
    """
    Send notifications via system notification bubbles.
    """
    def __init__(self):
        pass

    def notify(self, title, message=None):
        if message is None:
            logger.info("NOTIFY <%s>", title)
        else:
            logger.info("NOTIFY <%s>: %s", title, message)

def str_or_empty(x):
    if x is None:
        return ''
    return str(x)

def get_msg(title, message):
    return str_or_empty(title) + ' ' + str_or_empty(message)

def notify_send(title, message=None):
    try:
        msg = get_msg(title, message)
        logger.info("NOTIFY-SEND: %s", msg)
        procutil.call(['notify-send', msg])
    except proctuil.WrappedCalledProcessError:
        logger.exception("notify-osd failed")
