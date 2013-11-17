import pynotify

import logging
import logconfig
logger = logging.getLogger(__name__)

class GUINotifier(object):
    """
    Send notifications via system notification bubbles.
    """
    def __init__(self):
        pynotify.init("Why do I need this...")

    def notify(self, title, message):
        notice = pynotify.Notification(title, message)
        notice.show()

class TerminalNotifier(object):
    """
    Send notifications via system notification bubbles.
    """
    def __init__(self):
        pass

    def notify(self, title, message):
        logger.info("NOTIFY <%s>: %s", title, message)
