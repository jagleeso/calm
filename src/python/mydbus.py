# import subprocess
# from StringIO import StringIO

import procutil

import logging
import logconfig
logger = logging.getLogger(__name__)

class WrappedCalledProcessError(Exception):
    pass

def send_dbus(service, path, method, args=[], qdbus_args=[]):
    """
    So basically, I can't figure out threading with dbus in python, so just invoke qdbus command line program instead to send a reply...

    qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvIm $conversation
    qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvImSend $convIMResult 'hello world'
    """
    def stringify(xs):
        return [str(x) for x in xs]

    cmd = ["qdbus"] + stringify(qdbus_args) + [service, path, method] + stringify(args) 
    return procutil.call(cmd)
